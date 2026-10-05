# Group underwriting and stop-loss pricing on Medicare claims

Predicts next-year medical and pharmacy cost for members of employer groups, the probability that
a member crosses a stop-loss specific deductible, the tail of large claims above it, and the
resulting specific and aggregate stop-loss cost per group, then compares those prices with what
actually happened the following year. Built as Kedro pipelines on CMS DE-SynPUF claims, with a dbt
feature mart reconciled row for row against the Python features.

> **Status: synthetic data only so far.** The CMS download hosts were blocked from the environment
> this was built in, so every number below comes from the offline synthetic mode: generated files
> in the DE-SynPUF layout, with a generator we wrote. They show the pipeline works end to end. They
> are not findings about Medicare or employer populations. The real-data tests are pre-registered
> in [`docs/preregistration.md`](docs/preregistration.md) and haven't been run yet.

## Question
Using only claims visible at a pricing date, can member-level models price specific and aggregate
stop-loss for employer groups of 50–2,500 lives so that next year's actual loss ratio lands near
the priced one, and how much worse is that for small groups?

## Data
| Source | Grain | Used for |
|---|---|---|
| DE-SynPUF Beneficiary Summary 2008–2010 (Sample 2) | member × year | Eligibility, age, sex, ESRD, 11 chronic-condition flags, coverage months, state/county |
| DE-SynPUF Inpatient, Outpatient, Carrier (A+B) claims | claim | Allowed cost by setting, stays, days, visit counts |
| DE-SynPUF Prescription Drug Events | fill | Pharmacy cost, fills, distinct drugs, specialty fills |

Allowed cost is rebuilt from payment, primary-payer and beneficiary-liability fields because
facility claims carry no allowed amount. DE-SynPUF has no paid date, so one is simulated per claim
type ([decisions](docs/decisions.md)).

**Employer groups are synthetic.** Within each split, members are sorted by state and county and
cut into consecutive blocks whose sizes are drawn from five bands (50–99 up to 1,000–2,500), so
groups are local like real employers. The members are Medicare beneficiaries, 65+ or disabled, so
these groups are an age-skewed proxy for a working-age employer population.

## Method
1. **Point-in-time features** as of Dec 31 of the feature year, from claims incurred that year and
   paid within 3 months after it (32 features: demographics, chronic flags, cost by setting,
   utilization, pharmacy). Race is not used.
2. **Out-of-time validation.** Members split 50/50 by ID hash. Train: training members, 2008
   features → 2009 cost. Test: the other members, 2009 features → 2010 cost. No member or group in
   both. 2010 predictions are trended by the 2008 → 2009 PMPM change at equal runout.
3. **Member and group cost.** Tweedie GLM (frozen baseline) vs Tweedie LightGBM, exposure-weighted,
   aggregated to group PMPM. MAE, Gini, predictive ratio by decile, predicted / actual.
4. **High-cost claimants.** P(annual cost > $25k / $50k / $100k): logistic baseline vs LightGBM.
   AUC, PR-AUC, Brier, calibration, top-decile lift.
5. **Tail.** Generalized Pareto above $25k on training members' cost, checked with mean-excess and
   QQ plots. Member expected excess above deductible d = P(cost > $25k) × GPD stop-loss at d − $25k.
6. **Pricing.** Per group: expected claims, expected specific (deductible by size band), aggregate
   attachment at 125% of expected net claims, expected aggregate excess by Monte Carlo from the
   fitted Tweedie, 15% load. Priced vs actual loss ratio by size band.
7. **Runout.** Monthly chain-ladder completion factors and IBNR at two valuation dates, against
   the actual ultimate.
8. **Explainability.** TreeSHAP for the LightGBM cost and claimant models; per-group top three
   drivers in plain language.

Every interval is a 95% bootstrap that resamples members (member metrics) or groups (group
metrics), never rows.

## Results (synthetic mode)
25,000 generated members · 11,104 test members in 44 groups. Full tables:
[`docs/synthetic/results.md`](docs/synthetic/results.md).

| Member next-year cost (test) | MAE | Gini | Predicted / actual |
|---|---|---|---|
| Tweedie GLM | $5,088 [4,895–5,288] | 0.504 [0.456–0.545] | 1.16 [1.13–1.20] |
| Tweedie LightGBM | $4,851 [4,646–5,052] | 0.526 [0.485–0.559] | 1.08 [1.05–1.11] |
| LightGBM − GLM | −$237 [−292 to −179] | +0.022 [0.009–0.039] | |

| High-cost claimants (test, LightGBM) | Claimants | AUC | Top-decile lift |
|---|---|---|---|
| > $25,000 | 467 | 0.80 [0.78–0.83] | 4.9× |
| > $50,000 | 265 | 0.83 [0.79–0.86] | 5.9× |
| > $100,000 | 24 | 0.39 [0.27–0.49] | 1.2× |

| Pricing by group size (test) | Groups | Priced LR | Actual LR | Claims A/E | Specific A/E |
|---|---|---|---|---|---|
| 50–99 | 13 | 0.845 | 0.863 [0.735–1.001] | 1.02 [0.87–1.19] | 1.22 [0.60–2.13] |
| 100–249 | 21 | 0.859 | 0.776 [0.736–0.821] | 0.90 [0.86–0.96] | 0.72 [0.51–0.96] |
| 250–499 | 7 | 0.868 | 0.854 [0.805–0.906] | 0.98 [0.93–1.04] | 0.91 [0.54–1.23] |
| 500+ | 3 | 0.870 | 0.78 | 0.89–0.91 | 0.24–0.50 |
| All | 44 | 0.864 | 0.803 [0.778–0.837] | 0.93 [0.90–0.97] | 0.81 [0.60–1.05] |

Other checks: GPD shape ξ = 0.24 above $25k; actual / expected excess 0.92 [0.80–1.04] above $25k
and 0.77 [0.59–0.95] above $50k. IBNR error −10.3% (valued 2009-12-31) and −1.4% (2010-12-31).
dbt mart vs Kedro features: all 22,233 rows and 33 columns match
([reconciliation](docs/synthetic/reconciliation.md)). Full synthetic run: ~43 s on 4 cores.

**Reading the synthetic numbers.**
- The 2008 → 2009 trend estimate (1.145) overshoots the generator's 2009 → 2010 change, so 2010
  is overpriced by ~7% (claims A/E 0.93). Trend from one year of history picks up the cohort's
  chronic-condition build-up as well as price inflation.
- LightGBM beats the GLM on MAE and Gini, with both intervals clear of zero. Generated cost isn't
  log-linear in these features (frailty is hidden, specialty drugs switch on), so this says nothing
  yet about DE-SynPUF.
- The $100k model is noise: 24 test claimants.
- The Tweedie Monte Carlo expects 5.2 aggregate hits and none happened. With the dispersion
  estimated on uncapped cost, simulated group totals are too wide.
- The 50–99 band's actual loss-ratio interval is about 2.6× the width of the 250–499 band's: small
  groups are where pricing error concentrates.

## Run it
Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dbt --extra drift

# Offline synthetic mode (generate DE-SynPUF-shaped files, then run everything): ~45 s
uv run kedro run --env synthetic --pipeline synthetic
uv run kedro run --env synthetic
uv run kedro run --env synthetic --pipeline warehouse   # dbt build + reconciliation

# Real data: DE-SynPUF Sample 2 into data/real/01_raw, then the same pipelines
uv run python -m group_underwriting.download            # or unzip the CSVs there by hand
uv run kedro run
uv run kedro run --pipeline warehouse

uv run pytest
```

Outputs: `data/<real|synthetic>/` (parquet tables and models, git-ignored),
`docs/results.md` or `docs/synthetic/results.md` with figures, MLflow runs and the registered cost
model in `mlflow.db` (real-data runs; `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`),
an Evidently drift report in `data/real/08_reporting/drift_report.html`.

Pipelines (`src/group_underwriting/pipelines/`): `ingest` → `features` → `models` → `tail` →
`pricing` → `reporting`, plus `runout` (IBNR), `synthetic` (data generator) and `warehouse` (dbt +
reconciliation). Parameters: `conf/base/parameters.yml`; synthetic overrides in `conf/synthetic/`.

## Snowflake
`dbt/profiles.yml` has a `snowflake` target (key-pair auth, settings from `SNOWFLAKE_*`
environment variables) and the models use portable macros for dates and regex. Loading RAW/KEDRO
tables into Snowflake and the Snowflake-vs-DuckDB reconciliation are not built yet.

## Limits
- **Synthetic numbers only** until the real-data run. The generator's structure decides what the
  models can find.
- **DE-SynPUF itself is synthetic.** CMS warns it does not preserve relationships between
  variables, so year-over-year signal may be weak. Pre-registered Test 0 decides whether to move
  to Synthea.
- **Medicare population.** 65+ and disabled beneficiaries, Medicare fee schedules, no commercial
  network discounts. Group PMPMs are Medicare-level, not employer-level.
- **Groups are constructed.** No real employer, industry or plan design. Group-level correlation
  comes only from geography.
- **Paid dates are simulated**, so the runout cutoff and IBNR results test the method, not CMS
  payment patterns.
- **No plan design.** Allowed cost, no deductibles or coinsurance of an employer plan, no
  lasering, no run-in/run-out contract terms.

## Repo layout
```
conf/            Kedro config: base (real data), synthetic, local (git-ignored)
src/             Kedro pipelines: ingest, features, models, tail, pricing, reporting, runout,
                 synthetic, warehouse; metrics.py; download.py
dbt/             staging and feature-mart models (DuckDB, Snowflake target)
docs/            decisions.md, preregistration.md, results (synthetic/ for now)
notebooks/       exploration only
tests/
```

## To do
- [ ] Real DE-SynPUF Sample 2 run and pre-registered tests 0–5
- [ ] Snowflake load and Snowflake-vs-DuckDB reconciliation
- [ ] Blog post for roncom.github.io after the real-data run

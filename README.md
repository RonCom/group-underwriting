# Group underwriting and stop-loss pricing on Medicare claims

Predicts next-year medical and pharmacy cost for members of employer groups, the probability that
a member crosses a stop-loss specific deductible, the tail of large claims above it, and the
resulting specific and aggregate stop-loss cost per group, then compares those prices with what
actually happened the following year. Built as Kedro pipelines on CMS DE-SynPUF claims, with a dbt
feature mart reconciled row for row against the Python features.

> **Status:** run on DE-SynPUF Sample 2 (116k beneficiaries, 11.2M claims) against tests
> pre-registered before any data was loaded. 6 of 13 predictions hit. Ranking works (test Gini
> 0.54, high-cost AUC 0.71–0.74), but **2010 cost-level checks fail** because DE-SynPUF's 2010
> claims are 30–40% thinner than 2009's, a drop in the data that nothing at the pricing date
> predicts. Scorecard: [`docs/scorecard.md`](docs/scorecard.md).

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

## Results (DE-SynPUF Sample 2)
Training: 35,996 members, 2008 features → 2009 cost. Test: 32,833 other members in 101 groups,
2009 features → 2010 cost. Full tables and figures: [`docs/results.md`](docs/results.md).

| Member next-year cost (test) | MAE | Gini | Predicted / actual |
|---|---|---|---|
| **Tweedie GLM (model of record)** | $4,980 [4,912–5,044] | 0.540 [0.525–0.555] | 1.72 [1.69–1.75] |
| Tweedie LightGBM | $4,960 [4,888–5,022] | 0.552 [0.538–0.566] | 1.73 [1.70–1.76] |
| LightGBM − GLM | −$20 [−40 to +0.3] | +0.012 [0.009–0.015] | |

| High-cost claimants (test) | Claimants | Logistic AUC | LightGBM AUC | Difference | Top-decile lift |
|---|---|---|---|---|---|
| > $25,000 | 627 | 0.739 [0.721–0.759] | 0.740 [0.722–0.761] | +0.001 [−0.004–0.008] | 3.5× |
| > $50,000 | 118 | 0.711 [0.659–0.759] | 0.718 [0.666–0.765] | +0.007 [−0.011–0.025] | 3.5× |
| > $100,000 | 10 | 0.615 | 0.583 | not tested (10 claimants) | |

| Pricing by group size (test, GLM) | Groups | Priced LR | Actual LR | Claims A/E | Specific A/E |
|---|---|---|---|---|---|
| 50–99 | 28 | 0.868 | 0.542 [0.509–0.586] | 0.62 [0.59–0.67] | 0.53 [0.35–0.74] |
| 100–249 | 37 | 0.869 | 0.526 [0.504–0.551] | 0.61 [0.58–0.63] | 0.26 [0.12–0.45] |
| 250–499 | 23 | 0.870 | 0.486 [0.472–0.501] | 0.56 [0.54–0.58] | 0.24 [0.16–0.33] |
| 500–999 | 8 | 0.870 | 0.518 [0.508–0.526] | 0.60 [0.58–0.60] | 0.16 [0.00–0.38] |
| 1,000–2,500 | 5 | 0.870 | 0.494 [0.486–0.500] | 0.57 [0.56–0.58] | 0.00 |
| All | 101 | 0.869 | 0.505 [0.498–0.514] | 0.58 [0.57–0.59] | 0.32 [0.23–0.41] |

Other checks: GPD shape ξ = 0.107 above $25k (KS p = 0.30). IBNR error +11.2% (valued
2009-12-31) and +20.9% (2010-12-31). dbt mart vs Kedro features: all 68,829 rows and 33 columns
match ([reconciliation](docs/reconciliation.md)). Full real-data run: ~4 minutes on 4 cores.

**Findings**
- **There is signal in DE-SynPUF.** Prior-year cost alone ranks next-year cost with Gini 0.64 on
  2008 → 2009; the models reach 0.69–0.71. The pre-registration expected 0.10–0.35, so the Synthea
  fallback isn't needed.
- **LightGBM doesn't earn adoption.** It ranks slightly better (+0.012 Gini, interval above 0),
  but its MAE gain crosses zero and its claimant AUC gains are within noise. The GLM and logistic
  baselines stay, per the pre-registered rule.
- **2010 levels are not usable for pricing tests.** Allowed cost per member-month falls 30–41% from
  2009 to 2010 in every claim type, with claim counts falling the same way. Priced on 2009 levels
  (trend 0.985), every band shows actual / expected near 0.6 and specific A/E near 0.3. These are
  misses against the pre-registration, and they measure the data's 2010 drop, not the method.
- **Small groups carry the most pricing noise.** The 50–99 band's actual loss-ratio interval is 4.3×
  the width of the 500–999 band's and 5.5× the 1,000+ band's.
- **Utilization drives the cost model.** Professional (carrier) claim count, second-half cost and
  total prior cost are the top SHAP drivers; group explanations read like "professional claims
  22.0 vs 17.7 per member (raises cost 15%)".

The synthetic mode (generated data, used for CI) has its own results in
[`docs/synthetic/results.md`](docs/synthetic/results.md); a full synthetic run takes ~45 s.

## Run it
Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dbt --extra drift

# Offline synthetic mode (generate DE-SynPUF-shaped files, then run everything): ~45 s
uv run kedro run --env synthetic --pipeline synthetic
uv run kedro run --env synthetic
uv run kedro run --env synthetic --pipeline warehouse   # dbt build + reconciliation

# Real data: DE-SynPUF Sample 2 into data/real/01_raw (3 GB), then the same pipelines
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
- **2010 is thin in DE-SynPUF.** Claims per member-month drop 30–40% from 2009, so the
  out-of-time test year can't check price levels. Ranking results stand.
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
docs/            decisions.md, preregistration.md, scorecard.md, results.md; synthetic/
notebooks/       exploration only
tests/
```

## To do
- [x] Real DE-SynPUF Sample 2 run and pre-registered tests 0–5 ([scorecard](docs/scorecard.md))
- [ ] Follow-up (new pre-registration): a level check that doesn't depend on 2010 volume, e.g.
      2008 → 2009 out-of-time on held-out members, or recalibrating to 2010's observed level
- [ ] Snowflake load and Snowflake-vs-DuckDB reconciliation
- [ ] Blog post for roncom.github.io after the real-data run

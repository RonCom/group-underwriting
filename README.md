# Group underwriting and stop-loss pricing on Medicare claims

[![CI](https://github.com/RonCom/group-underwriting/actions/workflows/ci.yml/badge.svg)](https://github.com/RonCom/group-underwriting/actions/workflows/ci.yml)

**Write-up:** [Pricing stop-loss for employer groups from claims data](https://roncom.github.io/blog/group-underwriting/): the design choices, what the first test got wrong, and five pre-registered rounds of results.

Predicts next-year medical and pharmacy cost for members of employer groups, the probability that
a member crosses a stop-loss specific deductible, the tail of large claims above it, and the
resulting specific and aggregate stop-loss cost per group, then compares those prices with what
actually happened the following year. Built as Kedro pipelines on CMS DE-SynPUF claims, with a dbt
feature mart reconciled row for row against the Python features.

> **Status:** five pre-registered rounds on DE-SynPUF Samples 2–6 (scorecard:
> [`docs/scorecard.md`](docs/scorecard.md)). Model of record: recalibrated LightGBM cost, logistic
> claimant model, Pareto tail spliced at $100k, and group totals simulated by resampling
> actual-to-predicted ratios. On samples no model had seen, group claims come in at 0.995–1.001 of
> expected. The original out-of-time year, 2010, can't check price levels: DE-SynPUF's 2010
> claims are 30–40% thinner than 2009's.

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
   Adopted after the Sample 4 re-test: a second GPD above $100k (spliced tail).
6. **Pricing.** Per group: expected claims, expected specific (deductible by size band), aggregate
   attachment at 125% of expected net claims, expected aggregate excess by Monte Carlo from the
   fitted Tweedie, 15% load. Priced vs actual loss ratio by size band, for each model
   configuration in `pricing_variants` (frozen baseline, earlier record, current model of record).
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
| Tweedie GLM (frozen baseline) | $4,980 [4,912–5,044] | 0.540 [0.525–0.555] | 1.72 [1.69–1.75] |
| Tweedie LightGBM (model of record after the Sample 4 re-test) | $4,960 [4,888–5,022] | 0.552 [0.538–0.566] | 1.73 [1.70–1.76] |
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
2009-12-31) and +20.9% (2010-12-31) with one triangle; +8.6% and −1.1% with triangles by claim
type. dbt mart vs Kedro features: all 68,829 rows and 33 columns
match ([reconciliation](docs/reconciliation.md)). Full real-data run: ~4 minutes on 4 cores.

**Findings**
- **There is signal in DE-SynPUF.** Prior-year cost alone ranks next-year cost with Gini 0.64 on
  2008 → 2009; the models reach 0.69–0.71. The pre-registration expected 0.10–0.35, so the Synthea
  fallback isn't needed.
- **LightGBM doesn't earn adoption on Sample 2** (reversed by the Sample 4 re-test below). It ranks slightly better (+0.012 Gini, interval above 0),
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

### Follow-up: independent sample, complete years (DE-SynPUF Sample 3)
Frozen Sample 2 models, Sample 3's 72,271 members (none in Sample 2) in 207 groups, 2008 features
→ 2009 cost. 10 of 12 pre-registered predictions hit. Tables:
[`docs/followup/results.md`](docs/followup/results.md).

| Pricing by group size (Sample 3, GLM) | Groups | Priced LR | Actual LR | Claims A/E | Specific A/E |
|---|---|---|---|---|---|
| 50–99 | 52 | 0.868 | 0.849 [0.816–0.882] | 0.98 [0.94–1.02] | 0.84 [0.71–0.98] |
| 100–249 | 72 | 0.869 | 0.879 [0.863–0.896] | 1.01 [0.99–1.03] | 1.02 [0.86–1.20] |
| 250–499 | 47 | 0.870 | 0.865 [0.847–0.881] | 1.00 [0.97–1.01] | 1.06 [0.90–1.22] |
| 500–999 | 26 | 0.870 | 0.863 [0.847–0.877] | 0.99 [0.97–1.01] | 0.73 [0.40–1.08] |
| 1,000–2,500 | 10 | 0.870 | 0.862 [0.850–0.873] | 0.99 [0.98–1.00] | 0.39 [0.13–0.63] |
| All | 207 | 0.869 | 0.865 [0.858–0.873] | 1.00 [0.99–1.00] | 0.94 [0.85–1.03] |

- **Calibrated where the data is complete.** Member predicted / actual 1.005, excess loss A/E 0.98
  above $25k and 0.97 above $50k, 2 aggregate breaches against 2.8 expected.
- **Ranking holds.** Member Gini 0.70; claimant AUC 0.82 ($25k), 0.85 ($50k), 0.91 ($100k, 75
  claimants); expected vs actual group PMPM Spearman 0.70 [0.60–0.76].
- **The far tail is overpriced.** Above $100k actual excess is 0.59 [0.42–0.77] of expected (not
  pre-registered): one GPD above $25k is too heavy that far out.
- **LightGBM looks better here** (MAE −$239, Gini +0.011, both intervals clear of zero), but the
  adoption rule was spent on Sample 2; the pre-registered re-test on Sample 4 (below) decided it.
- **2010 relative pricing misses** after removing the overall drop: 50–99 groups run 7% above
  expected, 250–499 groups 4% below.

### Re-test: LightGBM and a spliced tail (DE-SynPUF Sample 4)
Frozen Sample 2 models on Sample 4 (72,197 members, none in Samples 2 or 3, 205 groups). 8 of 9
pre-registered predictions hit. Tables: [`docs/retest/results.md`](docs/retest/results.md).

| Excess loss above attachment (Sample 4) | Claimants | Single GPD A/E | Spliced A/E |
|---|---|---|---|
| $25,000 | 3,682 | 1.00 [0.96–1.05] | 1.01 [0.97–1.05] |
| $50,000 | 937 | 0.98 [0.90–1.06] | 1.01 [0.92–1.10] |
| $100,000 | 88 | 0.78 [0.61–0.99] | 1.02 [0.80–1.29] |

- **LightGBM adopted for cost.** Its gains replicate on a second unseen sample: Gini +0.012
  [0.010–0.014], MAE −$222 [−237 to −208]. It runs about 2% low on level (group claims A/E 1.02
  [1.01–1.03] vs the GLM's 1.00), so recalibrating its level is the next challenger.
- **Logistic stays for claimants.** LightGBM's AUC gain at $50k isn't clear of zero.
- **Spliced tail adopted.** Above $100k the cost distribution has a bounded tail (ξ₂ = −0.09), so
  one GPD from $25k overstated far-tail losses. Splicing a second GPD at $100k brings expected
  excess in line at all three attachments.
- **The level result replicates:** GLM group claims A/E 1.00 [0.99–1.01], specific A/E 1.00
  [0.89–1.11], 2 aggregate breaches against 2.4 expected.

### Holdout: the model of record on Sample 5
Frozen models, tails and LightGBM level factor (1.018, from Samples 3–4) on Sample 5: 72,116
members in none of the earlier samples, 205 groups. 6 of 7 pre-registered predictions hit.
Tables: [`docs/holdout/results.md`](docs/holdout/results.md).

| Configuration (Sample 5) | Member predicted / actual | Group claims A/E | Specific A/E | Aggregate breaches (expected) |
|---|---|---|---|---|
| Baseline: GLM, logistic, single GPD | 1.002 [0.993–1.011] | 1.00 [0.99–1.01] | 0.87 [0.76–0.98] | 0 (2.4) |
| LightGBM, logistic, spliced tail | 0.984 [0.976–0.992] | 1.02 [1.01–1.03] | 0.91 [0.80–1.02] | 0 (2.9) |
| **Recalibrated LightGBM, logistic, spliced tail (model of record)** | 1.002 [0.993–1.010] | 1.00 [0.99–1.01] | 0.91 [0.80–1.02] | 0 (2.8) |

- **Recalibration adopted.** One factor from earlier samples fixes LightGBM's 2% low level on a
  new sample while keeping its better ranking (Gini 0.711 vs the GLM's 0.699).
- **The spliced tail holds up a second time:** excess A/E above $100k 0.88 [0.60–1.16], against
  0.68 [0.46–0.89] for the single GPD.
- **Aggregate stop-loss may be priced a little high.** Breaches came in at or below expectation in
  all three complete-year runs (pooled 4 observed vs 7.6 expected, Poisson P(≤ 4) = 0.12).
- **Miss:** the 250–499 band runs 2% below expected (0.98 [0.963–0.994]) with every configuration.

### Aggregate layer: the simulated spread (DE-SynPUF Sample 6)
Aggregate breaches came in below expectation on Samples 3–5, so the simulation of group net
claims became a pre-registered test on Sample 6 (72,216 members, 206 groups). 5 of 5 predictions
hit. Tables: [`docs/aggtest/results.md`](docs/aggtest/results.md).

| Member-cost simulation | PIT variance (uniform = 0.0833) | Mean squared z (target 1) | Breaches (expected) | Expected aggregate cost PMPM |
|---|---|---|---|---|
| Tweedie, dispersion from uncapped cost | 0.060 [0.052–0.067] | 0.58 [0.48–0.71] | 0 (3.1) | $0.109 |
| **Resampled actual / predicted ratios (adopted)** | 0.083 [0.072–0.091] | 0.95 [0.79–1.14] | 0 (1.0) | $0.024 |

PIT value: the share of a group's simulated net claims below its actual net claims; uniform PIT
values mean the simulated distribution has the right spread. The Tweedie spread was about 1.3×
too wide, which overpriced the aggregate layer about 4.5×. Group claims A/E is unchanged (1.001).

### Credibility: does a group's own experience add anything? (DE-SynPUF Sample 7)
Underwriters blend a manual rate with a group's own claims history, weighted by credibility
Z = n / (n + k). Constants were fitted on Samples 3–6 and tested on Sample 7 (72,309 members, 207
groups); 4 of 4 pre-registered predictions hit. Table: [`docs/credibility/results.md`](docs/credibility/results.md).

| Manual rate | k (member-months) | Median Z | Group PMPM MAE, manual | Blended | Change |
|---|---|---|---|---|---|
| Model of record (member claims model) | 293,317 | 0.008 | $28.09 | $27.97 | −0.4% [−1.5% to +0.6%] |
| Demographic (age band × sex) | 3,409 | 0.395 | $53.07 | $34.65 | −34.7% [−44.6% to −22.5%] |

The claims model already uses every member's prior-year cost, so group experience earns under 1%
weight and isn't adopted. Against a demographic rate it earns about 40% and cuts error by a third,
which still leaves it $6.55 PMPM worse than the claims model alone.

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

# Follow-up: frozen models on Sample 3 (download it to data/sample3/01_raw first)
uv run python -m group_underwriting.download --sample 3 --dest data/sample3/01_raw
uv run kedro run --env followup --pipeline followup

# Re-test: Sample 4 (upper tail fit uses Sample 2 training + Sample 3)
uv run python -m group_underwriting.download --sample 4 --dest data/sample4/01_raw
uv run kedro run --env retest --pipeline retest

# Holdout: Sample 5 (needs the Sample 3 and 4 runs for the level factor and disjointness check)
uv run python -m group_underwriting.download --sample 5 --dest data/sample5/01_raw
uv run kedro run --env holdout --pipeline holdout

# Aggregate-layer test: Sample 6 (pool of seen ratios from Samples 3-5)
uv run python -m group_underwriting.download --sample 6 --dest data/sample6/01_raw
uv run kedro run --env aggtest --pipeline aggtest

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
The same dbt models build in Snowflake, and a reconciliation compares Snowflake's
`MART.MEMBER_FEATURES` with DuckDB's on every row and column.

```
data/real/01_raw/*.csv  --PUT/COPY-->  RAW.*        (all text, plus FILENAME)
Kedro claims, groups    --PUT/COPY-->  KEDRO.*      (simulated paid dates, cohort rows)
dbt build --target snowflake  -->  STG.*, MART.MEMBER_FEATURES  -->  compare with DuckDB
```

One-time setup: generate a key pair locally, paste the public key into
[`snowflake/setup.sql`](snowflake/setup.sql) and run it in Snowsight as ACCOUNTADMIN. Then set
`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER` (`GU_SVC`) and `SNOWFLAKE_PRIVATE_KEY` (PEM text) or
`SNOWFLAKE_PRIVATE_KEY_PATH` as environment variables, and run:

```bash
uv sync --extra dbt --extra snowflake
uv run kedro run --pipeline warehouse     # DuckDB build first
uv run kedro run --pipeline snowflake     # load, dbt build on Snowflake, reconcile
```

Output: [`docs/reconciliation_snowflake.md`](docs/reconciliation_snowflake.md). Latest run (Sample 2): all 68,829 member-years and 33 feature columns match DuckDB; 7/7 dbt models and tests pass in both targets. The only differences are in `age` (≤ 5×10⁻⁷, Snowflake rounds division to 6 decimals).

## Limits
- **2010 is thin in DE-SynPUF.** Claims per member-month drop 30–40% from 2009, so the
  out-of-time test year can't check price levels. Ranking results stand.
- **DE-SynPUF itself is synthetic.** CMS warns it does not preserve relationships between
  variables, so year-over-year signal may be weak. Pre-registered Test 0 decides whether to move
  to Synthea.
- **Medicare population.** 65+ and disabled beneficiaries (the 15% under 65 price correctly on their own: group claims A/E 0.998 [0.986–1.008], `docs/under65/results.md`), Medicare fee schedules, no commercial
  network discounts. Group PMPMs are Medicare-level, not employer-level.
- **Groups are constructed.** No real employer, industry or plan design. Group-level correlation
  comes only from geography.
- **Paid dates are simulated**, so the runout cutoff and IBNR results test the method, not CMS
  payment patterns.
- **No plan design.** Allowed cost, no deductibles or coinsurance of an employer plan, no
  lasering, no run-in/run-out contract terms.

## Repo layout
```
conf/            Kedro config: base (real data), synthetic, followup, retest, holdout, aggtest, local (git-ignored)
src/             Kedro pipelines: ingest, features, models, tail, pricing, reporting, runout,
                 synthetic, warehouse, followup, retest, holdout, snowflake, aggtest; metrics.py; download.py
dbt/             staging and feature-mart models (DuckDB, Snowflake target)
docs/            decisions.md, preregistration.md, scorecard.md, results.md; synthetic/
notebooks/       exploration only
tests/
```

## To do
- [x] Real DE-SynPUF Sample 2 run and pre-registered tests 0–5 ([scorecard](docs/scorecard.md))
- [x] Pre-registered follow-up on Sample 3 and 2010 relative pricing
- [x] Pre-registered LightGBM re-test and spliced tail on Sample 4
- [x] Wire the adopted models into the main pricing pipeline (`pricing_variants`)
- [x] Pre-registered LightGBM level recalibration, tested on Sample 5
- [x] Snowflake load, dbt build and Snowflake-vs-DuckDB reconciliation
- [x] Pre-registered aggregate-layer simulation test on Sample 6; empirical ratios adopted
- [x] Blog post published: [Pricing stop-loss for employer groups from claims data](https://roncom.github.io/blog/group-underwriting/)
- [x] Credibility blending of group experience, pre-registered on Sample 7: not adopted (−0.4% change in group pricing error)
- [x] Under-65 subgroup check (Samples 3–6, 44,605 members): 6 of 6 pre-registered predictions hit; group claims A/E 0.998 [0.986–1.008]
- [ ] Working-age population (Synthea): deferred; Synthea's costs come from lookup tables, so it would test the code more than the pricing
- [x] The 250–499 band miss: doesn't recur on Samples 3, 4 or 6 (pooled A/E 0.995 [0.987–1.004]); treated as chance
- [x] IBNR by claim type, pre-registered on Sample 6: better than one triangle (+15.7% vs +24.5% at 2010-12-31) but missed the ±10% bar; not adopted. An upward bias remains in both
- [ ] Drop "distinct drugs" (duplicates "fills" in DE-SynPUF)
- [ ] Run the manual "Snowflake" workflow (`.github/workflows/snowflake.yml`): needs the CI database lines at the end of `snowflake/setup.sql` and repository secrets `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY`

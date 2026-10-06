# Decisions

Dated log of choices that change what the numbers mean. Newest last.

## 2026-10-05: initial build

**Data source.** CMS DE-SynPUF Sample 1 (changed to Sample 2 below) (Beneficiary Summary 2008–2010, Inpatient, Outpatient,
Carrier A/B, Prescription Drug Events). The CMS download hosts were blocked from the environment
the project was built in, so the first build runs only on generated data (`--env synthetic`). The
Synthea fallback in the project brief is triggered by the pre-registered signal check
(`docs/preregistration.md`, Test 0), not yet run.

**Allowed cost.** DE-SynPUF facility claims carry payments, not allowed amounts. Allowed is rebuilt
as Medicare payment + primary-payer payment + beneficiary deductible + coinsurance + blood
deductible (inpatient: Part A fields; outpatient: Part B fields). Carrier: sum of the 13
`LINE_ALOWD_CHRG_AMT` columns. Part D: `TOT_RX_CST_AMT`. Negative amounts are floored at 0.
Inpatient claim segments are summed per `CLM_ID`.

**Paid dates are simulated.** DE-SynPUF has no paid date. Each claim gets
paid = service end + lag, lag = minimum + Gamma(shape, mean/shape) by claim type, plus a uniform
late-payment tail for a small share (`paid_lag` in `conf/base/parameters.yml`). Consequences: the
runout cutoff in the features and the IBNR test use a lag pattern we chose, so the IBNR results
check the code path and the chain-ladder method, not real Medicare payment speed.

**Eligibility.** A (member, year Y) row needs the member in the summary files for Y and Y+1, zero
HMO months in both (HMO members have no fee-for-service claims) and at least one month of Parts A
and B in Y+1. Members without Part D stay in; `months_d` is a feature.

**Out-of-time split.** Members are split 50/50 by a salted hash of `DESYNPUF_ID`. Training rows:
training members, features 2008 → cost 2009. Test rows: test members, features 2009 → cost 2010.
No member and no group appears in both. Within training, 20% of members (second hash) form an
inner validation set for LightGBM early stopping, the Tweedie dispersion estimate and the signal
check; both cost models are fit on the remaining 80%, so they see the same data.

**Target and exposure.** Cost models predict annualized cost (next-year allowed / exposure,
exposure = months of A and B in Y+1 / 12) with exposure as the sample weight, Tweedie power 1.5.
High-cost-claimant labels use raw annual cost (stop-loss attaches to the contract year, not an
annualized rate).

**Features exclude race.** `BENE_RACE_CD` is loaded but not used for pricing. State and county
only drive group assignment.

**Runout in features.** Features as of Y-12-31 use claims incurred in Y and paid by the cutoff +
3 months, the same rule in training and test.

**Trend.** The models learn the cost level of their training target year (2009). Test predictions
for 2010 are multiplied by the 2008 → 2009 PMPM ratio over all fee-for-service member-months, both
years measured at the same 3-month runout (data available at the 2009 cutoff + 3 months).

**Employer groups.** Within each split, members are sorted by state, county and a hash, then cut
into consecutive blocks with sizes drawn from bands 50–99 / 100–249 / 250–499 / 500–999 /
1000–2500 (weights in `groups.size_bands`). Groups are therefore geographically local, like real
employers, but their members are Medicare beneficiaries (65+ or disabled), an age-skewed proxy for
an employer population. A leftover block smaller than 50 is merged into the previous group.
The synthetic environment uses more small groups so its smaller test cohort still has ~45 groups.

**Tail.** GPD fit to training members' 2009 annual cost above $25,000 (also the lowest attachment
point, chosen from the mean-excess plot). A member's expected loss above deductible d is
P(X > $25k) from the LightGBM HCC model × the GPD stop-loss transform at d − $25k. This links the
member-level classifier to the portfolio tail; it assumes the excess distribution above $25k is
the same for every member.

**Pricing.** Specific deductible by size band (25k for 50–99, 50k for 100–499, 100k for 500+).
Aggregate attachment = 125% of expected claims net of specific. Expected aggregate excess by
Monte Carlo: members drawn from the fitted Tweedie (compound Poisson–gamma), capped at the
specific deductible, summed per group and rescaled to the expected net claims. Premium = expected
net + specific + aggregate, loaded 15%. Priced loss ratio = expected claims / premium; actual loss
ratio = actual claims / premium.

**IBNR.** Chain ladder on monthly paid triangles (24 incurred months × 24 lag months) at
valuations 2009-12-31 and 2010-12-31, volume-weighted age-to-age factors, compared with the
actual ultimate known from the simulated paid dates.

**Warehouse.** dbt reads the raw CSVs (DuckDB `read_csv`) and two Kedro outputs it cannot rebuild
in SQL: simulated paid dates and the cohort/group assignment. The feature mart is then compared
with the Kedro features on every row and column (`kedro run --pipeline warehouse`). The Snowflake
target is configured in `dbt/profiles.yml` but not yet run (no account in this environment).

**Tracking.** MLflow with a local SQLite store (`mlflow.db`, git-ignored) and the model registry;
off in synthetic mode. Drift between scoring years: PSI per feature always; an Evidently HTML
report on real-data runs (`drift` extra).

**Blog post.** Deferred until the real-data run: a write-up of synthetic results would describe
the generator, not DE-SynPUF.

## 2026-10-05: DE-SynPUF Sample 2 instead of Sample 1

CMS no longer hosts Sample 1's 2010 Beneficiary Summary file: the Sample 1 download page links to
`de1_0_2010_beneficiary_summary_file_sample_20.zip`, and every Sample 1 URL variant returns 404.
The 2010 file is required (test-year enrollment and exposure). Sample 2 has all eight files, so
the project uses Sample 2. Samples are random, equal-sized draws from the same synthesis, so the
pre-registered predictions are unchanged. No DE-SynPUF data had been loaded or analyzed when this
was decided (only the Sample 1 2008 and 2009 beneficiary files had been downloaded by the failed
download run; they were deleted unopened).

## 2026-10-05: reporting completed for the pre-registered rules (after the first real run)

The first real-data run showed the report lacked two things the pre-registration requires: the
LightGBM − GLM AUC difference (Test 2 rule) and pricing with the GLM when LightGBM isn't adopted
(Test 1 rule). Both were added; models, features, parameters and rules are unchanged, and the
saved models were reused. The tail's expected excess is now computed from both HCC models
(`tail.hcc_model` parameter removed).

The GLM remains the cost and claimant model of record (Test 1 and 2 rules). DE-SynPUF's 2010
claim volume is 30–40% below 2009 (`docs/scorecard.md`); no adjustment for it is made in the
frozen run.

## 2026-10-05: follow-up on Sample 3

DE-SynPUF has no years after 2010, so the level test uses another sample instead of more years:
the frozen Sample 2 models score Sample 3 (2008 → 2009) in the `followup` Kedro environment
(`kedro run --env followup --pipeline followup`), which reads models, the GPD fit and Sample 2
member IDs from `data/real` and fails if any member overlaps. Pre-registered in
`docs/preregistration_followup.md` before Sample 3 was downloaded.

## 2026-10-05: re-test on Sample 4, models of record changed

Pre-registered in `docs/preregistration_retest.md`, run in the `retest` Kedro environment (Sample 4
data, frozen Sample 2 models, upper tail fit on Sample 2 training + Sample 3). Outcome under the
pre-registered rules:
- **Cost model of record: LightGBM** (Gini and MAE differences both clear of zero). It runs ~2% low
  on level; recalibration is a separate future challenger.
- **Claimant model of record: logistic** (LightGBM's AUC gain at $50k isn't clear of zero).
- **Tail: spliced** (GPD above $25k up to $100k, second GPD above $100k).
The main `kedro run` still produces the original frozen Sample 2 outputs; the adopted tail lives
in the `retest` pipeline until it is wired into pricing.

## 2026-10-05: adopted models wired into the main pipeline

Main `kedro run` pricing now compares named configurations (`pricing_variants`): the frozen
baseline (GLM, logistic, single GPD), the model of record (LightGBM cost, logistic claimants,
spliced tail) and a challenger (model of record with LightGBM's level recalibrated). The upper GPD
is fit on this run's training members plus already-seen samples listed in
`upper_tail.extra_features`; with fewer than 30 costs above $100k it falls back to the single GPD.
The level factor per cost model is total actual / total predicted on already-seen samples scored
by the frozen models (`level_calibration.files`: Samples 3 and 4; LightGBM 1.018, GLM 0.999).
Retraining reproduces the frozen models exactly (same metrics to the dollar).

## 2026-10-05: holdout on Sample 5, recalibration adopted

Pre-registered in `docs/preregistration_holdout.md`, run in the `holdout` Kedro environment.
LightGBM's level factor (1.018, from Samples 3–4) is adopted: the model of record is now
recalibrated LightGBM cost, logistic claimants, spliced tail. `pricing_variants` keeps the frozen
baseline and the pre-Sample-5 record (`record_v1`) for comparison. The holdout results were
produced with the variant names in force before adoption (`record`, `recalibrated`).

## 2026-10-05: Snowflake build

Raw DE-SynPUF Sample 2 CSVs and the two Kedro inputs (simulated paid dates, cohort rows) were
loaded into Snowflake (`kedro run --pipeline snowflake`) and the dbt project built there. Two SQL
fixes were needed for Snowflake, both applied to the shared models: a CTE named `rows` (reserved in
Snowflake) became `cohort`, and a `SELECT r.member_id, ..., c.*` that duplicated `member_id` now
lists the claim columns. The DuckDB build was rerun after the fixes and still matches the Kedro
features; Snowflake matches DuckDB on every row and column.

## 2026-10-06: aggregate-layer simulation, empirical ratios adopted

Pre-registered in `docs/preregistration_aggregate.md` after a post-hoc diagnostic on Samples 3–5
(`scripts/aggregate_diagnostic.py`), run on Sample 6 in the `aggtest` environment. All five
predictions hit. The model of record now simulates member costs by resampling actual / predicted
ratios from Samples 3–5 within tenths of predicted cost (`residual_pool`). `pricing_variants`
keeps the earlier record as `record_v2` (Tweedie simulation). With no pool files present (fresh
clone, synthetic mode), empirical variants fall back to Tweedie with a warning.

## 2026-10-06: IBNR by claim type tested, not adopted

Pre-registered in `docs/preregistration_ibnr.md` and run on Sample 6. By-claim-type triangles beat
the single triangle at both valuations but missed the ±10% bar at 2010-12-31 (+15.7%), so the
single triangle stays the method of record. Reports now show both methods (`ibnr.methods`).
The 250–499 band miss on Sample 5 was checked post hoc across Samples 3–6 and treated as chance.

# PROJECT.md — group-underwriting

## Purpose
Portfolio project for a Lead Data Scientist application at ParetoHealth (a benefits captive that funds employer health plans with stop-loss). It shows predictive underwriting and pricing on claims and pharmacy data. A companion project, `RonCom/medicare-fwa`, already covers XGBoost, calibration, out-of-time validation, explainability and optimization. Don't rebuild those; this repo covers what that one doesn't:

- Member-level medical and pharmacy claims
- Employer-group PMPM cost prediction
- High-cost claimant (HCC) probability and stop-loss tail modeling
- Claims maturity / runout (IBNR)
- Kedro pipelines

## Data
- **Primary:** CMS DE-SynPUF, one sample to start. Use these tables: Beneficiary Summary (2008–2010), Inpatient, Outpatient, Carrier, and Prescription Drug Events.
- **Known limit:** DE-SynPUF is synthetic, and CMS warns it doesn't preserve relationships between variables, so predictive signal may be weak. Measure this early with a baseline-vs-model check on 2008→2009. If the signal is near zero, switch to Synthea (already used in `care-outreach`) and record the switch in `docs/decisions.md`.
- **Employer groups:** synthetic groups built by assigning beneficiaries to groups of varying size. Document the rule. Medicare members are 65+, so the groups are an age-skewed proxy for an employer population. Say so in the README.

## Modeling scope
1. **Point-in-time features.** Build features as of a cutoff date from claims incurred before it. Simulate runout by dropping claims paid more than N months after the cutoff.
2. **Out-of-time validation.** Train on 2008 features to predict 2009 cost; test on 2009 features to predict 2010. No random splits, and no member in both train and test.
3. **Member and group cost.** Predict member-level next-year allowed cost with a Tweedie GBM (LightGBM or XGBoost) against a GLM baseline, then aggregate to group PMPM. Report MAE, predictive ratio by decile, and calibration.
4. **High-cost claimants.** Predict P(member cost > specific deductible) for several attachment points. Report AUC, PR-AUC, calibration, and top-decile lift.
5. **Tail.** Fit a generalized Pareto above a threshold; check with mean-excess and QQ plots. Estimate expected excess loss per member above each specific deductible.
6. **Pricing.** Compute expected specific and aggregate stop-loss cost per group. Compare the priced loss ratio to the actual loss ratio by group-size band.
7. **Explainability.** SHAP for the GBMs, plus the top drivers per group in plain language.

## Methods conventions (same as medicare-fwa)
- Write predictions and adoption rules in `docs/preregistration.md` before running each test. Report every miss.
- Report bootstrap intervals that resample members (or groups), not rows.
- Test challengers against a frozen baseline, one change at a time.

## Stack
- Python with `uv` (no Anaconda)
- Kedro for pipelines
- DuckDB locally first, then Snowflake via dbt; reconcile the two row for row
- MLflow for tracking and the model registry; Evidently for drift reports between scoring years
- pytest, plus GitHub Actions CI
- A synthetic-data mode that runs the full pipeline offline in under a minute

## Repo layout
```
conf/            Kedro config (base, local)
src/             Kedro pipelines: ingest, features, models, tail, pricing, reporting
dbt/             staging and feature-mart models
docs/            decisions.md, preregistration.md, results.md
notebooks/       exploration only; nothing the pipeline depends on
tests/
```

## Git
- Commits are authored by Chris only: no AI co-author lines or tool attribution in commits, PRs or files.
- Write commit messages in the imperative, one change per commit.

## Output
- A README with results tables and intervals, plus a limits section (synthetic data, Medicare population, group construction).
- A blog post for roncom.github.io in the same style as the medicare-fwa write-up.

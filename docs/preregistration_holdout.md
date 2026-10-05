# Pre-registration: level recalibration and the model of record on Sample 5

Written 2026-10-05, after the Sample 4 re-test (`docs/scorecard.md`) and **before DE-SynPUF
Sample 5 was downloaded**. Sample 5 members are checked to be in none of Samples 2, 3 or 4.
Design as before: frozen Sample 2 models, 2008 features → 2009 cost, every eligible member in the
test cohort, groups by the same rule, trend = 1. Intervals: 95% bootstrap, 500 resamples of
members or groups. Every miss is reported.

Frozen inputs, all from already-seen data:
- LightGBM level factor **1.0180** (GLM 0.9990): total actual / total predicted on Samples 3 and 4
  (144,468 members), `data/real/07_model_output/level_calibration.parquet`.
- Upper GPD above $100k from the main run (Sample 2 training + Sample 3): ξ₂ = −0.088.
- Variants as in `conf/base/parameters.yml` (`pricing_variants`): baseline, record, recalibrated.

## H1: LightGBM level recalibration (one change against the model of record)

| # | Prediction |
|---|---|
| H1a | Uncalibrated LightGBM member predicted / actual: interval entirely below 1 |
| H1b | Recalibrated LightGBM member predicted / actual: interval covers 1 |
| H1c | Group claims A/E, all groups: model of record interval entirely above 1; recalibrated interval covers 1 |

Adoption rule: recalibration joins the model of record if H1b holds and the recalibrated group
claims A/E interval covers 1.

## H2: the model of record on unseen data

| # | Prediction |
|---|---|
| H2a | Specific stop-loss A/E (logistic claimants, spliced tail), all groups: interval covers 1 |
| H2b | Excess A/E above $100k with the spliced tail: interval covers 1 |
| H2c | Aggregate breaches (model of record) within the central 95% Poisson range of the expected count |
| H2d | No size band's group claims A/E interval excludes 1 for the recalibrated variant |

# Pre-registration: follow-up level and relative-pricing tests

Written 2026-10-05, after the Sample 2 run (`docs/scorecard.md`) and **before DE-SynPUF Sample 3
was downloaded**. The Sample 2 test can't check price levels because DE-SynPUF's 2010 claims are
30–40% thinner than 2009's. DE-SynPUF has no years after 2010 and no other free CMS claims source
covers later years, so more data here means more members (another sample).

Frozen: the Sample 2 models (`data/real/06_models/`), GPD fit, features, parameters and pricing
rules as of the commit adding this file. The GLM/logistic models stay the models of record
(Test 1–2 rules); LightGBM is reported alongside and no adoption rule is re-run. Every miss is
reported. Intervals: 95% bootstrap, 500 resamples of members or groups.

What I've already seen that informs these predictions: Sample 2 inner-validation Gini on
2008 → 2009 (GLM 0.69, LightGBM 0.71) and every number in `docs/results.md`.

## F1: independent population, complete years (Sample 3, 2008 features → 2009 cost)

All eligible Sample 3 members form one test cohort, cut into groups with the same rule and
parameters. No Sample 3 member is in Sample 2 (checked in the pipeline). Same period as training,
so trend = 1 by construction.

| # | Prediction |
|---|---|
| F1a | Member Gini (GLM) 0.62–0.74 |
| F1b | Member predicted / actual (GLM), overall, within 0.95–1.05 |
| F1c | High-cost AUC (logistic) 0.72–0.82 at $25k and 0.70–0.82 at $50k |
| F1d | Actual / expected excess above $25k and above $50k: intervals cover 1 |
| F1e | Group claims actual / expected, all groups: interval covers 1 and estimate within 0.95–1.05 |
| F1f | No size band's claims actual / expected interval excludes 1 |
| F1g | Specific stop-loss actual / expected, all groups: interval covers 1 |
| F1h | Number of groups breaching the aggregate attachment within the central 95% Poisson range of the expected count |
| F1i | 50–99 band's actual loss-ratio interval at least 2× as wide as each 500+ band's |
| F1j | Spearman correlation of expected vs actual group PMPM between 0.3 and 0.7, interval above 0 |

## F2: relative pricing on the Sample 2 2010 test

Expected claims are rescaled by one factor k = total actual / total expected (GLM), recomputed in
each bootstrap resample, so only relative pricing is tested.

| # | Prediction |
|---|---|
| F2a | Each size band's rescaled actual / expected interval covers 1 |
| F2b | Spearman correlation of expected vs actual group PMPM across the 101 groups between 0.2 and 0.6, interval above 0 |

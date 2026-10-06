# Pre-registration: under-65 members (Samples 3–6)

Written 2026-10-06, before any metric was computed for this subgroup. **Not a holdout:** every
member here is in Samples 3–6, which earlier rounds scored as whole samples; no result has been
broken out by age before. Medicare members under 65 qualify through disability or ESRD, so they're
sicker than an employer population; this checks whether pricing holds outside the 65+ core, not
whether it holds for workers.

Design: members aged under 65 at the cutoff, Samples 3–6 pooled, 2008 features → 2009 cost, scored
with the model of record (recalibrated LightGBM cost, logistic claimants, spliced tail, empirical
simulation). Groups are re-cut from these members only, with the same rule and size bands.
Intervals: 95% bootstrap, 500 resamples of members or groups.

| # | Prediction |
|---|---|
| U1 | Member predicted / actual within 0.95–1.05 |
| U2 | Member Gini at least 0.60 |
| U3 | Logistic AUC at least 0.75 at $25k and at $50k |
| U4 | Group claims A/E: interval covers 1 |
| U5 | Excess A/E above $25k and above $50k: intervals cover 1 |
| U6 | PIT variance of group net claims: interval covers 0.0833 |

No adoption rule: nothing changes in the model of record either way. Misses go in the scorecard
and the limits sections of the README and blog.

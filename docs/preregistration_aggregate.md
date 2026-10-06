# Pre-registration: aggregate-layer simulation (DE-SynPUF Sample 6)

Written 2026-10-06, **before DE-SynPUF Sample 6 was downloaded**. Sample 6 members are checked to
be in none of Samples 2–5. Design as in the holdout: frozen Sample 2 models, tails and LightGBM
level factor (1.018); 2008 features → 2009 cost; every eligible member in the test cohort; groups
by the same rule. Both arms use the model of record (recalibrated LightGBM cost, logistic
claimants, spliced tail) and differ in one thing: how member costs are simulated to get each
group's distribution of net claims (capped at the specific deductible).

- **Baseline (frozen):** compound Poisson–gamma Tweedie draws with the dispersion fit on
  uncapped training cost.
- **Challenger:** each member's cost = predicted cost × a ratio resampled from already-seen
  members (Samples 3–5, 216,584 members) in the same tenth of predicted cost.

Both arms rescale simulated net claims to the same expected net claims, so only the shape and
spread differ.

## Evidence that motivated this (already-seen data, post hoc)

On Samples 3–5 (`scripts/aggregate_diagnostic.py`; the empirical pool for each sample came from
the other two):

| | Tweedie | Empirical |
|---|---|---|
| Variance of group PIT values (uniform = 0.0833) | 0.066, 0.061, 0.058 | 0.089, 0.083, 0.080 |
| Mean squared z of actual net claims | 0.66, 0.59, 0.55 | 1.09, 0.97, 0.89 |
| Aggregate breaches observed / expected | 3 / 3.2, 0 / 2.8, 0 / 2.8 | 3 / 0.9, 0 / 0.7, 0 / 0.8 |

PIT value: the share of a group's simulated net claims below its actual net claims. If the
simulated distribution is right, PIT values are uniform across groups (variance 1/12); a spread
that's too wide pushes them toward 0.5 (variance below 1/12).

## Predictions for Sample 6 (intervals: 95% bootstrap resampling groups, 500 resamples)

| # | Prediction |
|---|---|
| A1 | Tweedie PIT variance between 0.050 and 0.072, interval entirely below 0.0833 |
| A2 | Empirical PIT variance between 0.074 and 0.093, interval covers 0.0833 |
| A3 | Mean squared z: Tweedie interval entirely below 1; empirical interval covers 1 |
| A4 | Empirical arm's aggregate breaches within the central 95% Poisson range of its expected count |
| A5 | Expected aggregate cost per member-month: empirical below 40% of Tweedie's |

Adoption rule: the empirical simulation replaces Tweedie in the model of record if A2 and the
empirical half of A3 both hold.

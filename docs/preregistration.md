# Pre-registration: DE-SynPUF Sample 1

Written 2026-10-05, before any DE-SynPUF file was downloaded or loaded. The code, parameters and
these rules are frozen at the commit that adds this file; any later change to them is logged in
`docs/decisions.md` with a reason and reported next to the frozen result. Every miss below gets
reported in `docs/results.md` and the README, including tests that fail.

Intervals: 95% percentile bootstrap, 500 resamples of members (member metrics) or groups (group
metrics), as implemented in `group_underwriting.metrics.cluster_bootstrap`.

Frozen baseline: Tweedie GLM for cost, logistic regression for high-cost claimants, on the
features in `features.nodes.FEATURES`. Challenger: LightGBM with the same features, one change.

## Test 0: is there year-over-year signal?

Metric: exposure-weighted Gini on inner-validation training members, 2008 features → 2009 cost.

- Prediction: prior-year cost alone 0.10–0.30; LightGBM 0.15–0.35. DE-SynPUF synthesizes
  variables partly independently, so these are lower than the 0.4–0.6 typical of real claims.
- Rule: if LightGBM Gini < 0.10, the predictive tests below are not interpreted as evidence about
  underwriting; the project moves to Synthea (recorded in `docs/decisions.md`) and Tests 1–4 are
  still reported for DE-SynPUF as a negative result.

## Test 1: LightGBM vs GLM, member next-year cost (test cohort, 2009 → 2010)

- Prediction: LightGBM − GLM Gini difference within ±0.03, interval covering 0. MAE difference
  under 5% of GLM MAE.
- Adoption rule: LightGBM becomes the cost model of record only if the Gini-difference interval
  is entirely above 0 **and** the MAE-difference interval is entirely below 0. Otherwise the GLM
  stays the model of record and pricing is reported with both.

## Test 2: high-cost claimants

- Prediction: AUC at $25k 0.65–0.80, at $50k 0.65–0.80; fewer than 50 test claimants above $100k,
  so that attachment is reported but not tested.
- Adoption rule: same as Test 1 on AUC difference (interval above 0) at $25k and $50k.

## Test 3: tail

- Prediction: GPD shape ξ between 0.0 and 0.4 above $25k. The mean-excess plot is roughly linear
  above the threshold.
- Check: on test members, actual / expected excess loss above $50k has an interval that covers 1.
  If it doesn't, the per-member excess (HCC probability × common GPD) is miscalibrated and the
  specific stop-loss price is reported as such.

## Test 4: pricing by group size

- Prediction: overall claims actual / expected within 0.90–1.10 after trend; the 50–99 band has the
  widest interval on actual loss ratio (at least twice the 500+ bands' width).
- Check: report priced vs actual loss ratio for every band with group-bootstrap intervals; a band
  whose actual / expected interval excludes 1 is a miss.

## Test 5: claims runout (mechanics check)

Paid dates are simulated (`docs/decisions.md`), so this checks the chain-ladder code, not CMS
payment speed.

- Prediction: total estimated IBNR within ±10% of actual at both valuation dates.

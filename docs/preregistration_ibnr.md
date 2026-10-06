# Pre-registration: IBNR by claim type (DE-SynPUF Sample 6)

Written 2026-10-06, before any IBNR estimate was computed on Sample 6 (its claims were loaded for
the aggregate test, but no triangle or runout figure from it has been looked at). Paid dates are
simulated with the same lag parameters as every other run, so this tests the chain-ladder method
under a changing claim mix, not Medicare payment speed.

- **Baseline (frozen):** one monthly paid triangle over all claims, volume-weighted age-to-age
  factors, valuations 2009-12-31 and 2010-12-31, 24 months of history.
- **Challenger:** the same chain ladder run separately on inpatient, outpatient, carrier and Part D
  triangles, with estimates summed.

## Evidence (Sample 2, already seen; post hoc)

| Valuation | Single triangle | By claim type |
|---|---|---|
| 2009-12-31 | +11.2% | +8.6% |
| 2010-12-31 | +20.9% | −1.1% |

Inpatient claims are about 55–60% of IBNR and pay slowest; their share of cost falls sharply in
2010, so factors from a pooled triangle overstate the remaining development.

## Predictions for Sample 6 (error = estimated / actual IBNR − 1)

| # | Prediction |
|---|---|
| I1 | Single triangle at 2010-12-31: error above +10% |
| I2 | By claim type: error within ±10% at both valuations |
| I3 | By claim type has the smaller absolute error at 2010-12-31 |

Adoption rule: by-claim-type IBNR replaces the single triangle if I2 holds.

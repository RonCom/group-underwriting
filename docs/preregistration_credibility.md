# Pre-registration: credibility blending of group experience (DE-SynPUF Sample 7)

Written 2026-10-06, **before DE-SynPUF Sample 7 was downloaded**. Sample 7 members are checked to be
in none of Samples 2–6. Design as in earlier rounds: frozen Sample 2 models with the LightGBM level
factor (1.018), 2008 features → 2009 cost, every eligible member in the test cohort, groups by the
same rule.

An underwriter renewing a group blends a manual rate with the group's own experience, weighted by
credibility Z = n / (n + k), n = the group's prior-year member-months. Here:

- **Experience:** the group's 2008 allowed cost per member-month as visible at the pricing date,
  projected by one factor c.
- **Two manual rates:** the model of record (member-level claims model, recalibrated LightGBM) and a
  demographic rate (age band × sex table of cost per member-month).
- c and k are fitted per manual rate on Samples 3–6 by weighted least squares on group cost per
  member-month and frozen in `docs/credibility/frozen.json`: c = 1.008 for both; k = 293,317
  member-months (model of record) and 3,409 (demographic).

Script: `scripts/credibility_test.py` (`fit` wrote the frozen constants; `test` scores Sample 7).

## Evidence (Samples 3–6, leave one sample out; post hoc)

| Manual rate | Fitted k | Median Z | Change in group PMPM MAE from blending |
|---|---|---|---|
| Model of record | 201,876–650,968 | 0.003–0.011 | −0.5% to +0.5% |
| Demographic | 3,353–4,075 | 0.36–0.40 | −27% to −33% |

## Predictions (intervals: 95% bootstrap resampling groups, 500 resamples)

| # | Prediction |
|---|---|
| C1 | Model of record: blending changes group PMPM MAE by −2% to +2%, interval of the change covers 0 |
| C2 | Demographic: blending reduces group PMPM MAE by 20%–40%, interval of the change entirely below 0 |
| C3 | Model of record unblended has lower MAE than the blended demographic rate (interval of the difference entirely below 0) |
| C4 | Blended model-of-record claims A/E interval covers 1 |

Adoption rule: credibility blending joins the model of record only if the interval of the C1
change is entirely below 0.

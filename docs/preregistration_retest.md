# Pre-registration: LightGBM re-test and spliced tail (DE-SynPUF Sample 4)

Written 2026-10-05, after the Sample 3 follow-up (`docs/scorecard.md`) and **before Sample 4 was
downloaded**. Two changes, each tested alone against the frozen baseline (GLM / logistic cost and
claimant models, one GPD above $25k). Sample 4 members are checked to be in neither Sample 2 nor
Sample 3. Design as in the follow-up: frozen Sample 2 models, 2008 features → 2009 cost, every
eligible member in the test cohort, groups by the same rule, trend = 1. Intervals: 95% bootstrap,
500 resamples of members or groups. Every miss is reported.

What informs these predictions: all Sample 2 and Sample 3 results, in particular on Sample 3
LightGBM − GLM Gini +0.011 [0.010–0.013], MAE −$239 [−256 to −226], AUC difference +0.004 ($25k),
and excess A/E above $100k of 0.59 [0.42–0.77] with the single GPD.

## R1: LightGBM vs GLM (same frozen Sample 2 models)

| # | Prediction |
|---|---|
| R1a | LightGBM − GLM member Gini difference between +0.005 and +0.020, interval above 0 |
| R1b | LightGBM − GLM MAE difference interval entirely below 0 |
| R1c | LightGBM − logistic AUC difference at $25k and $50k: intervals cover 0 |

Adoption rule (unchanged from Test 1): LightGBM becomes the cost model of record if the Gini
difference interval is above 0 and the MAE difference interval is below 0. Claimant model: LightGBM
replaces logistic only if the AUC-difference interval is above 0 at both $25k and $50k.

## R2: spliced tail above $100k

Challenger: keep the frozen GPD above $25k up to $100k, and above $100k use a second GPD fit to
2009 annual cost above $100k from Sample 2 training members and all eligible Sample 3 members
(pooled, both already seen). For a member with P(X > $25k) = p from the logistic claimant model,
S(x) = p · S₁(x − 25k) for 25k ≤ x < 100k and p · S₁(75k) · S₂(x − 100k) above, and expected excess
over d is the integral of S from d to infinity.

| # | Prediction |
|---|---|
| R2a | Second GPD shape ξ₂ between −0.2 and 0.3 |
| R2b | Baseline (single GPD) excess A/E above $100k on Sample 4: interval excludes 1, below 1 |
| R2c | Spliced excess A/E above $100k: interval covers 1 |
| R2d | Spliced excess A/E above $25k and $50k: intervals cover 1 |

Adoption rule: the spliced tail replaces the single GPD if R2c and R2d both hold.

## R3: replication of the Sample 3 level result (baseline models)

| # | Prediction |
|---|---|
| R3a | Group claims A/E (GLM), all groups: interval covers 1 |
| R3b | Specific stop-loss A/E (GLM, single GPD), all groups: interval covers 1 |

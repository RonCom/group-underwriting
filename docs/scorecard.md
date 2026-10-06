# Pre-registered tests: scorecard (DE-SynPUF Sample 2)

Run 2026-10-05 with the code and rules frozen in `docs/preregistration.md` (amended only for
Sample 1 → 2 before any data was loaded). One reporting change came after the first run, with no
change to models or rules: the report now computes the pre-registered AUC difference and prices
groups with both models, as the Test 1 rule requires (`docs/decisions.md`). Full tables:
[`results.md`](results.md).

| Test | Prediction | Result | Verdict |
|---|---|---|---|
| 0. Signal | Prior-year cost Gini 0.10–0.30 | 0.639 | **Miss** (stronger) |
| 0. Signal | LightGBM Gini 0.15–0.35 | 0.708 | **Miss** (stronger) |
| 0. Rule | Move to Synthea if LightGBM Gini < 0.10 | 0.708 | Stay on DE-SynPUF |
| 1. Cost | LightGBM − GLM Gini within ±0.03, interval covering 0 | +0.012 [0.009–0.015] | **Miss**: within ±0.03 but the interval excludes 0 |
| 1. Cost | MAE difference under 5% of GLM MAE | −$20 [−40 to +0.3], 0.4% | Hit |
| 1. Rule | Adopt LightGBM if Gini diff > 0 **and** MAE diff < 0 | MAE interval crosses 0 | **GLM stays model of record** |
| 2. HCC | AUC at $25k 0.65–0.80 | LightGBM 0.740, GLM 0.739 | Hit |
| 2. HCC | AUC at $50k 0.65–0.80 | LightGBM 0.718, GLM 0.711 | Hit |
| 2. HCC | < 50 test claimants above $100k | 10 | Hit |
| 2. Rule | Adopt LightGBM if AUC diff > 0 at $25k and $50k | +0.001 [−0.004–0.008]; +0.007 [−0.011–0.025] | **Logistic stays** |
| 3. Tail | GPD shape ξ in 0.0–0.4 above $25k | 0.107 (KS p = 0.30) | Hit |
| 3. Tail | Actual / expected excess above $50k covers 1 | 0.25 [0.19–0.31] (GLM HCC) | **Miss** |
| 4. Pricing | Claims actual / expected within 0.90–1.10 | 0.58 [0.57–0.59] (GLM) | **Miss** |
| 4. Pricing | No band's actual / expected interval excludes 1 | All five exclude 1 | **Miss** |
| 4. Pricing | 50–99 actual-LR interval ≥ 2× the 500+ bands' width | 0.077 vs 0.018 and 0.014 | Hit |
| 5. IBNR | Estimate within ±10% of actual at both valuations | +11.2% and +20.9% | **Miss** |

## What drives the misses (post hoc, not pre-registered)

**DE-SynPUF's 2010 claims are thin.** Allowed cost per fee-for-service member-month, all
members, by year of service:

| Claim type | 2008 | 2009 | 2010 | 2010 / 2009 |
|---|---|---|---|---|
| Inpatient | $323 | $325 | $192 | 0.59 |
| Outpatient | $116 | $144 | $87 | 0.61 |
| Carrier | $228 | $243 | $168 | 0.69 |
| Part D | $133 | $152 | $107 | 0.70 |

Claim counts fall by the same proportions (inpatient 28.8 → 17.1 per 1,000 member-months) while
enrollment doesn't. Nothing visible at the 2009 cutoff predicts this: the 2008 → 2009 trend was
0.985. So every level-based check on 2010 (Tests 3 and 4) is dominated by a drop in the data, not
by the pricing method. Ranking checks (Gini, AUC, lift) don't depend on level and are usable.

**IBNR** (Test 5) uses simulated paid dates, so the miss is about the method under a changing mix.
An untested explanation: inpatient lags are measured from admission month while payment follows
discharge, and inpatient's share of cost falls in 2010, so factors fit on 2008–09 overstate the
remaining development. Not verified.

**Data note.** `PROD_SRVC_ID` is close to unique per fill in DE-SynPUF (distinct drugs ≈ fills:
19.43 vs 19.43 per member in 2009), so "distinct drugs" duplicates "fills".

# Follow-up (pre-registered in `docs/preregistration_followup.md`)

Run 2026-10-05: frozen Sample 2 models on DE-SynPUF Sample 3 (72,271 members, none in Sample 2;
207 groups), 2008 features → 2009 cost, plus relative pricing on the Sample 2 2010 test. Full
tables: [`followup/results.md`](followup/results.md). **10 of 12 predictions hit.**

| # | Prediction | Result (GLM unless noted) | Verdict |
|---|---|---|---|
| F1a | Member Gini 0.62–0.74 | 0.698 [0.692–0.705] | Hit |
| F1b | Predicted / actual 0.95–1.05 | 1.005 [0.995–1.014] | Hit |
| F1c | AUC 0.72–0.82 at $25k, 0.70–0.82 at $50k | 0.823 and 0.850 | **Miss** (stronger) |
| F1d | Excess A/E intervals cover 1 at $25k and $50k | 0.98 [0.94–1.03]; 0.97 [0.88–1.05] | Hit |
| F1e | Group claims A/E covers 1, within 0.95–1.05 | 0.995 [0.987–1.004] | Hit |
| F1f | No band's claims A/E interval excludes 1 | All five cover 1 (lowest: 50–99, 0.98 [0.94–1.02]) | Hit |
| F1g | Specific A/E interval covers 1 | 0.94 [0.85–1.03] | Hit |
| F1h | Aggregate breaches within 95% Poisson range | 2 observed, 2.8 expected (range 0–6) | Hit |
| F1i | 50–99 actual-LR interval ≥ 2× each 500+ band's | 0.066 vs 0.030 and 0.023 | Hit |
| F1j | Group PMPM Spearman 0.3–0.7, interval above 0 | 0.698 [0.602–0.764] | Hit |
| F2a | Rescaled 2010 A/E covers 1 in every band | 50–99: 1.07 [1.01–1.15]; 250–499: 0.96 [0.94–0.99]; 1,000+: 0.98 [0.95–0.99] | **Miss** |
| F2b | 2010 group PMPM Spearman 0.2–0.6, interval above 0 | 0.586 [0.421–0.714] | Hit |

**Reading.**
- On complete years and a population the models never saw, the pricing method is calibrated:
  claims A/E 0.995, specific A/E 0.94, and 2 aggregate breaches against 2.8 expected. That is
  consistent with the Sample 2 level misses coming from the 2010 data drop, not the method.
- Above $100k (not pre-registered; 75 claimants) actual excess is 0.59 [0.42–0.77] of expected:
  the single GPD overstates the far tail.
- On Sample 3, LightGBM beats the GLM on both MAE (−$239 [−256 to −226]) and Gini (+0.011
  [0.010–0.013]), which would meet the Test 1 adoption rule. The rule was applied once, on Sample 2,
  and isn't re-run here. A pre-registered re-test on another sample would settle it.
- In 2010, after removing the overall drop, 50–99 groups run 7% above expected and 250–499 groups
  4% below. The 2010 thinning isn't uniform across groups; the cause isn't established.

# Re-test (pre-registered in `docs/preregistration_retest.md`)

Run 2026-10-05: frozen Sample 2 models on DE-SynPUF Sample 4 (72,197 members, none in Samples 2
or 3; 205 groups), 2008 features → 2009 cost. Full tables: [`retest/results.md`](retest/results.md).
**8 of 9 predictions hit.**

| # | Prediction | Result | Verdict |
|---|---|---|---|
| R1a | LightGBM − GLM Gini +0.005 to +0.020, interval above 0 | +0.012 [0.010–0.014] | Hit |
| R1b | LightGBM − GLM MAE interval below 0 | −$222 [−237 to −208] | Hit |
| R1c | AUC difference intervals cover 0 at $25k and $50k | $25k: +0.004 [0.001–0.006]; $50k: +0.004 [−0.001–0.008] | **Miss** at $25k |
| R1 rule | Cost: adopt LightGBM if R1a and R1b intervals clear 0 | Both clear | **LightGBM adopted for cost** |
| R1 rule | Claimants: adopt LightGBM if AUC difference > 0 at both | $50k interval covers 0 | **Logistic stays** |
| R2a | Upper GPD shape ξ₂ in −0.2 to 0.3 | −0.088 (113 exceedances, KS p = 0.99) | Hit |
| R2b | Single-GPD excess A/E above $100k: interval below 1 | 0.78 [0.61–0.99] | Hit |
| R2c | Spliced excess A/E above $100k covers 1 | 1.02 [0.80–1.29] | Hit |
| R2d | Spliced excess A/E above $25k and $50k cover 1 | 1.01 [0.97–1.05]; 1.01 [0.92–1.10] | Hit |
| R2 rule | Adopt spliced tail if R2c and R2d hold | Both hold | **Spliced tail adopted** |
| R3a | Group claims A/E (GLM) covers 1 | 1.00 [0.99–1.01] | Hit |
| R3b | Specific A/E (GLM, single GPD) covers 1 | 1.00 [0.89–1.11] | Hit |

**Reading.**
- LightGBM's advantage replicates on a second unseen sample with nearly the same size (Gini
  +0.011 / +0.012, MAE −$239 / −$222), so it becomes the cost model of record.
- LightGBM's level is about 2% low on both new samples (predicted / actual 0.986 and 0.978, GLM
  0.997–1.005), so group claims A/E with LightGBM is 1.02 [1.01–1.03]. The adoption rule didn't
  include calibration. A level recalibration of LightGBM is the obvious next challenger.
- The upper GPD has a negative shape (a bounded tail), which is why one GPD from $25k overstated
  losses above $100k. Spliced at $100k, expected excess matches actual at all three attachments.
- At $100k, LightGBM's claimant AUC is below logistic's (−0.023 [−0.041 to −0.006], 88 claimants;
  not pre-registered).

# Holdout (pre-registered in `docs/preregistration_holdout.md`)

Run 2026-10-05: frozen Sample 2 models, tails and level factors on DE-SynPUF Sample 5 (72,116
members, none in Samples 2–4; 205 groups), 2008 features → 2009 cost. Full tables:
[`holdout/results.md`](holdout/results.md). **6 of 7 predictions hit.**

| # | Prediction | Result | Verdict |
|---|---|---|---|
| H1a | Uncalibrated LightGBM predicted / actual below 1 | 0.984 [0.976–0.992] | Hit |
| H1b | Recalibrated (× 1.018) predicted / actual covers 1 | 1.002 [0.993–1.010] | Hit |
| H1c | Group claims A/E: model of record above 1, recalibrated covers 1 | 1.017 [1.008–1.025]; 0.999 [0.990–1.007] | Hit |
| H1 rule | Adopt recalibration if H1b holds and recalibrated A/E covers 1 | Both hold | **Recalibration adopted** |
| H2a | Specific A/E (logistic, spliced) covers 1 | 0.91 [0.80–1.02] | Hit |
| H2b | Spliced excess A/E above $100k covers 1 | 0.88 [0.60–1.16] (single GPD: 0.68 [0.46–0.89]) | Hit |
| H2c | Aggregate breaches within 95% Poisson range | 0 observed, 2.9 expected (range 0–7) | Hit |
| H2d | No band's recalibrated claims A/E excludes 1 | 250–499: 0.98 [0.963–0.994] | **Miss** |

**Reading.**
- With the level factor estimated on Samples 3–4, LightGBM's predicted / actual on a fifth sample
  moves from 0.984 to 1.002, and group claims A/E from 1.017 to 0.999.
- The single GPD again overstates losses above $100k (A/E 0.68); the spliced tail is in range
  (0.88) for the second time.
- Aggregate breaches came in at or below expectation in every complete-year run (Samples 3, 4,
  5: 2, 2, 0 observed with the baseline against 2.8, 2.4, 2.4 expected; pooled 4 vs 7.6,
  Poisson P(≤ 4) = 0.12). Not significant, but the direction is consistent: the Tweedie
  simulation may be too wide (post hoc).
- The 250–499 band runs 2% below expected with every variant; the cause isn't established.

# Aggregate-layer simulation (pre-registered in `docs/preregistration_aggregate.md`)

Run 2026-10-06: DE-SynPUF Sample 6 (72,216 members, none in Samples 2–5; 206 groups), 2008 features
→ 2009 cost, model of record with two ways of simulating member costs. Full tables:
[`aggtest/results.md`](aggtest/results.md). **5 of 5 predictions hit.**

| # | Prediction | Result | Verdict |
|---|---|---|---|
| A1 | Tweedie PIT variance 0.050–0.072, interval below 0.0833 | 0.0599 [0.0521–0.0674] | Hit |
| A2 | Empirical PIT variance 0.074–0.093, interval covers 0.0833 | 0.0825 [0.0717–0.0914] | Hit |
| A3 | Mean squared z: Tweedie interval below 1, empirical covers 1 | 0.58 [0.48–0.71]; 0.95 [0.79–1.14] | Hit |
| A4 | Empirical breaches within 95% Poisson range | 0 observed, 1.0 expected (range 0–3) | Hit |
| A5 | Empirical expected aggregate cost below 40% of Tweedie's | $0.024 vs $0.109 PMPM (22%) | Hit |
| Rule | Adopt empirical simulation if A2 and empirical A3 hold | Both hold | **Empirical simulation adopted** |

**Reading.**
- The Tweedie simulation's spread of group net claims is about 1.3× too wide (mean squared z 0.58
  means actual deviations are √0.58 ≈ 0.76 of the simulated standard deviation). Resampling
  actual-to-predicted ratios from seen members gets the spread right on a sample it never saw.
- The aggregate layer's expected cost falls by about 78% under the adopted simulation. With a
  125% corridor, a breach needs a group's net claims 25% above expected, which the narrower
  distribution makes rarer: expected breaches drop from 3.1 to 1.0 on Sample 6.

# IBNR by claim type (pre-registered in `docs/preregistration_ibnr.md`)

Run 2026-10-06 on DE-SynPUF Sample 6 claims (simulated paid dates). **2 of 3 predictions hit.**

| # | Prediction | Result | Verdict |
|---|---|---|---|
| I1 | Single triangle at 2010-12-31: error above +10% | +24.5% | Hit |
| I2 | By claim type: error within ±10% at both valuations | +8.3% (2009-12-31), +15.7% (2010-12-31) | **Miss** |
| I3 | By claim type has the smaller absolute error at 2010-12-31 | 15.7% vs 24.5% | Hit |
| Rule | Adopt by claim type if I2 holds | I2 missed | **Single triangle stays** |

**Reading.**
- Splitting by claim type removes part of the bias at both valuations on Sample 6 (12.8% → 8.3%,
  24.5% → 15.7%), but on Sample 6 it doesn't remove all of it the way it did on Sample 2 (−1.1%).
- Both methods overestimate at every valuation on both samples (+8% to +25%), so a second source
  of upward bias remains besides the claim mix. Not identified.

# Post hoc: the 250–499 band (not pre-registered)

The H2d miss on Sample 5 (250–499 band A/E 0.977) doesn't recur. By sample, the band's claims A/E
is 0.995, 1.007, 0.977 and 1.002 (Samples 3–6); pooled over 188 groups it's 0.995 [0.987–1.004].
Three pre-registered rounds tested five bands each, so one 95% interval excluding 1 by chance is
expected. Group A/E is unrelated to how many states a group spans (r = 0.003) or to log group size
(r = −0.03). Treated as chance; no change.

# Under-65 subgroup (pre-registered in `docs/preregistration_under65.md`; not a holdout)

Run 2026-10-06: 44,605 members under 65 (15.4% of Samples 3–6, Medicare through disability or
ESRD), 132 groups re-cut from them, model of record. Tables: [`under65/results.md`](under65/results.md).
**6 of 6 predictions hit.**

| # | Prediction | Result | Verdict |
|---|---|---|---|
| U1 | Member predicted / actual 0.95–1.05 | 1.002 [0.991–1.013] | Hit |
| U2 | Member Gini at least 0.60 | 0.733 [0.725–0.740] | Hit |
| U3 | Logistic AUC at least 0.75 at $25k and $50k | 0.833; 0.867 | Hit |
| U4 | Group claims A/E interval covers 1 | 0.998 [0.986–1.008] | Hit |
| U5 | Excess A/E above $25k and $50k cover 1 | 1.03 [0.98–1.08]; 1.03 [0.93–1.14] | Hit |
| U6 | PIT variance covers 0.0833 | 0.0876 [0.0738–0.1007] | Hit |

**Reading.** Pricing holds for the under-65 members (mean cost $7,525 against $6,920 for 65+),
including the simulated spread with a ratio pool drawn only from 65+ members. They're a disabled
population, not workers, so this narrows the population limit without removing it.

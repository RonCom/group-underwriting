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

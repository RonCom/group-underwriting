# Decisions

Dated log of choices that change what the numbers mean. Newest last.

## 2026-10-05: initial build

**Data source.** CMS DE-SynPUF Sample 1 (Beneficiary Summary 2008–2010, Inpatient, Outpatient,
Carrier A/B, Prescription Drug Events). The CMS download hosts were blocked from the environment
the project was built in, so the first build runs only on generated data (`--env synthetic`). The
Synthea fallback in CLAUDE.md is triggered by the pre-registered signal check
(`docs/preregistration.md`, Test 0), not yet run.

**Allowed cost.** DE-SynPUF facility claims carry payments, not allowed amounts. Allowed is rebuilt
as Medicare payment + primary-payer payment + beneficiary deductible + coinsurance + blood
deductible (inpatient: Part A fields; outpatient: Part B fields). Carrier: sum of the 13
`LINE_ALOWD_CHRG_AMT` columns. Part D: `TOT_RX_CST_AMT`. Negative amounts are floored at 0.
Inpatient claim segments are summed per `CLM_ID`.

**Paid dates are simulated.** DE-SynPUF has no paid date. Each claim gets
paid = service end + lag, lag = minimum + Gamma(shape, mean/shape) by claim type, plus a uniform
late-payment tail for a small share (`paid_lag` in `conf/base/parameters.yml`). Consequences: the
runout cutoff in the features and the IBNR test use a lag pattern we chose, so the IBNR results
check the code path and the chain-ladder method, not real Medicare payment speed.

**Eligibility.** A (member, year Y) row needs the member in the summary files for Y and Y+1, zero
HMO months in both (HMO members have no fee-for-service claims) and at least one month of Parts A
and B in Y+1. Members without Part D stay in; `months_d` is a feature.

**Out-of-time split.** Members are split 50/50 by a salted hash of `DESYNPUF_ID`. Training rows:
training members, features 2008 → cost 2009. Test rows: test members, features 2009 → cost 2010.
No member and no group appears in both. Within training, 20% of members (second hash) form an
inner validation set for LightGBM early stopping, the Tweedie dispersion estimate and the signal
check; both cost models are fit on the remaining 80%, so they see the same data.

**Target and exposure.** Cost models predict annualized cost (next-year allowed / exposure,
exposure = months of A and B in Y+1 / 12) with exposure as the sample weight, Tweedie power 1.5.
High-cost-claimant labels use raw annual cost (stop-loss attaches to the contract year, not an
annualized rate).

**Features exclude race.** `BENE_RACE_CD` is loaded but not used for pricing. State and county
only drive group assignment.

**Runout in features.** Features as of Y-12-31 use claims incurred in Y and paid by the cutoff +
3 months, the same rule in training and test.

**Trend.** The models learn the cost level of their training target year (2009). Test predictions
for 2010 are multiplied by the 2008 → 2009 PMPM ratio over all fee-for-service member-months, both
years measured at the same 3-month runout (data available at the 2009 cutoff + 3 months).

**Employer groups.** Within each split, members are sorted by state, county and a hash, then cut
into consecutive blocks with sizes drawn from bands 50–99 / 100–249 / 250–499 / 500–999 /
1000–2500 (weights in `groups.size_bands`). Groups are therefore geographically local, like real
employers, but their members are Medicare beneficiaries (65+ or disabled), an age-skewed proxy for
an employer population. A leftover block smaller than 50 is merged into the previous group.
The synthetic environment uses more small groups so its smaller test cohort still has ~45 groups.

**Tail.** GPD fit to training members' 2009 annual cost above $25,000 (also the lowest attachment
point, chosen from the mean-excess plot). A member's expected loss above deductible d is
P(X > $25k) from the LightGBM HCC model × the GPD stop-loss transform at d − $25k. This links the
member-level classifier to the portfolio tail; it assumes the excess distribution above $25k is
the same for every member.

**Pricing.** Specific deductible by size band (25k for 50–99, 50k for 100–499, 100k for 500+).
Aggregate attachment = 125% of expected claims net of specific. Expected aggregate excess by
Monte Carlo: members drawn from the fitted Tweedie (compound Poisson–gamma), capped at the
specific deductible, summed per group and rescaled to the expected net claims. Premium = expected
net + specific + aggregate, loaded 15%. Priced loss ratio = expected claims / premium; actual loss
ratio = actual claims / premium.

**IBNR.** Chain ladder on monthly paid triangles (24 incurred months × 24 lag months) at
valuations 2009-12-31 and 2010-12-31, volume-weighted age-to-age factors, compared with the
actual ultimate known from the simulated paid dates.

**Warehouse.** dbt reads the raw CSVs (DuckDB `read_csv`) and two Kedro outputs it cannot rebuild
in SQL: simulated paid dates and the cohort/group assignment. The feature mart is then compared
with the Kedro features on every row and column (`kedro run --pipeline warehouse`). The Snowflake
target is configured in `dbt/profiles.yml` but not yet run (no account in this environment).

**Tracking.** MLflow with a local SQLite store (`mlflow.db`, git-ignored) and the model registry;
off in synthetic mode. Drift between scoring years: PSI per feature always; an Evidently HTML
report on real-data runs (`drift` extra).

**Blog post.** Deferred until the real-data run: a write-up of synthetic results would describe
the generator, not DE-SynPUF.

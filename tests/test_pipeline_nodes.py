"""Unit tests for nodes that the end-to-end run exercises but doesn't check numerically."""

import numpy as np
import pandas as pd
import pytest

from group_underwriting.pipelines.features.nodes import assign_groups, build_cohorts
from group_underwriting.pipelines.ingest.nodes import load_claims
from group_underwriting.pipelines.pricing.nodes import price_variants
from group_underwriting.pipelines.runout.nodes import estimate_ibnr

BANDS = [
    {"min": 50, "max": 99, "weight": 0.5},
    {"min": 100, "max": 249, "weight": 0.5},
]


def _cohort(n, split):
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "member_id": [f"{split}{i:05d}" for i in range(n)],
            "split": split,
            "state": rng.integers(1, 5, n),
            "county": rng.integers(0, 10, n),
        }
    )


@pytest.mark.parametrize("n", [237, 1000, 1049])
def test_assign_groups_covers_every_member_once_and_respects_bands(n):
    cohorts = pd.concat([_cohort(n, "train"), _cohort(n + 13, "test")], ignore_index=True)
    g = assign_groups(cohorts, {"seed": 1, "salt": "s", "size_bands": BANDS})
    assert len(g) == len(cohorts) and g["member_id"].is_unique
    assert (g.groupby("group_id")["split"].nunique() == 1).all()
    sizes = g.groupby("group_id").size()
    # the last block of a split can be merged into its neighbour, so it may exceed the top band
    assert sizes.min() >= BANDS[0]["min"]
    assert (sizes <= BANDS[-1]["max"] + BANDS[0]["min"]).all()


def test_build_cohorts_eligibility_and_disjoint_split():
    rows = []
    for i in range(400):
        hmo = 12 if i % 10 == 0 else 0
        for y in (2008, 2009, 2010):
            rows.append(
                {"member_id": f"m{i}", "year": y, "months_a": 12, "months_b": 12, "months_hmo": hmo}
            )
    rows.append(
        {"member_id": "dies", "year": 2008, "months_a": 12, "months_b": 12, "months_hmo": 0}
    )
    c = build_cohorts(
        pd.DataFrame(rows),
        {"split_salt": "x", "train_share": 0.5, "train_year": 2008, "test_year": 2009},
    )
    assert not c["member_id"].isin([f"m{i}" for i in range(0, 400, 10)]).any()  # HMO excluded
    assert "dies" not in set(c["member_id"])  # not enrolled in the target year
    assert set(c.loc[c["split"] == "train", "feature_year"]) == {2008}
    assert set(c.loc[c["split"] == "test", "feature_year"]) == {2009}
    assert not set(c.loc[c["split"] == "train", "member_id"]) & set(
        c.loc[c["split"] == "test", "member_id"]
    )


def test_chain_ladder_recovers_ultimate_for_a_fixed_lag_pattern():
    # each incurred month pays 50% in month 0, 30% in month 1, 20% in month 2; volume grows
    rows = []
    for k, inc in enumerate(pd.date_range("2008-01-01", "2009-12-01", freq="MS")):
        total = 1000 + 50 * k
        for lag, share in enumerate([0.5, 0.3, 0.2]):
            rows.append(
                {
                    "from_dt": inc,
                    "paid_dt": inc + pd.DateOffset(months=lag),
                    "allowed": total * share,
                }
            )
    factors, est = estimate_ibnr(
        pd.DataFrame(rows),
        {"valuation_dates": ["2009-12-31"], "history_months": 24, "max_lag_months": 4},
    )
    est = est[est["method"] == "single"]
    np.testing.assert_allclose(est["estimated_ultimate"], est["actual_ultimate"], rtol=1e-9)
    np.testing.assert_allclose(factors["completion"].iloc[:3], [0.5, 0.8, 1.0], rtol=1e-9)


def test_load_claims_rebuilds_allowed_cost(tmp_path):
    pd.DataFrame(
        {  # two segments of one inpatient claim
            "DESYNPUF_ID": ["A", "A"],
            "CLM_ID": ["1", "1"],
            "SEGMENT": [1, 2],
            "CLM_FROM_DT": ["20080105", "20080110"],
            "CLM_THRU_DT": ["20080110", "20080112"],
            "CLM_PMT_AMT": [8000, 500],
            "NCH_PRMRY_PYR_CLM_PD_AMT": [0, 100],
            "NCH_BENE_IP_DDCTBL_AMT": [1024, 0],
            "NCH_BENE_PTA_COINSRNC_LBLTY_AM": [0, 0],
            "NCH_BENE_BLOOD_DDCTBL_LBLTY_AM": [0, 0],
            "CLM_UTLZTN_DAY_CNT": [5, 2],
            "ICD9_DGNS_CD_1": ["4280", "4280"],
        }
    ).to_csv(tmp_path / "DE1_0_2008_to_2010_Inpatient_Claims_Sample_9.csv", index=False)
    pd.DataFrame(
        {
            "DESYNPUF_ID": ["A"],
            "CLM_ID": ["2"],
            "CLM_FROM_DT": ["20080201"],
            "CLM_THRU_DT": ["20080201"],
            "CLM_PMT_AMT": [80],
            "NCH_PRMRY_PYR_CLM_PD_AMT": [0],
            "NCH_BENE_PTB_DDCTBL_AMT": [0],
            "NCH_BENE_PTB_COINSRNC_AMT": [20],
            "NCH_BENE_BLOOD_DDCTBL_LBLTY_AM": [0],
            "ICD9_DGNS_CD_1": ["4019"],
        }
    ).to_csv(tmp_path / "DE1_0_2008_to_2010_Outpatient_Claims_Sample_9.csv", index=False)
    car = {
        "DESYNPUF_ID": ["A"],
        "CLM_ID": ["3"],
        "CLM_FROM_DT": ["20080301"],
        "CLM_THRU_DT": ["20080301"],
        "ICD9_DGNS_CD_1": ["4019"],
    }
    car.update({f"LINE_ALOWD_CHRG_AMT_{j}": [10.0 * j if j <= 3 else None] for j in range(1, 14)})
    pd.DataFrame(car).to_csv(
        tmp_path / "DE1_0_2008_to_2010_Carrier_Claims_Sample_9A.csv", index=False
    )
    pd.DataFrame(
        {
            "DESYNPUF_ID": ["A"],
            "PDE_ID": ["4"],
            "SRVC_DT": ["20080401"],
            "PROD_SRVC_ID": ["00000000001"],
            "TOT_RX_CST_AMT": [55.5],
        }
    ).to_csv(tmp_path / "DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_9.csv", index=False)

    c = load_claims(str(tmp_path)).set_index("source")
    assert c.loc["IP", "allowed"] == 8000 + 500 + 100 + 1024
    assert c.loc["IP", "ip_days"] == 7
    assert str(c.loc["IP", "from_dt"])[:10] == "2008-01-05"
    assert str(c.loc["IP", "thru_dt"])[:10] == "2008-01-12"
    assert c.loc["OP", "allowed"] == 100
    assert c.loc["CAR", "allowed"] == 60
    assert c.loc["RX", "allowed"] == 55.5


def test_price_variants_applies_level_factor_and_tail_choice():
    n = 120
    feats = pd.DataFrame(
        {
            "member_id": [f"m{i}" for i in range(n)],
            "split": "test",
            "group_id": ["G1"] * 60 + ["G2"] * 60,
            "size_band": "50-99",
            "exposure": 1.0,
            "target_cost": 5000.0,
        }
    )
    preds = feats[["member_id", "split"]].assign(pred_glm=5000.0, pred_gbm=4000.0)
    single = feats[["member_id", "split"]].assign(
        exp_excess_glm_25000=100.0, exp_excess_gbm_25000=100.0
    )
    spliced = single.assign(exp_excess_glm_25000=60.0, exp_excess_gbm_25000=60.0)
    variants = {
        "a": {"label": "a", "cost": "gbm", "claimant": "glm", "tail": "single", "calibrate": False},
        "b": {"label": "b", "cost": "gbm", "claimant": "glm", "tail": "spliced", "calibrate": True},
    }
    out = price_variants(
        feats,
        preds,
        single,
        spliced,
        {"tweedie_power": 1.5, "phi": {"glm": 50.0, "gbm": 50.0}},
        pd.DataFrame({"model": ["glm", "gbm"], "factor": [1.0, 1.25]}),
        variants,
        {
            "seed": 0,
            "n_sims": 50,
            "aggregate_corridor": 1.25,
            "load": 0.15,
            "specific_deductible_by_band": {"50-99": 25000},
        },
    ).set_index(["model", "group_id"])
    assert out.loc[("a", "G1"), "expected_claims"] == pytest.approx(60 * 4000)
    assert out.loc[("b", "G1"), "expected_claims"] == pytest.approx(60 * 4000 * 1.25)
    assert out.loc[("a", "G1"), "expected_specific"] == pytest.approx(60 * 100)
    assert out.loc[("b", "G1"), "expected_specific"] == pytest.approx(60 * 60)
    assert out.loc[("a", "G2"), "actual_claims"] == pytest.approx(60 * 5000)


def test_empirical_draws_resample_ratios_within_bands():
    from group_underwriting.pipelines.pricing.nodes import _empirical_draws

    pool = pd.DataFrame(
        {
            "band_lo": [-np.inf] * 3 + [1000.0] * 3,
            "ratio": [0.0, 1.0, 2.0, 10.0, 10.0, 10.0],
        }
    )
    rng = np.random.default_rng(0)
    pred = np.array([500.0, 5000.0])
    draws = _empirical_draws(rng, pred, np.array([1.0, 0.5]), pool, 4000)
    assert set(np.unique(draws[:, 0])) == {0.0, 500.0, 1000.0}  # low band ratios x 500
    assert np.all(draws[:, 1] == 10 * 5000 * 0.5)  # high band, exposure 0.5
    assert draws[:, 0].mean() == pytest.approx(500, rel=0.05)


def test_empirical_variant_falls_back_to_tweedie_without_pool():
    n = 60
    feats = pd.DataFrame(
        {
            "member_id": [f"m{i}" for i in range(n)],
            "split": "test",
            "group_id": "G1",
            "size_band": "50-99",
            "exposure": 1.0,
            "target_cost": 5000.0,
        }
    )
    preds = feats[["member_id", "split"]].assign(pred_glm=5000.0, pred_gbm=5000.0)
    exc = feats[["member_id", "split"]].assign(exp_excess_glm_25000=100.0)
    variant = {
        "label": "e",
        "cost": "gbm",
        "claimant": "glm",
        "tail": "single",
        "calibrate": False,
        "simulation": "empirical",
    }
    args = (
        feats,
        preds,
        exc,
        exc,
        {"tweedie_power": 1.5, "phi": {"glm": 50.0, "gbm": 50.0}},
        pd.DataFrame({"model": ["glm", "gbm"], "factor": [1.0, 1.0]}),
        {"e": variant},
        {
            "seed": 0,
            "n_sims": 50,
            "aggregate_corridor": 1.25,
            "load": 0.15,
            "specific_deductible_by_band": {"50-99": 25000},
        },
    )
    empty = pd.DataFrame({"band_lo": [], "ratio": []})
    a = price_variants(*args, empty)
    b = price_variants(*args)
    pd.testing.assert_frame_equal(a, b)


def test_ibnr_by_source_recovers_ultimate_when_mix_shifts():
    # slow-paying IP shrinks over time while fast RX grows: a pooled triangle is biased,
    # separate triangles are exact
    rows = []
    for k, inc in enumerate(pd.date_range("2008-01-01", "2009-12-01", freq="MS")):
        for src, total, shares in (
            ("IP", 1000 - 30 * k, [0.2, 0.3, 0.5]),
            ("RX", 200 + 40 * k, [0.9, 0.1, 0.0]),
        ):
            for lag, share in enumerate(shares):
                rows.append(
                    {
                        "source": src,
                        "from_dt": inc,
                        "paid_dt": inc + pd.DateOffset(months=lag),
                        "allowed": total * share,
                    }
                )
    _, est = estimate_ibnr(
        pd.DataFrame(rows),
        {"valuation_dates": ["2009-12-31"], "history_months": 24, "max_lag_months": 4},
    )
    tot = est.groupby("method")[["estimated_ibnr", "actual_ibnr"]].sum()
    assert tot.at["by_source", "estimated_ibnr"] == pytest.approx(
        tot.at["by_source", "actual_ibnr"]
    )
    assert abs(tot.at["single", "estimated_ibnr"] / tot.at["single", "actual_ibnr"] - 1) > 0.05

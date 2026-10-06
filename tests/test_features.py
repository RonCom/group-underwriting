import pandas as pd

from group_underwriting.pipelines.features.nodes import FEATURES, build_features


def _claims():
    return pd.DataFrame(
        {
            "member_id": ["m1"] * 4,
            "claim_id": ["a", "b", "c", "d"],
            "source": ["IP", "RX", "CAR", "OP"],
            "from_dt": pd.to_datetime(["2008-03-01", "2008-12-20", "2008-12-28", "2009-05-01"]),
            "thru_dt": pd.to_datetime(["2008-03-05", "2008-12-20", "2008-12-28", "2009-05-01"]),
            # c is paid 4 months after the 2008 cutoff, so it is not visible with 3 months of runout
            "paid_dt": pd.to_datetime(["2008-04-15", "2008-12-22", "2009-04-30", "2009-06-01"]),
            "allowed": [10000.0, 50.0, 300.0, 700.0],
            "ip_days": [4.0, 0, 0, 0],
            "ndc": [None, "123", None, None],
        }
    )


def _groups():
    row = {
        "member_id": "m1",
        "split": "train",
        "feature_year": 2008,
        "group_id": "TR0000",
        "group_size": 60,
        "size_band": "50-99",
        "state": 1,
        "county": 1,
        "target_months": 12,
        "birth_dt": pd.Timestamp("1938-12-31"),
        "sex": 2,
        "esrd": False,
        "months_ab": 12,
        "months_d": 12,
    }
    row.update(
        {
            c: False
            for c in FEATURES
            if c
            in {
                "alzheimers",
                "chf",
                "ckd",
                "cancer",
                "copd",
                "depression",
                "diabetes",
                "ischemic_heart",
                "osteoporosis",
                "ra_oa",
                "stroke",
            }
        }
    )
    return pd.DataFrame([row])


def test_features_respect_cutoff_and_runout():
    f = build_features(
        _claims(), _groups(), {"runout_months": 3, "specialty_rx_threshold": 1000}
    ).iloc[0]
    assert f["cost_total"] == 10050  # late-paid carrier claim and 2009 claim excluded
    assert f["cost_car"] == 0
    assert f["n_ip_stays"] == 1 and f["ip_days"] == 4
    assert f["target_cost"] == 700
    assert round(f["age"]) == 70
    assert f["female"] == 1

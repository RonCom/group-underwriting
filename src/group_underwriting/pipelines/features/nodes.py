"""Point-in-time member features, next-year targets, out-of-time cohorts and employer groups.

Features for feature year Y are built as of the cutoff Y-12-31 from claims incurred in Y and
paid no later than `runout_months` after the cutoff. Targets use every claim incurred in Y+1.

Members are split once, by a hash of their ID, into a training cohort and a test cohort. The
training rows are (training cohort, Y=2008 -> 2009); the test rows are (test cohort, Y=2009 -> 2010),
so no member is in both and test is a later period.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..ingest.nodes import CHRONIC_COLS

log = logging.getLogger(__name__)

CHRONIC = list(CHRONIC_COLS.values())
SOURCES = ["IP", "OP", "CAR", "RX"]
CLAIM_FEATURES = [f"cost_{s.lower()}" for s in SOURCES] + [
    "cost_total",
    "cost_h2",
    "max_claim",
    "n_ip_stays",
    "ip_days",
    "n_op",
    "n_car",
    "n_rx",
    "n_ndc",
    "n_specialty_rx",
    "months_with_claims",
]
FEATURES = [
    "age",
    "female",
    "esrd",
    "months_ab",
    "months_d",
    *CHRONIC,
    "n_chronic",
    *CLAIM_FEATURES,
]


def _hash_unit(ids: pd.Series, salt: str) -> np.ndarray:
    """Stable value in [0, 1) per ID."""
    h = pd.util.hash_pandas_object(ids, index=False, hash_key=salt.ljust(16, "0")[:16])
    return (h.to_numpy() % 10_000) / 10_000


def build_cohorts(members: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Eligible (member, feature year) rows with their split.

    Eligible: present in the summary file for Y and Y+1, no HMO months in either year (HMO
    members have no fee-for-service claims), and Parts A and B for at least one month in Y+1.
    """
    m = members.copy()
    m["months_ab"] = m[["months_a", "months_b"]].min(axis=1).clip(0, 12)
    nxt = m[["member_id", "year", "months_ab", "months_hmo"]].copy()
    nxt["year"] -= 1
    df = m.merge(nxt, on=["member_id", "year"], suffixes=("", "_next"))
    df = df[(df["months_hmo"] == 0) & (df["months_hmo_next"] == 0) & (df["months_ab_next"] > 0)]
    df["split"] = np.where(
        _hash_unit(df["member_id"], params["split_salt"]) < params["train_share"], "train", "test"
    )
    keep = ((df["split"] == "train") & (df["year"] == params["train_year"])) | (
        (df["split"] == "test") & (df["year"] == params["test_year"])
    )
    df = df[keep].rename(columns={"year": "feature_year", "months_ab_next": "target_months"})
    log.info("Cohort rows: %s", df.groupby("split").size().to_dict())
    return df.drop(columns=["months_hmo_next"]).reset_index(drop=True)


def assign_groups(cohorts: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Cut each split into synthetic employer groups.

    Members are ordered by state, county and a hash, then cut into consecutive blocks whose sizes
    are drawn from the configured size bands, so groups are geographically local like real
    employers. The last block of each split is merged into the one before it if it is smaller
    than the smallest band.
    """
    rng = np.random.default_rng(params["seed"])
    bands = params["size_bands"]
    weights = np.array([b["weight"] for b in bands], float)
    weights /= weights.sum()
    out = []
    for split, d in cohorts.groupby("split", sort=True):
        d = d.assign(_h=_hash_unit(d["member_id"], params["salt"]))
        d = d.sort_values(["state", "county", "_h"]).reset_index(drop=True)
        sizes = []
        while sum(sizes) < len(d):
            b = bands[rng.choice(len(bands), p=weights)]
            sizes.append(int(rng.integers(b["min"], b["max"] + 1)))
        sizes[-1] = len(d) - sum(sizes[:-1])
        if sizes[-1] < bands[0]["min"] and len(sizes) > 1:
            last = sizes.pop()
            sizes[-1] += last
        gid = np.repeat(np.arange(len(sizes)), sizes)
        d["group_id"] = [f"{split[:2].upper()}{g:04d}" for g in gid]
        out.append(d.drop(columns="_h"))
    df = pd.concat(out, ignore_index=True)
    size = df.groupby("group_id")["member_id"].transform("size")
    edges = [b["min"] for b in bands] + [np.inf]
    labels = [f"{b['min']}-{b['max']}" for b in bands]
    df["group_size"] = size
    df["size_band"] = pd.cut(size, edges, right=False, labels=labels).astype(str)
    log.info("Groups: %s", df.groupby("split")["group_id"].nunique().to_dict())
    return df


def _claim_features(c: pd.DataFrame, specialty_threshold: float) -> pd.DataFrame:
    src = c["source"].astype(str)
    c = c.assign(
        h2=c["from_dt"].dt.month >= 7,
        svc_month=c["from_dt"].dt.month,
        is_ip=src == "IP",
        is_op=src == "OP",
        is_car=src == "CAR",
        is_rx=src == "RX",
    )
    g = c.groupby("member_id")
    f = pd.DataFrame(
        {
            "cost_total": g["allowed"].sum(),
            "max_claim": g["allowed"].max(),
            "months_with_claims": g["svc_month"].nunique(),
        }
    )
    for s in SOURCES:
        f[f"cost_{s.lower()}"] = c[src == s].groupby("member_id")["allowed"].sum()
    f["cost_h2"] = c[c["h2"]].groupby("member_id")["allowed"].sum()
    f["n_ip_stays"] = g["is_ip"].sum()
    f["ip_days"] = g["ip_days"].sum()
    f["n_op"] = g["is_op"].sum()
    f["n_car"] = g["is_car"].sum()
    f["n_rx"] = g["is_rx"].sum()
    rx = c[c["is_rx"]]
    f["n_ndc"] = rx.groupby("member_id")["ndc"].nunique()
    f["n_specialty_rx"] = (rx["allowed"] > specialty_threshold).groupby(rx["member_id"]).sum()
    return f


def build_features(claims: pd.DataFrame, groups: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Features as of each row's cutoff, plus next-year allowed cost."""
    claims = claims.assign(
        from_dt=pd.to_datetime(claims["from_dt"]), paid_dt=pd.to_datetime(claims["paid_dt"])
    )
    rows = []
    for year, d in groups.groupby("feature_year"):
        cutoff = pd.Timestamp(f"{year}-12-31")
        visible_by = cutoff + pd.DateOffset(months=params["runout_months"])
        c = claims[claims["member_id"].isin(d["member_id"])]
        past = c[(c["from_dt"].dt.year == year) & (c["paid_dt"] <= visible_by)]
        nxt = c[c["from_dt"].dt.year == year + 1]
        f = _claim_features(past, params["specialty_rx_threshold"])
        target = nxt.groupby("member_id")["allowed"].sum().rename("target_cost")
        d = d.set_index("member_id").join(f).join(target)
        d["valuation_date"] = visible_by
        rows.append(d.reset_index())
    df = pd.concat(rows, ignore_index=True)

    df[CLAIM_FEATURES] = df[CLAIM_FEATURES].fillna(0)
    df["target_cost"] = df["target_cost"].fillna(0)
    cutoff = pd.to_datetime(df["feature_year"].astype(str) + "-12-31")
    df["age"] = (cutoff - pd.to_datetime(df["birth_dt"])).dt.days / 365.25
    df["female"] = (df["sex"] == 2).astype(int)
    df["esrd"] = df["esrd"].fillna(False).astype(int)
    df["months_d"] = df["months_d"].fillna(0).clip(0, 12)
    df[CHRONIC] = df[CHRONIC].fillna(False).astype(int)
    df["n_chronic"] = df[CHRONIC].sum(axis=1)
    df["exposure"] = df["target_months"] / 12
    df["target_rate"] = df["target_cost"] / df["exposure"]
    keep = [
        "member_id",
        "split",
        "feature_year",
        "group_id",
        "group_size",
        "size_band",
        "state",
        "county",
        "valuation_date",
        "target_months",
        "exposure",
        "target_cost",
        "target_rate",
        *FEATURES,
    ]
    log.info("Features: %d rows, %d columns", len(df), len(FEATURES))
    return df[keep].sort_values(["split", "group_id", "member_id"]).reset_index(drop=True)


def estimate_trend(
    claims: pd.DataFrame, members: pd.DataFrame, cohorts: dict, params: dict
) -> pd.DataFrame:
    """Annual cost trend from train_year to test_year PMPM, both at the same runout.

    Uses every fee-for-service member-month (open population), so it only needs data visible at
    the test cutoff plus `runout_months`. Predictions for the test year are multiplied by it.
    """
    years = [cohorts["train_year"], cohorts["test_year"]]
    mm = members[members["months_hmo"] == 0]
    mm = mm.assign(months=mm[["months_a", "months_b"]].min(axis=1).clip(0, 12))
    ffs = mm[["member_id", "year"]]
    c = claims.assign(year=pd.to_datetime(claims["from_dt"]).dt.year)
    c = c[c["year"].isin(years)].merge(ffs, on=["member_id", "year"])
    visible = pd.to_datetime(c["year"].astype(str) + "-12-31") + pd.DateOffset(
        months=params["runout_months"]
    )
    c = c[pd.to_datetime(c["paid_dt"]) <= visible]
    pmpm = (
        c.groupby("year")["allowed"].sum()
        / mm[mm["year"].isin(years)].groupby("year")["months"].sum()
    )
    out = pd.DataFrame(
        [
            {
                "base_year": years[0],
                "next_year": years[1],
                "pmpm_base": pmpm[years[0]],
                "pmpm_next": pmpm[years[1]],
                "trend": pmpm[years[1]] / pmpm[years[0]],
            }
        ]
    )
    log.info("Trend %d -> %d: %.3f", years[0], years[1], out["trend"].iloc[0])
    return out

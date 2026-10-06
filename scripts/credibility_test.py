"""Credibility blending of group experience with the manual rate (docs/preregistration_credibility.md).

    uv run python scripts/credibility_test.py fit    # fit on Samples 3-6, write docs/credibility/frozen.json
    uv run python scripts/credibility_test.py test   # score Sample 7 with the frozen constants

Experience: a group's prior-year (feature-year) allowed cost per member-month, as visible at the
pricing date. Projected experience = c x experience. Blended rate = Z x projected experience +
(1 - Z) x manual rate, Z = n / (n + k), n = prior-year member-months. c and k are fitted on seen
samples by weighted least squares on group cost per member-month.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from group_underwriting.metrics import cluster_bootstrap

FIT_SAMPLES, TEST_SAMPLE = [3, 4, 5, 6], 7
FROZEN = Path("docs/credibility/frozen.json")
AGE_EDGES = [0, 45, 55, 65, 70, 75, 80, 85, 200]
LEVEL = float(
    pd.read_parquet("data/real/07_model_output/level_calibration.parquet")
    .set_index("model")
    .at["gbm", "factor"]
)


def members(s: int) -> pd.DataFrame:
    f = pd.read_parquet(f"data/sample{s}/04_feature/features.parquet")
    p = pd.read_parquet(f"data/sample{s}/07_model_output/predictions.parquet")
    d = f.merge(p[["member_id", "pred_gbm"]], on="member_id")
    d["sample"] = s
    d["cell"] = pd.cut(d["age"], AGE_EDGES).astype(str) + "_" + d["female"].astype(str)
    return d


def groups(d: pd.DataFrame, manual: pd.Series) -> pd.DataFrame:
    d = d.assign(mu=manual * d["target_months"])
    g = d.groupby(["sample", "group_id"], as_index=False).agg(
        prior=("cost_total", "sum"),
        prior_mm=("months_ab", "sum"),
        mu=("mu", "sum"),
        actual=("target_cost", "sum"),
        mm=("target_months", "sum"),
    )
    g["M"], g["A"], g["E"] = g["mu"] / g["mm"], g["actual"] / g["mm"], g["prior"] / g["prior_mm"]
    return g


def manual_rates(d: pd.DataFrame, table: dict) -> dict[str, pd.Series]:
    # both per member-month: the cost model predicts an annual rate
    return {
        "record": d["pred_gbm"] * LEVEL / 12,
        "demographic": d["cell"].map(table["demographic"]),
    }


def fit_ck(g: pd.DataFrame) -> tuple[float, float]:
    c = (g["actual"].sum() / g["mm"].sum()) / (g["prior"].sum() / g["prior_mm"].sum())
    best = None
    for k in np.logspace(2, 7, 200):
        z = g["prior_mm"] / (g["prior_mm"] + k)
        err = np.average((z * c * g["E"] + (1 - z) * g["M"] - g["A"]) ** 2, weights=g["mm"])
        if best is None or err < best[1]:
            best = (float(k), err)
    return float(c), best[0]


def fit() -> None:
    d = pd.concat([members(s) for s in FIT_SAMPLES])
    demo = d.groupby("cell").apply(lambda x: x["target_cost"].sum() / x["target_months"].sum())
    table = {"demographic": demo.to_dict()}
    rates = manual_rates(d, table)
    out = {
        "fit_samples": FIT_SAMPLES,
        "level_factor": LEVEL,
        "demographic_table": table["demographic"],
    }
    for arm, m in rates.items():
        c, k = fit_ck(groups(d, m))
        out[arm] = {"c": c, "k": k}
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    FROZEN.write_text(json.dumps(out, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({a: out[a] for a in ("record", "demographic")}, indent=2))


def test() -> None:
    fz = json.loads(FROZEN.read_text(encoding="utf-8"))
    d = members(TEST_SAMPLE)
    seen = pd.concat(
        [
            pd.read_parquet(f, columns=["member_id"])
            for f in [
                "data/real/02_intermediate/members.parquet",
                *[f"data/sample{s}/02_intermediate/members.parquet" for s in FIT_SAMPLES],
            ]
        ]
    )
    if d["member_id"].isin(seen["member_id"]).any():
        raise ValueError("Test members overlap seen samples")
    rates = manual_rates(d, {"demographic": pd.Series(fz["demographic_table"])})
    G = {}
    for arm, m in rates.items():
        g = groups(d, m)
        z = g["prior_mm"] / (g["prior_mm"] + fz[arm]["k"])
        g["Z"], g["P"] = z, z * fz[arm]["c"] * g["E"] + (1 - z) * g["M"]
        G[arm] = g
    both = G["record"][["group_id", "mm", "A", "M", "P", "actual", "mu"]].merge(
        G["demographic"][["group_id", "M", "P"]], on="group_id", suffixes=("", "_demo")
    )

    def stat(x):
        w = x["mm"]

        def mae(col):
            return np.average(np.abs(x[col] - x["A"]), weights=w)

        r, rb, dm, db = mae("M"), mae("P"), mae("M_demo"), mae("P_demo")
        return {
            "record_manual": r,
            "record_blend": rb,
            "record_change": rb / r - 1,
            "demo_manual": dm,
            "demo_blend": db,
            "demo_change": db / dm - 1,
            "record_minus_demo_blend": r - db,
            "record_blend_ae": x["actual"].sum() / (x["P"] * x["mm"]).sum(),
        }

    ci = cluster_bootstrap(both, "group_id", stat, 500, 9).set_index("metric")

    def f(m: str, fmt: str = "{:.3f}") -> str:
        r = ci.loc[m]
        return f"{fmt.format(r['estimate'])} [{fmt.format(r['lo'])}–{fmt.format(r['hi'])}]"

    L = [
        f"# Credibility test (Sample {TEST_SAMPLE})",
        "",
        "Generated by `scripts/credibility_test.py test`. Predictions: "
        "`docs/preregistration_credibility.md`. Constants frozen in `docs/credibility/frozen.json`.",
        "",
        f"{len(d):,} members (none in Samples 2–6), {both.shape[0]} groups. Intervals resample groups.",
        "",
        "| Manual rate | k (member-months) | Median Z | Group PMPM MAE, manual | MAE, blended | Change |",
        "|---|---|---|---|---|---|",
        f"| Model of record | {fz['record']['k']:,.0f} | {G['record']['Z'].median():.3f} | "
        f"{f('record_manual', '${:.2f}')} | {f('record_blend', '${:.2f}')} | {f('record_change', '{:+.1%}')} |",
        f"| Demographic (age band × sex) | {fz['demographic']['k']:,.0f} | {G['demographic']['Z'].median():.3f} | "
        f"{f('demo_manual', '${:.2f}')} | {f('demo_blend', '${:.2f}')} | {f('demo_change', '{:+.1%}')} |",
        "",
        f"Model of record MAE minus blended demographic MAE: {f('record_minus_demo_blend', '${:.2f}')}.",
        f"Blended model-of-record claims A/E: {f('record_blend_ae')}.",
        "",
    ]
    out = Path("docs/credibility/results.md")
    out.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    {"fit": fit, "test": test}[sys.argv[1]]()

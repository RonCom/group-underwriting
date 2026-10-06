"""Post-hoc diagnostic on already-seen Samples 3-5: is the simulated group net-claims spread right?

Run from the repo root after the main, followup, retest and holdout runs:
    uv run python scripts/aggregate_diagnostic.py
"""

import pickle

import pandas as pd
import yaml

from group_underwriting.pipelines.pricing.nodes import build_residual_pool, price_variants
from group_underwriting.pipelines.tail.nodes import expected_excess, spliced_excess

P = yaml.safe_load(
    open("conf/base/parameters.yml")
    .read()
    .replace("${runtime_params:data_root,${globals:data_root}}", "data/real")
)
cost = pickle.load(open("data/real/06_models/cost_models.pkl", "rb"))
cal = pd.read_parquet("data/real/07_model_output/level_calibration.parquet")
tail = pd.read_parquet("data/real/07_model_output/tail_fit.parquet")
upper = pd.read_parquet("data/real/07_model_output/upper_tail_fit.parquet")
k = float(cal.set_index("model").at["gbm", "factor"])
pricing = {**P["pricing"], "n_sims": 1000}
variants = {
    "tweedie": {
        "label": "t",
        "cost": "gbm",
        "claimant": "glm",
        "tail": "spliced",
        "calibrate": True,
    },
    "empirical": {
        "label": "e",
        "cost": "gbm",
        "claimant": "glm",
        "tail": "spliced",
        "calibrate": True,
        "simulation": "empirical",
    },
}
samples = {s: f"data/sample{s}" for s in (3, 4, 5)}
rows = []
for s, root in samples.items():
    f = pd.read_parquet(f"{root}/04_feature/features.parquet")
    pr = pd.read_parquet(f"{root}/07_model_output/predictions.parquet")
    att = P["attachment_points"]
    single = expected_excess(pr, tail, att)
    spl = spliced_excess(pr, tail, upper, att)
    others = [f"data/sample{o}/07_model_output/predictions.parquet" for o in samples if o != s]
    pool = build_residual_pool({"files": others, "cost": "gbm", "level_factor": k, "n_bands": 10})
    out = price_variants(f, pr, single, spl, cost, cal, variants, pricing, pool)
    for m, g in out.groupby("model"):
        rows.append(
            {
                "sample": s,
                "sim": m,
                "groups": len(g),
                "pit_var": g["pit"].var(),
                "z_var": (((g["actual_net"] - g["expected_net"]) / g["net_sim_sd"]) ** 2).mean(),
                "breaches": int((g["actual_aggregate"] > 0).sum()),
                "exp_breaches": g["p_aggregate_hit"].sum(),
                "exp_agg_pmpm": g["expected_aggregate"].sum() / g["member_months"].sum(),
            }
        )
r = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(r.round(4).to_string())
print("uniform PIT var = 0.0833")

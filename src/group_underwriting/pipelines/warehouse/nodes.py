"""Run dbt (DuckDB or Snowflake) and compare `mart.member_features` with the Kedro features.

Every (member, feature year) row and every shared column is compared. Floating-point sums can
differ in the last digits because SQL and pandas add in different orders, so values match when
|a - b| <= 1e-6 * max(1, |a|).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ..features.nodes import FEATURES

log = logging.getLogger(__name__)
DBT_DIR = Path(__file__).resolve().parents[4] / "dbt"


def run_dbt(features: pd.DataFrame, claims: pd.DataFrame, params: dict) -> str:
    """`dbt build` on the configured target. Inputs are only here to order the node.

    dbt runs in a subprocess so it releases the DuckDB file before the reconciliation reads it.
    """
    db_path = Path(params["db_path"]).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GU_DATA_ROOT": str(Path(params["data_root"]).resolve()),
        "GU_DB_PATH": str(db_path),
        "GU_DBT_TARGET": params["target"],
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    args = [
        sys.executable,
        "-c",
        "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        "--target",
        params["target"],
        "--vars",
        f"{{runout_months: {params['runout_months']}, "
        f"specialty_rx_threshold: {params['specialty_rx_threshold']}}}",
    ]
    res = subprocess.run(args, env=env, capture_output=True, text=True)
    log.info("dbt build:\n%s", res.stdout[-2000:])
    if res.returncode != 0:
        raise RuntimeError(f"dbt build failed on {params['target']}:\n{res.stdout[-4000:]}")
    return str(db_path)


def reconcile(features: pd.DataFrame, db_path: str, params: dict) -> pd.DataFrame:
    with duckdb.connect(db_path, read_only=True) as con:
        sql = con.execute("SELECT * FROM mart.member_features").df()
    key = ["member_id", "feature_year"]
    cols = [c for c in [*FEATURES, "target_cost"] if c in sql.columns]
    m = features[key + cols].merge(
        sql[key + cols], on=key, how="outer", suffixes=("_kedro", "_dbt"), indicator=True
    )
    both = m[m["_merge"] == "both"]
    rows = [
        {
            "column": "(rows)",
            "kedro_rows": len(features),
            "dbt_rows": len(sql),
            "matched_rows": len(both),
            "mismatches": int((m["_merge"] != "both").sum()),
            "max_abs_diff": np.nan,
        }
    ]
    for c in cols:
        a = both[f"{c}_kedro"].astype(float).to_numpy()
        b = both[f"{c}_dbt"].astype(float).to_numpy()
        diff = np.abs(a - b)
        bad = diff > 1e-6 * np.maximum(1, np.abs(a))
        rows.append(
            {
                "column": c,
                "kedro_rows": len(features),
                "dbt_rows": len(sql),
                "matched_rows": len(both),
                "mismatches": int(bad.sum()),
                "max_abs_diff": float(diff.max()) if len(diff) else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    status = "MATCH" if out["mismatches"].sum() == 0 else "MISMATCH"
    lines = [
        f"# Reconciliation: Kedro features vs dbt `mart.member_features` ({params['label']})",
        "",
        f"Target: {params['target']}. Status: **{status}**. {len(features):,} Kedro rows, "
        f"{len(sql):,} dbt rows, {len(cols)} columns compared.",
        "",
        "| Column | Matched rows | Mismatches | Max abs diff |",
        "|---|---|---|---|",
        *[
            f"| {r.column} | {r.matched_rows:,} | {r.mismatches} | {r.max_abs_diff:.2g} |"
            for r in out.itertuples()
        ],
        "",
    ]
    path = Path(params["report_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    log.info("Reconciliation %s: %s", status, path)
    if status != "MATCH" and params["fail_on_mismatch"]:
        raise ValueError(f"dbt and Kedro features differ; see {path}")
    return out

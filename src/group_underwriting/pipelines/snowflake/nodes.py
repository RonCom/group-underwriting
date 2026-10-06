"""Snowflake warehouse build and Snowflake-vs-DuckDB reconciliation.

Credentials come from environment variables (never from the repo): SNOWFLAKE_ACCOUNT,
SNOWFLAKE_USER and either SNOWFLAKE_PRIVATE_KEY (PEM text) or SNOWFLAKE_PRIVATE_KEY_PATH.
Role, warehouse and database default to the names in snowflake/setup.sql.
"""

from __future__ import annotations

import atexit
import csv
import logging
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..features.nodes import FEATURES
from ..warehouse.nodes import DBT_DIR

log = logging.getLogger(__name__)

RAW_TABLES = {
    "BENEFICIARY": "*Beneficiary_Summary_File*.csv",
    "INPATIENT": "*Inpatient_Claims*.csv",
    "OUTPATIENT": "*Outpatient_Claims*.csv",
    "CARRIER": "*Carrier_Claims*.csv",
    "PDE": "*Prescription_Drug_Events*.csv",
}


def _key_path() -> str:
    """Path to the private key, writing SNOWFLAKE_PRIVATE_KEY to a 0600 temp file if given.

    The temp file is deleted when the process exits.
    """
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        return os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
    if not pem:
        raise RuntimeError("Set SNOWFLAKE_PRIVATE_KEY (PEM text) or SNOWFLAKE_PRIVATE_KEY_PATH")
    pem = pem.replace("\\n", "\n").strip() + "\n"
    fd, path = tempfile.mkstemp(suffix=".p8")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(pem)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    atexit.register(lambda: Path(path).unlink(missing_ok=True))
    os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"] = path
    return path


def _settings(params: dict) -> dict:
    return {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ.get("SNOWFLAKE_USER", params["user"]),
        "role": os.environ.get("SNOWFLAKE_ROLE", params["role"]),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", params["warehouse"]),
        "database": os.environ.get("SNOWFLAKE_DATABASE", params["database"]),
    }


def _connect(params: dict):
    import snowflake.connector

    s = _settings(params)
    return snowflake.connector.connect(
        **s, authenticator="SNOWFLAKE_JWT", private_key_file=_key_path()
    )


def _header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def load_raw(params: dict) -> pd.DataFrame:
    """Create RAW tables (all VARCHAR plus FILENAME) and load every CSV through a stage."""
    raw = Path(params["raw_dir"])
    rows = []
    with _connect(params) as con:
        cur = con.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS RAW")
        cur.execute("CREATE STAGE IF NOT EXISTS RAW.GU_STAGE")
        cur.execute(
            "CREATE FILE FORMAT IF NOT EXISTS RAW.GU_CSV TYPE = CSV SKIP_HEADER = 1 "
            "FIELD_OPTIONALLY_ENCLOSED_BY = '\"' EMPTY_FIELD_AS_NULL = TRUE"
        )
        for table, pattern in RAW_TABLES.items():
            files = sorted(raw.glob(pattern))
            if not files:
                raise FileNotFoundError(f"No {pattern} in {raw}")
            cols = _header(files[0])
            ddl = ", ".join(f'"{c}" VARCHAR' for c in cols) + ", FILENAME VARCHAR"
            cur.execute(f"CREATE OR REPLACE TABLE RAW.{table} ({ddl})")
            cur.execute(f"REMOVE @RAW.GU_STAGE/{table}/")
            for f in files:
                cur.execute(
                    f"PUT 'file://{f.resolve()}' @RAW.GU_STAGE/{table}/ "
                    "AUTO_COMPRESS = TRUE PARALLEL = 8 OVERWRITE = TRUE"
                )
            select = ", ".join(f"${i + 1}" for i in range(len(cols)))
            target = ", ".join(f'"{c}"' for c in cols)
            cur.execute(
                f"COPY INTO RAW.{table} ({target}, FILENAME) FROM (SELECT {select}, "
                f"METADATA$FILENAME FROM @RAW.GU_STAGE/{table}/) FILE_FORMAT = RAW.GU_CSV"
            )
            n = cur.execute(f"SELECT COUNT(*) FROM RAW.{table}").fetchone()[0]
            rows.append({"table": f"RAW.{table}", "files": len(files), "rows": n})
            log.info("Loaded RAW.%s: %d rows from %d files", table, n, len(files))
    return pd.DataFrame(rows)


def load_kedro_inputs(
    claims: pd.DataFrame, member_groups: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """KEDRO.CLAIMS (simulated paid dates) and KEDRO.MEMBER_GROUPS, the inputs dbt can't rebuild."""
    tables = {
        "CLAIMS": pa.table(
            {
                "member_id": claims["member_id"].astype(str),
                "claim_id": claims["claim_id"].astype(str),
                "source": claims["source"].astype(str),
                "paid_dt": pd.to_datetime(claims["paid_dt"]).dt.date,
            }
        ),
        "MEMBER_GROUPS": pa.table(
            {
                "member_id": member_groups["member_id"].astype(str),
                "feature_year": member_groups["feature_year"].astype("int32"),
            }
        ),
    }
    ddl = {
        "CLAIMS": "member_id VARCHAR, claim_id VARCHAR, source VARCHAR, paid_dt DATE",
        "MEMBER_GROUPS": "member_id VARCHAR, feature_year INT",
    }
    rows = []
    with tempfile.TemporaryDirectory() as tmp, _connect(params) as con:
        cur = con.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS KEDRO")
        cur.execute("CREATE STAGE IF NOT EXISTS KEDRO.GU_STAGE")
        for name, t in tables.items():
            path = Path(tmp) / f"{name.lower()}.parquet"
            pq.write_table(t, path)
            cur.execute(f"CREATE OR REPLACE TABLE KEDRO.{name} ({ddl[name]})")
            cur.execute(f"PUT 'file://{path}' @KEDRO.GU_STAGE/{name}/ OVERWRITE = TRUE")
            cur.execute(
                f"COPY INTO KEDRO.{name} FROM @KEDRO.GU_STAGE/{name}/ "
                "FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE "
                "PURGE = TRUE"
            )
            n = cur.execute(f"SELECT COUNT(*) FROM KEDRO.{name}").fetchone()[0]
            rows.append({"table": f"KEDRO.{name}", "files": 1, "rows": n})
            log.info("Loaded KEDRO.%s: %d rows", name, n)
    return pd.DataFrame(rows)


def run_dbt_snowflake(
    raw_loaded: pd.DataFrame, kedro_loaded: pd.DataFrame, params: dict
) -> pd.DataFrame:
    s = _settings(params)
    env = {
        **os.environ,
        "GU_DBT_TARGET": "snowflake",
        "GU_DATA_ROOT": str(Path(params["data_root"]).resolve()),
        "SNOWFLAKE_ACCOUNT": s["account"],
        "SNOWFLAKE_USER": s["user"],
        "SNOWFLAKE_ROLE": s["role"],
        "SNOWFLAKE_WAREHOUSE": s["warehouse"],
        "SNOWFLAKE_DATABASE": s["database"],
        "SNOWFLAKE_PRIVATE_KEY_PATH": _key_path(),
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
        "snowflake",
        "--vars",
        f"{{runout_months: {params['runout_months']}, "
        f"specialty_rx_threshold: {params['specialty_rx_threshold']}}}",
    ]
    res = subprocess.run(args, env=env, capture_output=True, text=True)
    log.info("dbt build (snowflake):\n%s", res.stdout[-2000:])
    if res.returncode != 0:
        raise RuntimeError(f"dbt build failed on snowflake:\n{res.stdout[-4000:]}")
    return pd.DataFrame([{"target": "snowflake", "status": "success"}])


def compare_marts(dk: pd.DataFrame, sf: pd.DataFrame) -> pd.DataFrame:
    """Row and per-column mismatch counts between the DuckDB and Snowflake feature marts.

    Values match when |a - b| <= 1e-6 * max(1, |a|); rows are matched on member and year.
    """
    sf = sf.rename(columns=str.lower)
    key = ["member_id", "feature_year"]
    cols = [c for c in [*FEATURES, "target_cost"] if c in sf.columns and c in dk.columns]
    m = dk[key + cols].merge(
        sf[key + cols], on=key, how="outer", suffixes=("_duckdb", "_snowflake"), indicator=True
    )
    both = m[m["_merge"] == "both"]
    rows = [
        {
            "column": "(rows)",
            "duckdb_rows": len(dk),
            "snowflake_rows": len(sf),
            "mismatches": int((m["_merge"] != "both").sum()),
            "max_abs_diff": float("nan"),
        }
    ]
    for c in cols:
        a = both[f"{c}_duckdb"].astype(float).to_numpy()
        b = both[f"{c}_snowflake"].astype(float).to_numpy()
        diff = abs(a - b)
        bad = diff > 1e-6 * pd.Series(abs(a)).clip(lower=1).to_numpy()
        rows.append(
            {
                "column": c,
                "duckdb_rows": len(dk),
                "snowflake_rows": len(sf),
                "mismatches": int(bad.sum()),
                "max_abs_diff": float(diff.max()) if len(diff) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def reconcile_snowflake(dbt_done: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Compare MART.MEMBER_FEATURES in Snowflake with the DuckDB mart, every row and column.

    Writes the report, then raises if anything differs (unless `fail_on_mismatch` is false), so
    a mismatch fails the run.
    """
    with _connect(params) as con:
        sf = con.cursor().execute("SELECT * FROM MART.MEMBER_FEATURES").fetch_pandas_all()
    with duckdb.connect(params["duckdb_path"], read_only=True) as con:
        dk = con.execute("SELECT * FROM mart.member_features").df()
    out = compare_marts(dk, sf)
    n_cols = len(out) - 1
    status = "MATCH" if out["mismatches"].sum() == 0 else "MISMATCH"
    lines = [
        "# Reconciliation: Snowflake vs DuckDB `mart.member_features`",
        "",
        f"Status: **{status}**. {len(dk):,} DuckDB rows, {len(sf):,} Snowflake rows, "
        f"{n_cols} columns compared.",
        "",
        "| Column | Mismatches | Max abs diff |",
        "|---|---|---|",
        *[f"| {r.column} | {r.mismatches} | {r.max_abs_diff:.2g} |" for r in out.itertuples()],
        "",
    ]
    path = Path(params["report_file"])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    log.info("Snowflake reconciliation %s", status)
    if status != "MATCH" and params.get("fail_on_mismatch", True):
        raise ValueError(f"Snowflake and DuckDB feature marts differ; see {path}")
    return out

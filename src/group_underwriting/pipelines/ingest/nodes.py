"""Load DE-SynPUF CSVs with DuckDB into a member-year table and one claims table.

Allowed cost per claim (DE-SynPUF has no allowed amount on facility claims, so it is rebuilt from
what Medicare, the primary payer and the beneficiary paid):
- Inpatient: CLM_PMT_AMT + NCH_PRMRY_PYR_CLM_PD_AMT + Part A deductible + coinsurance + blood deductible
- Outpatient: CLM_PMT_AMT + NCH_PRMRY_PYR_CLM_PD_AMT + Part B deductible + coinsurance + blood deductible
- Carrier: sum of LINE_ALOWD_CHRG_AMT_1..13
- Part D: TOT_RX_CST_AMT

DE-SynPUF has no paid date, so one is simulated from a per-source lag distribution (see
`simulate_paid_dates` and docs/decisions.md).
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CHRONIC_COLS = {
    "SP_ALZHDMTA": "alzheimers",
    "SP_CHF": "chf",
    "SP_CHRNKIDN": "ckd",
    "SP_CNCR": "cancer",
    "SP_COPD": "copd",
    "SP_DEPRESSN": "depression",
    "SP_DIABETES": "diabetes",
    "SP_ISCHMCHT": "ischemic_heart",
    "SP_OSTEOPRS": "osteoporosis",
    "SP_RA_OA": "ra_oa",
    "SP_STRKETIA": "stroke",
}


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    return con


def _files(raw_dir: str, pattern: str) -> list[str]:
    files = sorted(str(p) for p in Path(raw_dir).glob(f"*{pattern}*.csv"))
    if not files:
        raise FileNotFoundError(f"No files matching *{pattern}*.csv in {raw_dir}")
    return files


def _read(con: duckdb.DuckDBPyConnection, files: list[str], name: str) -> list[str]:
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT * FROM read_csv({files!r}, "
        "all_varchar=true, header=true, filename=true, union_by_name=true)"
    )
    return [r[0] for r in con.execute(f"DESCRIBE {name}").fetchall()]


def _num(col: str, cols: list[str]) -> str:
    return f"COALESCE(TRY_CAST({col} AS DOUBLE), 0)" if col in cols else "0"


def _date(col: str) -> str:
    return f"TRY_STRPTIME(NULLIF(TRIM({col}), ''), '%Y%m%d')::DATE"


def load_members(raw_dir: str) -> pd.DataFrame:
    """One row per member and calendar year from the Beneficiary Summary files."""
    con = _connect()
    _read(con, _files(raw_dir, "Beneficiary_Summary_File"), "bene")
    flags = ",\n".join(f"TRY_CAST({c} AS INT) = 1 AS {name}" for c, name in CHRONIC_COLS.items())
    df = con.execute(f"""
        SELECT
            DESYNPUF_ID AS member_id,
            CAST(regexp_extract(filename, 'DE1_0_(\\d{{4}})_Beneficiary', 1) AS INT) AS year,
            {_date("BENE_BIRTH_DT")} AS birth_dt,
            {_date("BENE_DEATH_DT")} AS death_dt,
            TRY_CAST(BENE_SEX_IDENT_CD AS INT) AS sex,
            TRY_CAST(BENE_RACE_CD AS INT) AS race,
            BENE_ESRD_IND = 'Y' AS esrd,
            TRY_CAST(SP_STATE_CODE AS INT) AS state,
            TRY_CAST(BENE_COUNTY_CD AS INT) AS county,
            TRY_CAST(BENE_HI_CVRAGE_TOT_MONS AS INT) AS months_a,
            TRY_CAST(BENE_SMI_CVRAGE_TOT_MONS AS INT) AS months_b,
            TRY_CAST(BENE_HMO_CVRAGE_TOT_MONS AS INT) AS months_hmo,
            TRY_CAST(PLAN_CVRG_MOS_NUM AS INT) AS months_d,
            {flags}
        FROM bene
        ORDER BY member_id, year
    """).df()
    log.info("Loaded %d member-years", len(df))
    return df


def load_claims(raw_dir: str) -> pd.DataFrame:
    """Inpatient, outpatient, carrier and Part D claims in one table, one row per claim."""
    con = _connect()
    parts = []

    ip = _read(con, _files(raw_dir, "Inpatient_Claims"), "ip")
    parts.append(f"""
        SELECT DESYNPUF_ID AS member_id, CLM_ID AS claim_id, 'IP' AS source,
               MIN({_date("CLM_FROM_DT")}) AS from_dt, MAX({_date("CLM_THRU_DT")}) AS thru_dt,
               SUM({_num("CLM_PMT_AMT", ip)} + {_num("NCH_PRMRY_PYR_CLM_PD_AMT", ip)}
                   + {_num("NCH_BENE_IP_DDCTBL_AMT", ip)} + {_num("NCH_BENE_PTA_COINSRNC_LBLTY_AM", ip)}
                   + {_num("NCH_BENE_BLOOD_DDCTBL_LBLTY_AM", ip)}) AS allowed,
               SUM({_num("CLM_UTLZTN_DAY_CNT", ip)}) AS ip_days,
               NULL::VARCHAR AS ndc, MIN(ICD9_DGNS_CD_1) AS dx1
        FROM ip GROUP BY 1, 2
    """)

    op = _read(con, _files(raw_dir, "Outpatient_Claims"), "op")
    parts.append(f"""
        SELECT DESYNPUF_ID, CLM_ID, 'OP',
               MIN({_date("CLM_FROM_DT")}), MAX({_date("CLM_THRU_DT")}),
               SUM({_num("CLM_PMT_AMT", op)} + {_num("NCH_PRMRY_PYR_CLM_PD_AMT", op)}
                   + {_num("NCH_BENE_PTB_DDCTBL_AMT", op)} + {_num("NCH_BENE_PTB_COINSRNC_AMT", op)}
                   + {_num("NCH_BENE_BLOOD_DDCTBL_LBLTY_AM", op)}),
               0, NULL, MIN(ICD9_DGNS_CD_1)
        FROM op GROUP BY 1, 2
    """)

    car = _read(con, _files(raw_dir, "Carrier_Claims"), "car")
    lines = " + ".join(_num(f"LINE_ALOWD_CHRG_AMT_{j}", car) for j in range(1, 14))
    parts.append(f"""
        SELECT DESYNPUF_ID, CLM_ID, 'CAR',
               MIN({_date("CLM_FROM_DT")}), MAX({_date("CLM_THRU_DT")}),
               SUM({lines}), 0, NULL, MIN(ICD9_DGNS_CD_1)
        FROM car GROUP BY 1, 2
    """)

    rx = _read(con, _files(raw_dir, "Prescription_Drug_Events"), "rx")
    parts.append(f"""
        SELECT DESYNPUF_ID, PDE_ID, 'RX', {_date("SRVC_DT")}, {_date("SRVC_DT")},
               {_num("TOT_RX_CST_AMT", rx)}, 0, PROD_SRVC_ID, NULL
        FROM rx
    """)

    df = con.execute(
        "SELECT * FROM (" + " UNION ALL ".join(parts) + ") "
        "WHERE from_dt IS NOT NULL ORDER BY source, claim_id, member_id"
    ).df()
    df["allowed"] = df["allowed"].clip(lower=0)
    df["source"] = df["source"].astype("category")
    log.info("Loaded %d claims", len(df))
    return df


def simulate_paid_dates(claims: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Add a paid date = service end + lag, lag ~ min_days + Gamma(shape, mean/shape) per source.

    A share of claims (`late_share`) gets an extra uniform lag up to `late_max_days`, standing in
    for adjustments and coordination-of-benefits delays that make IBNR tails long.
    """
    rng = np.random.default_rng(params["seed"])
    lag = np.zeros(len(claims))
    src = claims["source"].astype(str).to_numpy()
    for s, p in params["lag"].items():
        m = src == s
        k = m.sum()
        lag[m] = p["min_days"] + rng.gamma(p["shape"], p["mean_days"] / p["shape"], k)
        late = rng.random(k) < p["late_share"]
        lag[np.flatnonzero(m)[late]] += rng.uniform(0, p["late_max_days"], late.sum())
    end = pd.to_datetime(claims["thru_dt"]).fillna(pd.to_datetime(claims["from_dt"]))
    out = claims.copy()
    out["paid_dt"] = (end + pd.to_timedelta(np.round(lag), unit="D")).astype("datetime64[s]")
    return out

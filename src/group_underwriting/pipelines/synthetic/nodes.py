"""Generate DE-SynPUF-shaped CSVs so the whole pipeline runs offline.

Files use the real DE-SynPUF file names and column names, restricted to the columns the ingest
step reads. Each member carries a persistent frailty score (AR(1) across years) that drives
chronic conditions, death and claim frequency, plus a catastrophic-claim process with a Pareto
tail. The numbers exercise the code paths; they are not estimates of real Medicare costs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

YEARS = (2008, 2009, 2010)
CHRONIC = {
    # column: (base log-odds at age 75, frailty loading)
    "SP_ALZHDMTA": (-2.2, 0.5),
    "SP_CHF": (-1.4, 0.6),
    "SP_CHRNKIDN": (-2.0, 0.6),
    "SP_CNCR": (-2.9, 0.3),
    "SP_COPD": (-2.2, 0.5),
    "SP_DEPRESSN": (-1.8, 0.4),
    "SP_DIABETES": (-0.7, 0.4),
    "SP_ISCHMCHT": (-0.5, 0.5),
    "SP_OSTEOPRS": (-1.9, 0.2),
    "SP_RA_OA": (-1.2, 0.3),
    "SP_STRKETIA": (-3.4, 0.5),
}
DX = ["4280", "41401", "25000", "4019", "496", "5849", "1749", "2724", "29680", "4359", "V5861"]


def _ymd(dates: pd.DatetimeIndex | pd.Series) -> np.ndarray:
    d = pd.DatetimeIndex(dates)
    return (d.year * 10000 + d.month * 100 + d.day).to_numpy().astype(str)


def _member_ids(rng: np.random.Generator, n: int) -> np.ndarray:
    return np.array([f"{x:016X}" for x in rng.integers(0, 2**63, n, dtype=np.int64)])


def _random_dates(rng: np.random.Generator, year: int, last_month: np.ndarray) -> pd.Series:
    """Uniform dates in [Jan 1, end of last_month] of `year`."""
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.to_datetime({"year": year, "month": last_month, "day": 1}) + pd.offsets.MonthEnd(0)
    span = (end - start).dt.days.to_numpy() + 1
    return start + pd.to_timedelta(np.floor(rng.random(len(span)) * span), unit="D")


def generate(params: dict) -> None:
    """Write synthetic beneficiary and claims files to `params['raw_dir']`."""
    rng = np.random.default_rng(params["seed"])
    n = params["n_members"]
    trend = params["annual_trend"]
    out = Path(params["raw_dir"])
    out.mkdir(parents=True, exist_ok=True)

    ids = _member_ids(rng, n)
    disabled = rng.random(n) < 0.15
    age08 = np.where(
        disabled,
        rng.integers(25, 65, n),
        np.minimum(65 + rng.exponential(10, n), 100).astype(int),
    )
    birth = pd.to_datetime({"year": 2008 - age08, "month": rng.integers(1, 13, n), "day": 1})
    sex = np.where(rng.random(n) < 0.55, 2, 1)
    race = rng.choice([1, 2, 3, 5], n, p=[0.82, 0.11, 0.03, 0.04])
    state = rng.choice(np.arange(1, 55), n, p=np.random.default_rng(1).dirichlet(np.ones(54)))
    county = rng.integers(0, 400, n)
    esrd = rng.random(n) < 0.02
    hmo = rng.random(n) < 0.10
    part_d = rng.random(n) < 0.75
    specialty = np.zeros(n, bool)

    z = rng.normal(0, 1, n)
    chronic = {c: np.zeros(n, bool) for c in CHRONIC}
    alive = np.ones(n, bool)
    bene_frames, ip, op, car, pde = [], [], [], [], []

    for y in YEARS:
        idx = np.flatnonzero(alive)
        m = len(idx)
        age = (y - 2008) + age08[idx]
        z[idx] = 0.8 * z[idx] + 0.6 * rng.normal(0, 1, m)
        zi = z[idx]
        for c, (b, load) in CHRONIC.items():
            p_on = 1 / (1 + np.exp(-(b - 2.5 + 0.03 * (age - 75) + load * zi)))
            if y == YEARS[0]:
                p_on = 1 / (1 + np.exp(-(b + 0.03 * (age - 75) + load * zi)))
            chronic[c][idx] |= rng.random(m) < p_on
        flags = {c: chronic[c][idx] for c in CHRONIC}
        n_chr = sum(f.astype(int) for f in flags.values())

        lp_death = (
            -5.2 + 0.07 * (age - 75) + 0.5 * zi + 0.6 * flags["SP_CHF"] + 0.8 * flags["SP_CNCR"]
        )
        dies = rng.random(m) < 1 / (1 + np.exp(-lp_death))
        months = np.where(dies, rng.integers(1, 13, m), 12)
        death_dt = np.where(dies, (y * 10000 + months * 100 + 15).astype(str), "")
        new_spec = (flags["SP_CNCR"] | flags["SP_RA_OA"]) & (rng.random(m) < 0.03)
        specialty[idx] |= new_spec & part_d[idx]

        bene = pd.DataFrame(
            {
                "DESYNPUF_ID": ids[idx],
                "BENE_BIRTH_DT": _ymd(birth[idx]),
                "BENE_DEATH_DT": death_dt,
                "BENE_SEX_IDENT_CD": sex[idx],
                "BENE_RACE_CD": race[idx],
                "BENE_ESRD_IND": np.where(esrd[idx], "Y", "0"),
                "SP_STATE_CODE": state[idx],
                "BENE_COUNTY_CD": county[idx],
                "BENE_HI_CVRAGE_TOT_MONS": months,
                "BENE_SMI_CVRAGE_TOT_MONS": months,
                "BENE_HMO_CVRAGE_TOT_MONS": np.where(hmo[idx], months, 0),
                "PLAN_CVRG_MOS_NUM": np.where(part_d[idx], months, 0),
                **{c: np.where(f, 1, 2) for c, f in flags.items()},
            }
        )
        bene_frames.append((y, bene))

        # Fee-for-service claims only for members not in an HMO.
        ffs = ~hmo[idx]

        def f(a, ffs=ffs):
            return a[ffs]

        mid, mz, mage, mmon, mesrd = f(ids[idx]), f(zi), f(age), f(months), f(esrd[idx])
        mflags = {c: f(v) for c, v in flags.items()}
        mchr = f(n_chr)
        exposure = mmon / 12
        price = trend ** (y - 2008)

        # Inpatient stays
        lam_ip = exposure * np.exp(
            -2.7
            + 0.45 * mz
            + 0.012 * (mage - 75)
            + 0.35 * mflags["SP_CHF"]
            + 0.3 * mflags["SP_CHRNKIDN"]
            + 0.3 * mflags["SP_COPD"]
            + 0.4 * mflags["SP_CNCR"]
            + 0.5 * mflags["SP_STRKETIA"]
            + 1.0 * mesrd
        )
        k = rng.poisson(lam_ip)
        if k.sum():
            r = np.repeat(np.arange(len(mid)), k)
            cost = rng.lognormal(np.log(9000), 0.75, len(r))
            cat = rng.random(len(r)) < 0.04 + 0.04 * (mz[r] > 1.5)
            cost[cat] += np.minimum(40000 * (rng.pareto(1.6, cat.sum()) + 1), 2_000_000)
            cost *= price
            adm = _random_dates(rng, y, mmon[r])
            days = np.clip(np.round(cost / 2500 * rng.uniform(0.6, 1.4, len(r))), 1, 120).astype(
                int
            )
            dis = adm + pd.to_timedelta(days, unit="D")
            ded = np.full(len(r), 1024.0)
            ip.append(
                pd.DataFrame(
                    {
                        "DESYNPUF_ID": mid[r],
                        "CLM_ID": rng.integers(10**14, 10**15, len(r)).astype(str),
                        "SEGMENT": 1,
                        "CLM_FROM_DT": _ymd(adm),
                        "CLM_THRU_DT": _ymd(dis),
                        "CLM_PMT_AMT": np.round(np.maximum(cost - ded, 0), -1),
                        "NCH_PRMRY_PYR_CLM_PD_AMT": 0.0,
                        "CLM_ADMSN_DT": _ymd(adm),
                        "NCH_BENE_IP_DDCTBL_AMT": ded,
                        "NCH_BENE_PTA_COINSRNC_LBLTY_AM": 0.0,
                        "NCH_BENE_BLOOD_DDCTBL_LBLTY_AM": 0.0,
                        "CLM_UTLZTN_DAY_CNT": days,
                        "NCH_BENE_DSCHRG_DT": _ymd(dis),
                        "ICD9_DGNS_CD_1": rng.choice(DX, len(r)),
                    }
                )
            )

        # Outpatient facility claims
        lam_op = exposure * np.exp(1.0 + 0.3 * mz + 0.15 * mchr + 2.0 * mesrd)
        k = rng.poisson(lam_op)
        r = np.repeat(np.arange(len(mid)), k)
        cost = rng.lognormal(np.log(220), 1.1, len(r)) * price
        dt = _random_dates(rng, y, mmon[r])
        op.append(
            pd.DataFrame(
                {
                    "DESYNPUF_ID": mid[r],
                    "CLM_ID": rng.integers(10**14, 10**15, len(r)).astype(str),
                    "SEGMENT": 1,
                    "CLM_FROM_DT": _ymd(dt),
                    "CLM_THRU_DT": _ymd(dt),
                    "CLM_PMT_AMT": np.round(cost * 0.8, -1),
                    "NCH_PRMRY_PYR_CLM_PD_AMT": 0.0,
                    "NCH_BENE_BLOOD_DDCTBL_LBLTY_AM": 0.0,
                    "NCH_BENE_PTB_DDCTBL_AMT": 0.0,
                    "NCH_BENE_PTB_COINSRNC_AMT": np.round(cost * 0.2, -1),
                    "ICD9_DGNS_CD_1": rng.choice(DX, len(r)),
                }
            )
        )

        # Carrier (professional) claims, up to 13 lines each
        lam_car = exposure * np.exp(2.0 + 0.25 * mz + 0.09 * mchr)
        k = rng.poisson(lam_car)
        r = np.repeat(np.arange(len(mid)), k)
        n_lines = np.minimum(rng.geometric(0.55, len(r)), 13)
        dt = _random_dates(rng, y, mmon[r])
        car_df = {
            "DESYNPUF_ID": mid[r],
            "CLM_ID": rng.integers(10**14, 10**15, len(r)).astype(str),
            "CLM_FROM_DT": _ymd(dt),
            "CLM_THRU_DT": _ymd(dt),
            "ICD9_DGNS_CD_1": rng.choice(DX, len(r)),
        }
        for j in range(1, 14):
            amt = np.round(rng.lognormal(np.log(70), 0.9, len(r)) * price, -1)
            car_df[f"LINE_ALOWD_CHRG_AMT_{j}"] = np.where(n_lines >= j, amt, np.nan)
            car_df[f"LINE_NCH_PMT_AMT_{j}"] = np.where(
                n_lines >= j, np.round(amt * 0.8, -1), np.nan
            )
        car.append(pd.DataFrame(car_df))

        # Part D fills; specialty-drug members fill monthly at ~$4k
        has_d = f(part_d[idx])
        lam_rx = exposure * has_d * np.exp(1.6 + 0.22 * mchr + 0.15 * mz)
        k = rng.poisson(lam_rx)
        spec = f(specialty[idx]) & has_d
        k_spec = np.where(spec, mmon, 0)
        r = np.repeat(np.arange(len(mid)), k)
        rs = np.repeat(np.arange(len(mid)), k_spec)
        cost = (
            np.concatenate(
                [
                    rng.lognormal(np.log(35), 1.1, len(r)),
                    rng.lognormal(np.log(4000), 0.3, len(rs)),
                ]
            )
            * price
        )
        rr = np.concatenate([r, rs])
        dt = _random_dates(rng, y, mmon[rr])
        ndc = np.concatenate(
            [
                rng.integers(0, 400, len(r)).astype(str),
                rng.integers(900, 910, len(rs)).astype(str),
            ]
        )
        pde.append(
            pd.DataFrame(
                {
                    "DESYNPUF_ID": mid[rr],
                    "PDE_ID": rng.integers(10**14, 10**15, len(rr)).astype(str),
                    "SRVC_DT": _ymd(dt),
                    "PROD_SRVC_ID": np.char.zfill(ndc, 11),
                    "QTY_DSPNSD_NUM": 30,
                    "DAYS_SUPLY_NUM": 30,
                    "PTNT_PAY_AMT": np.round(cost * 0.25, 2),
                    "TOT_RX_CST_AMT": np.round(cost, 2),
                }
            )
        )

        alive[idx[dies]] = False

    def write(df: pd.DataFrame, name: Path) -> None:
        duckdb.from_df(df).write_csv(str(name))

    for y, bene in bene_frames:
        write(bene, out / f"DE1_0_{y}_Beneficiary_Summary_File_Sample_1.csv")
    write(pd.concat(ip), out / "DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv")
    write(pd.concat(op), out / "DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.csv")
    car_all = pd.concat(car)
    half = len(car_all) // 2
    write(car_all.iloc[:half], out / "DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.csv")
    write(car_all.iloc[half:], out / "DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.csv")
    write(pd.concat(pde), out / "DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_1.csv")
    log.info("Wrote synthetic DE-SynPUF files for %d members to %s", n, out)

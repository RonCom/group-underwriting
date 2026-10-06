"""Chain-ladder completion factors on monthly paid triangles, checked against actual runout.

For each valuation date, the triangle holds claims incurred in the `history_months` before it,
by incurred month and payment lag in months, using only claims paid by the valuation date.
Age-to-age factors are volume-weighted over every incurred month that has both lags observed.
Because the simulated paid dates are known for every claim, the estimate can be compared with
the actual ultimate for each incurred month.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _month_index(d: pd.Series) -> pd.Series:
    return d.dt.year * 12 + d.dt.month - 1


def _factors(cum: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Volume-weighted age-to-age factors f_k = sum C[:, k+1] / sum C[:, k] where both observed."""
    n_lag = cum.shape[1]
    f = np.ones(n_lag - 1)
    for k in range(n_lag - 1):
        both = observed[:, k + 1]
        den = cum[both, k].sum()
        if den > 0:
            f[k] = cum[both, k + 1].sum() / den
    return f


def _chain_ladder(claims: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = claims.assign(
        inc=_month_index(pd.to_datetime(claims["from_dt"])),
        paid=_month_index(pd.to_datetime(claims["paid_dt"])),
    )
    c["lag"] = (c["paid"] - c["inc"]).clip(lower=0)
    max_lag = params["max_lag_months"]
    c["lag"] = c["lag"].clip(upper=max_lag)
    factor_rows, result_rows = [], []
    for val in params["valuation_dates"]:
        v = _month_index(pd.Series([pd.Timestamp(val)]))[0]
        months = np.arange(v - params["history_months"] + 1, v + 1)
        d = c[c["inc"].isin(months)]
        actual = d.groupby("inc")["allowed"].sum().reindex(months, fill_value=0)
        seen = d[d["paid"] <= v]
        tri = (
            seen.pivot_table(index="inc", columns="lag", values="allowed", aggfunc="sum")
            .reindex(index=months, columns=range(max_lag + 1))
            .fillna(0)
        )
        cum = tri.to_numpy().cumsum(axis=1)
        age = v - months  # latest observed lag per incurred month
        observed = np.arange(max_lag + 1)[None, :] <= age[:, None]
        f = _factors(cum, observed)
        to_ult = np.append(np.cumprod(f[::-1])[::-1], 1.0)
        completion = 1 / to_ult
        paid_to_date = cum[np.arange(len(months)), np.minimum(age, max_lag)]
        est_ult = paid_to_date * to_ult[np.minimum(age, max_lag)]
        factor_rows.append(
            pd.DataFrame(
                {
                    "valuation_date": val,
                    "lag_months": np.arange(max_lag + 1),
                    "completion": completion,
                }
            )
        )
        result_rows.append(
            pd.DataFrame(
                {
                    "valuation_date": val,
                    "incurred_month": [f"{m // 12}-{m % 12 + 1:02d}" for m in months],
                    "lag_at_valuation": age,
                    "paid_to_date": paid_to_date,
                    "estimated_ultimate": est_ult,
                    "actual_ultimate": actual.to_numpy(),
                }
            )
        )
    res = pd.concat(result_rows, ignore_index=True)
    res["estimated_ibnr"] = res["estimated_ultimate"] - res["paid_to_date"]
    res["actual_ibnr"] = res["actual_ultimate"] - res["paid_to_date"]
    return pd.concat(factor_rows, ignore_index=True), res


def estimate_ibnr(claims: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Completion factors (single triangle) and IBNR estimates per method.

    Methods (`params["methods"]`, default both): `single`, one triangle over all claims;
    `by_source`, one triangle per claim type with estimates summed by incurred month.
    """
    factors, single = _chain_ladder(claims, params)
    out = [single.assign(method="single")]
    methods = params.get("methods", ["single", "by_source"])
    if "by_source" in methods and "source" in claims.columns:
        parts = [_chain_ladder(d, params)[1] for _, d in claims.groupby("source", observed=True)]
        keys = ["valuation_date", "incurred_month", "lag_at_valuation"]
        summed = pd.concat(parts).groupby(keys, as_index=False).sum(numeric_only=True)
        out.append(summed.assign(method="by_source"))
    return factors, pd.concat(out, ignore_index=True)

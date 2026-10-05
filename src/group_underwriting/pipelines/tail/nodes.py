"""Generalized Pareto tail above a threshold and expected excess loss per member.

The GPD is fit to training members' next-year (2009) annual allowed cost above `threshold`.
A member's expected loss above a specific deductible d >= threshold is

    E[(X - d)+] = P(X > u) * E[(Y - (d - u))+],   Y ~ GPD(xi, sigma)

with P(X > u) from that member's high-cost claimant model at u (so the threshold must be one of
the attachment points), and for xi < 1

    E[(Y - t)+] = (sigma + xi * t) / (1 - xi) * (1 + xi * t / sigma) ** (-1 / xi).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats

log = logging.getLogger(__name__)


def gpd_stop_loss(t: np.ndarray | float, xi: float, sigma: float) -> np.ndarray:
    """E[(Y - t)+] for Y ~ GPD(xi, sigma), t >= 0."""
    t = np.asarray(t, float)
    if xi >= 1:
        raise ValueError(f"GPD shape {xi:.2f} >= 1: excess mean is infinite")
    if abs(xi) < 1e-6:
        return sigma * np.exp(-t / sigma)
    surv = np.clip(1 + xi * t / sigma, 0, None) ** (-1 / xi)
    return (sigma + xi * t) / (1 - xi) * surv


def fit_tail(
    features: pd.DataFrame, params: dict
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit the GPD; return the fit, a mean-excess table and QQ points."""
    x = features.loc[features["split"] == "train", "target_cost"].to_numpy()
    u = params["threshold"]
    exc = x[x > u] - u
    xi, _, sigma = stats.genpareto.fit(exc, floc=0)
    fit = pd.DataFrame(
        [
            {
                "threshold": u,
                "xi": xi,
                "sigma": sigma,
                "n_exceed": len(exc),
                "n": len(x),
                "p_exceed": len(exc) / len(x),
                "ks_pvalue": stats.kstest(exc, "genpareto", args=(xi, 0, sigma)).pvalue,
            }
        ]
    )
    log.info("GPD above %s: xi=%.3f sigma=%.0f (%d exceedances)", u, xi, sigma, len(exc))

    pos = np.sort(x[x > 0])
    grid = np.quantile(pos, np.linspace(0.5, 0.995, 60))
    me = pd.DataFrame(
        {
            "threshold": grid,
            "mean_excess": [np.mean(pos[pos > g] - g) for g in grid],
            "n_above": [int(np.sum(pos > g)) for g in grid],
        }
    )
    q = (np.arange(1, len(exc) + 1) - 0.5) / len(exc)
    qq = pd.DataFrame(
        {
            "empirical": np.sort(exc) + u,
            "gpd": stats.genpareto.ppf(q, xi, 0, sigma) + u,
        }
    )
    return fit, me, qq


def expected_excess(
    predictions: pd.DataFrame, tail_fit: pd.DataFrame, attachments: list[float], model: str
) -> pd.DataFrame:
    """Per-member expected and actual loss above each attachment point."""
    f = tail_fit.iloc[0]
    u = f["threshold"]
    if int(u) not in [int(a) for a in attachments]:
        raise ValueError(f"Tail threshold {u} must be one of the attachment points {attachments}")
    p_u = predictions[f"p_{model}_{int(u)}"].to_numpy()
    out = predictions[["member_id", "split", "group_id", "target_cost"]].copy()
    for d in attachments:
        if d < u:
            continue
        out[f"exp_excess_{int(d)}"] = p_u * gpd_stop_loss(d - u, f["xi"], f["sigma"])
        out[f"act_excess_{int(d)}"] = np.clip(out["target_cost"] - d, 0, None)
    return out

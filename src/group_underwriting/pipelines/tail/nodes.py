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
    predictions: pd.DataFrame, tail_fit: pd.DataFrame, attachments: list[float]
) -> pd.DataFrame:
    """Per-member expected (per HCC model) and actual loss above each attachment point."""
    f = tail_fit.iloc[0]
    u = f["threshold"]
    if int(u) not in [int(a) for a in attachments]:
        raise ValueError(f"Tail threshold {u} must be one of the attachment points {attachments}")
    out = predictions[["member_id", "split", "group_id", "target_cost"]].copy()
    for d in attachments:
        if d < u:
            continue
        excess_above_u = gpd_stop_loss(d - u, f["xi"], f["sigma"])
        for m in ("glm", "gbm"):
            out[f"exp_excess_{m}_{int(d)}"] = predictions[f"p_{m}_{int(u)}"] * excess_above_u
        out[f"act_excess_{int(d)}"] = np.clip(out["target_cost"] - d, 0, None)
    return out


def gpd_survival(t: np.ndarray | float, xi: float, sigma: float) -> np.ndarray:
    t = np.asarray(t, float)
    if abs(xi) < 1e-6:
        return np.exp(-t / sigma)
    return np.clip(1 + xi * t / sigma, 0, None) ** (-1 / xi)


def fit_upper_tail(
    train_features: pd.DataFrame, calibration_features: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """Second GPD above `upper_threshold`, fit to pooled annual cost from already-seen data."""
    x = np.concatenate(
        [
            train_features.loc[train_features["split"] == "train", "target_cost"].to_numpy(),
            calibration_features["target_cost"].to_numpy(),
        ]
    )
    u2 = params["upper_threshold"]
    exc = x[x > u2] - u2
    xi, _, sigma = stats.genpareto.fit(exc, floc=0)
    log.info("Upper GPD above %s: xi=%.3f sigma=%.0f (%d exceedances)", u2, xi, sigma, len(exc))
    return pd.DataFrame(
        [
            {
                "threshold": u2,
                "xi": xi,
                "sigma": sigma,
                "n_exceed": len(exc),
                "n": len(x),
                "ks_pvalue": stats.kstest(exc, "genpareto", args=(xi, 0, sigma)).pvalue,
            }
        ]
    )


def spliced_excess(
    predictions: pd.DataFrame,
    tail_fit: pd.DataFrame,
    upper_fit: pd.DataFrame,
    attachments: list[float],
) -> pd.DataFrame:
    """Expected excess with the lower GPD up to the upper threshold and the upper GPD beyond.

    S(x) = p S1(x - u) on [u, u2) and p S1(u2 - u) S2(x - u2) above u2; E[(X - d)+] = ∫_d^∞ S.
    """
    f1, f2 = tail_fit.iloc[0], upper_fit.iloc[0]
    u, u2 = f1["threshold"], f2["threshold"]
    s1_u2 = gpd_survival(u2 - u, f1["xi"], f1["sigma"])
    above_u2 = s1_u2 * gpd_stop_loss(0.0, f2["xi"], f2["sigma"])
    out = predictions[["member_id", "split", "group_id", "target_cost"]].copy()
    for d in attachments:
        if d < u:
            continue
        if d < u2:
            per_p = (
                gpd_stop_loss(d - u, f1["xi"], f1["sigma"])
                - gpd_stop_loss(u2 - u, f1["xi"], f1["sigma"])
                + above_u2
            )
        else:
            per_p = s1_u2 * gpd_stop_loss(d - u2, f2["xi"], f2["sigma"])
        for m in ("glm", "gbm"):
            out[f"exp_excess_{m}_{int(d)}"] = predictions[f"p_{m}_{int(u)}"] * per_p
        out[f"act_excess_{int(d)}"] = np.clip(out["target_cost"] - d, 0, None)
    return out

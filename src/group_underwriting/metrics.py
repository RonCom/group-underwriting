"""Evaluation metrics and cluster bootstrap (resamples members or groups, never rows)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def gini(y: np.ndarray, pred: np.ndarray, w: np.ndarray | None = None) -> float:
    """Normalized Gini of `pred` for ranking `y` (1 = perfect order, 0 = random)."""
    w = np.ones(len(y)) if w is None else np.asarray(w, float)

    def _g(score):
        order = np.lexsort((np.arange(len(score)), -score))
        cw = np.cumsum(w[order]) / w.sum()
        cy = np.cumsum((y * w)[order]) / (y * w).sum()
        return np.sum(cy - cw) / len(y)

    return _g(np.asarray(pred, float)) / _g(np.asarray(y, float))


def predictive_ratio_by_decile(y, pred, w, n: int = 10) -> pd.DataFrame:
    """Sum of predicted / sum of actual cost within deciles of predicted cost (exposure-weighted)."""
    d = pd.DataFrame({"y": y * w, "p": pred * w, "w": w, "r": pred})
    d["decile"] = pd.qcut(d["r"].rank(method="first"), n, labels=range(1, n + 1)).astype(int)
    t = d.groupby("decile").agg(actual=("y", "sum"), predicted=("p", "sum"), exposure=("w", "sum"))
    t["predictive_ratio"] = t["predicted"] / t["actual"]
    return t.reset_index()


def calibration_table(y, p, n: int = 10) -> pd.DataFrame:
    d = pd.DataFrame({"y": y, "p": p})
    d["bin"] = pd.qcut(d["p"].rank(method="first"), n, labels=range(1, n + 1)).astype(int)
    return (
        d.groupby("bin")
        .agg(mean_predicted=("p", "mean"), observed_rate=("y", "mean"), n=("y", "size"))
        .reset_index()
    )


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """ROC AUC via the Mann-Whitney rank statistic (ties get average ranks)."""
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    r = rankdata(p)
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def average_precision(y: np.ndarray, p: np.ndarray) -> float:
    """Average precision (PR-AUC as step-wise sum), same definition as scikit-learn."""
    order = np.argsort(-p, kind="stable")
    ys, ps = y[order], p[order]
    last = np.r_[np.flatnonzero(np.diff(ps)), len(ps) - 1]  # end of each tied block
    tp = np.cumsum(ys)[last]
    precision = tp / (last + 1)
    recall = tp / ys.sum()
    return float(np.sum(np.diff(np.r_[0, recall]) * precision))


def top_decile_lift(y, p) -> float:
    k = max(1, int(np.ceil(len(p) * 0.1)))
    top = np.argsort(-np.asarray(p))[:k]
    return float(np.mean(np.asarray(y)[top]) / np.mean(y))


def classification_metrics(y, p) -> dict[str, float]:
    y = np.asarray(y)
    p = np.asarray(p)
    if y.min() == y.max():
        return {
            "auc": np.nan,
            "pr_auc": np.nan,
            "brier": np.nan,
            "top_decile_lift": np.nan,
            "mean_p": float(p.mean()),
            "rate": float(y.mean()),
        }
    return {
        "auc": auc(y, p),
        "pr_auc": average_precision(y, p),
        "brier": float(np.mean((p - y) ** 2)),
        "top_decile_lift": top_decile_lift(y, p),
        "mean_p": float(p.mean()),
        "rate": float(y.mean()),
    }


def cluster_bootstrap(
    df: pd.DataFrame,
    cluster: str,
    stat: Callable[[pd.DataFrame], dict[str, float]],
    n_boot: int,
    seed: int,
    level: float = 0.95,
) -> pd.DataFrame:
    """Point estimate and percentile interval for each statistic returned by `stat`.

    Resamples whole clusters (members or groups) with replacement.
    """
    rng = np.random.default_rng(seed)
    point = stat(df)
    codes, uniq = pd.factorize(df[cluster])
    order = np.argsort(codes, kind="stable")
    sizes = np.bincount(codes, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        n = sizes[pick]
        offs = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        idx = order[np.repeat(starts[pick], n) + offs]
        draws.append(stat(df.iloc[idx]))
    draws = pd.DataFrame(draws)
    a = (1 - level) / 2
    return pd.DataFrame(
        {
            "metric": list(point),
            "estimate": list(point.values()),
            "lo": [draws[k].quantile(a) for k in point],
            "hi": [draws[k].quantile(1 - a) for k in point],
        }
    )

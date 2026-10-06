"""Member next-year cost (Tweedie GLM baseline vs Tweedie LightGBM) and high-cost claimant models.

Cost models predict annualized allowed cost (target_cost / exposure) with exposure as the sample
weight. Both are fit on the same inner-training members; an inner validation set of training
members (by member hash) is used for LightGBM early stopping, the Tweedie dispersion estimate and
the 2008 -> 2009 signal check. Test members are never touched here.
"""

from __future__ import annotations

import logging
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, TweedieRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ...metrics import gini
from ..features.nodes import FEATURES, _hash_unit

log = logging.getLogger(__name__)

LOG_COLS = [c for c in FEATURES if c.startswith(("cost_", "n_", "ip_days", "max_claim"))]


def glm_design(df: pd.DataFrame) -> pd.DataFrame:
    """GLM inputs: log1p of costs and counts, age and age squared, everything else as is."""
    x = df[FEATURES].astype(float).copy()
    x[LOG_COLS] = np.log1p(x[LOG_COLS].clip(lower=0))
    x["age2"] = (x["age"] - 75) ** 2 / 100
    return x


def _inner_split(train: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    val = _hash_unit(train["member_id"], params["validation_salt"]) < params["validation_share"]
    return train[~val], train[val]


def _hcc_label(df: pd.DataFrame, d: float) -> np.ndarray:
    return (df["target_cost"] > d).astype(int).to_numpy()


def train_cost_models(features: pd.DataFrame, params: dict) -> dict:
    train = features[features["split"] == "train"]
    fit, val = _inner_split(train, params)
    p = params["tweedie_power"]

    glm = make_pipeline(
        StandardScaler(),
        TweedieRegressor(power=p, link="log", alpha=params["glm_alpha"], max_iter=2000),
    )
    glm.fit(glm_design(fit), fit["target_rate"], tweedieregressor__sample_weight=fit["exposure"])

    gbm_params = {
        **params["lgbm"],
        "objective": "tweedie",
        "tweedie_variance_power": p,
        "verbose": -1,
        "seed": params["seed"],
    }
    dfit = lgb.Dataset(fit[FEATURES], fit["target_rate"], weight=fit["exposure"])
    dval = lgb.Dataset(val[FEATURES], val["target_rate"], weight=val["exposure"], reference=dfit)
    gbm = lgb.train(
        gbm_params,
        dfit,
        num_boost_round=params["max_rounds"],
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False)],
    )

    # Pearson dispersion on validation members, per model
    phi = {}
    for name, mu in {
        "glm": glm.predict(glm_design(val)),
        "gbm": gbm.predict(val[FEATURES], num_iteration=gbm.best_iteration),
    }.items():
        w = val["exposure"].to_numpy()
        phi[name] = float(np.sum(w * (val["target_rate"] - mu) ** 2 / mu**p) / (len(val) - 1))
    log.info("Cost GBM best iteration %d; dispersion %s", gbm.best_iteration, phi)
    return {
        "glm": glm,
        "gbm": gbm,
        "tweedie_power": p,
        "phi": phi,
        "n_fit": len(fit),
        "n_val": len(val),
    }


def train_hcc_models(features: pd.DataFrame, params: dict, attachments: list[float]) -> dict:
    train = features[features["split"] == "train"]
    fit, val = _inner_split(train, params)
    models = {}
    for d in attachments:
        y_fit, y_val = _hcc_label(fit, d), _hcc_label(val, d)
        logit = make_pipeline(
            StandardScaler(), LogisticRegression(C=params["logit_C"], max_iter=2000)
        )
        logit.fit(glm_design(fit), y_fit)
        gbm_params = {
            **params["lgbm_hcc"],
            "objective": "binary",
            "verbose": -1,
            "seed": params["seed"],
        }
        dfit = lgb.Dataset(fit[FEATURES], y_fit)
        dval = lgb.Dataset(val[FEATURES], y_val, reference=dfit)
        gbm = lgb.train(
            gbm_params,
            dfit,
            num_boost_round=params["max_rounds"],
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False)],
        )
        models[int(d)] = {"glm": logit, "gbm": gbm}
        log.info(
            "HCC > %d: %d training positives, GBM best iteration %d",
            d,
            y_fit.sum(),
            gbm.best_iteration,
        )
    return models


def predict(
    features: pd.DataFrame, cost_models: dict, hcc_models: dict, trend: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """Predictions for every row, with a flag for the inner validation fold of training.

    Cost predictions for test rows are multiplied by the estimated trend, since the models learn
    the cost level of the training target year.
    """
    x_glm = glm_design(features)
    gbm = cost_models["gbm"]
    out = features[
        ["member_id", "split", "group_id", "exposure", "target_cost", "target_rate"]
    ].copy()
    out["inner_val"] = (features["split"] == "train") & (
        _hash_unit(features["member_id"], params["validation_salt"]) < params["validation_share"]
    )
    out["pred_glm"] = cost_models["glm"].predict(x_glm)
    out["pred_gbm"] = gbm.predict(features[FEATURES], num_iteration=gbm.best_iteration)
    factor = np.where(features["split"] == "test", trend["trend"].iloc[0], 1.0)
    out["pred_glm"] *= factor
    out["pred_gbm"] *= factor
    for d, m in hcc_models.items():
        out[f"p_glm_{d}"] = m["glm"].predict_proba(x_glm)[:, 1]
        out[f"p_gbm_{d}"] = m["gbm"].predict(
            features[FEATURES], num_iteration=m["gbm"].best_iteration
        )
    return out


def signal_check(predictions: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Exposure-weighted Gini on the 2008 -> 2009 inner validation members.

    Compares a constant, prior-year cost alone, the GLM and the GBM. Near-zero Gini for the
    models means DE-SynPUF carries too little year-over-year signal (see the project brief).
    """
    v = predictions[predictions["inner_val"]].merge(
        features[["member_id", "split", "cost_total"]], on=["member_id", "split"]
    )
    y, w = v["target_rate"].to_numpy(), v["exposure"].to_numpy()
    rows = {
        "constant": np.full(len(v), y.mean()),
        "prior_year_cost": v["cost_total"].to_numpy(),
        "glm": v["pred_glm"].to_numpy(),
        "gbm": v["pred_gbm"].to_numpy(),
    }
    return pd.DataFrame(
        {
            "predictor": list(rows),
            "gini": [0.0 if k == "constant" else gini(y, p, w) for k, p in rows.items()],
            "n_members": len(v),
        }
    )


def level_calibration(params: dict) -> pd.DataFrame:
    """One multiplicative level factor per cost model: total actual / total predicted cost on
    already-seen samples scored by the frozen models (`files`, prediction parquet paths).

    Factor 1.0 when none of the files exist.
    """
    frames = [pd.read_parquet(f) for f in params["files"] if Path(f).exists()]
    missing = [f for f in params["files"] if not Path(f).exists()]
    if missing:
        log.warning("Level-calibration files not found, skipped: %s", missing)
    rows = []
    for m in ("glm", "gbm"):
        if frames:
            p = pd.concat(frames)
            p = p[p["split"] == "test"]
            factor = p["target_cost"].sum() / (p[f"pred_{m}"] * p["exposure"]).sum()
            n = len(p)
        else:
            factor, n = 1.0, 0
        rows.append(
            {
                "model": m,
                "factor": float(factor),
                "n_members": n,
                "sources": ", ".join(f for f in params["files"] if Path(f).exists()),
            }
        )
    out = pd.DataFrame(rows)
    log.info(
        "Level calibration factors: %s",
        dict(zip(out["model"], out["factor"].round(4), strict=True)),
    )
    return out

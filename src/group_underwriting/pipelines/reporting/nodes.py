"""Test-set evaluation, explanations, drift, figures, MLflow logging and the results page.

Every interval resamples members (member-level metrics) or groups (group-level metrics).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ...metrics import (
    auc,
    calibration_table,
    classification_metrics,
    cluster_bootstrap,
    gini,
    predictive_ratio_by_decile,
)
from ..features.nodes import FEATURES

log = logging.getLogger(__name__)

MODELS = {"glm": "GLM (Tweedie / logistic)", "gbm": "LightGBM"}
LABELS = {
    "age": "age",
    "female": "share female",
    "esrd": "share with ESRD",
    "months_ab": "months enrolled",
    "months_d": "months with Part D",
    "alzheimers": "share with Alzheimer's",
    "chf": "share with heart failure",
    "ckd": "share with chronic kidney disease",
    "cancer": "share with cancer",
    "copd": "share with COPD",
    "depression": "share with depression",
    "diabetes": "share with diabetes",
    "ischemic_heart": "share with ischemic heart disease",
    "osteoporosis": "share with osteoporosis",
    "ra_oa": "share with arthritis",
    "stroke": "share with stroke/TIA",
    "n_chronic": "chronic conditions per member",
    "cost_ip": "prior inpatient cost",
    "cost_op": "prior outpatient cost",
    "cost_car": "prior professional cost",
    "cost_rx": "prior pharmacy cost",
    "cost_total": "prior total cost",
    "cost_h2": "prior second-half cost",
    "max_claim": "largest prior claim",
    "n_ip_stays": "inpatient stays",
    "ip_days": "inpatient days",
    "n_op": "outpatient claims",
    "n_car": "professional claims",
    "n_rx": "prescription fills",
    "n_ndc": "distinct drugs",
    "n_specialty_rx": "specialty-drug fills",
    "months_with_claims": "months with claims",
}


def _test(features: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    t = predictions[predictions["split"] == "test"].merge(
        features.loc[features["split"] == "test", ["member_id", "size_band", "target_months"]],
        on="member_id",
    )
    return t


def evaluate_cost(
    features: pd.DataFrame, predictions: pd.DataFrame, params: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Member-level next-year cost on the test cohort (2009 features -> 2010 cost)."""
    t = _test(features, predictions)

    def stat(d: pd.DataFrame) -> dict[str, float]:
        y, w = d["target_cost"].to_numpy(), d["exposure"].to_numpy()
        out = {}
        for m in MODELS:
            pred = d[f"pred_{m}"].to_numpy() * w
            out[f"{m}_mae"] = np.mean(np.abs(pred - y))
            out[f"{m}_gini"] = gini(d["target_rate"].to_numpy(), d[f"pred_{m}"].to_numpy(), w)
            out[f"{m}_predicted_to_actual"] = pred.sum() / y.sum()
        out["gbm_minus_glm_mae"] = out["gbm_mae"] - out["glm_mae"]
        out["gbm_minus_glm_gini"] = out["gbm_gini"] - out["glm_gini"]
        return out

    ci = cluster_bootstrap(t, "member_id", stat, params["n_boot"], params["seed"])
    deciles = pd.concat(
        [
            predictive_ratio_by_decile(
                t["target_rate"].to_numpy(), t[f"pred_{m}"].to_numpy(), t["exposure"].to_numpy()
            ).assign(model=m)
            for m in MODELS
        ]
    )
    return ci, deciles


def evaluate_groups(
    features: pd.DataFrame, predictions: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """Group PMPM: predicted vs actual, by size band, intervals from resampling groups."""
    t = _test(features, predictions)
    for m in MODELS:
        t[f"exp_{m}"] = t[f"pred_{m}"] * t["exposure"]
    g = t.groupby(["group_id", "size_band"], as_index=False).agg(
        member_months=("target_months", "sum"),
        actual=("target_cost", "sum"),
        exp_glm=("exp_glm", "sum"),
        exp_gbm=("exp_gbm", "sum"),
    )

    def stat(d: pd.DataFrame) -> dict[str, float]:
        out = {}
        actual = d["actual"] / d["member_months"]
        for m in MODELS:
            pred = d[f"exp_{m}"] / d["member_months"]
            out[f"{m}_pmpm_mae"] = np.average(np.abs(pred - actual), weights=d["member_months"])
            out[f"{m}_pmpm_mape"] = np.average(
                np.abs(pred / actual - 1), weights=d["member_months"]
            )
            out[f"{m}_predicted_to_actual"] = d[f"exp_{m}"].sum() / d["actual"].sum()
        out["actual_pmpm"] = d["actual"].sum() / d["member_months"].sum()
        return out

    rows = []
    bands = [*sorted(g["size_band"].unique(), key=lambda b: int(b.split("-")[0])), "All"]
    for b in bands:
        d = g if b == "All" else g[g["size_band"] == b]
        ci = cluster_bootstrap(d, "group_id", stat, params["n_boot"], params["seed"])
        rows.append(ci.assign(size_band=b, groups=len(d)))
    return pd.concat(rows, ignore_index=True)


def evaluate_hcc(
    features: pd.DataFrame, predictions: pd.DataFrame, attachments: list[float], params: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    t = _test(features, predictions)
    rows, cal = [], []
    for d in attachments:
        d = int(d)
        y = (t["target_cost"] > d).astype(int)
        t["_y"] = y
        for m in MODELS:
            col = f"p_{m}_{d}"

            def stat(x: pd.DataFrame, col=col) -> dict[str, float]:
                return classification_metrics(x["_y"].to_numpy(), x[col].to_numpy())

            ci = cluster_bootstrap(t, "member_id", stat, params["n_boot"], params["seed"])
            rows.append(ci.assign(attachment=d, model=m, positives=int(y.sum())))
            cal.append(
                calibration_table(y.to_numpy(), t[col].to_numpy()).assign(attachment=d, model=m)
            )

        def diff(x: pd.DataFrame, d=d) -> dict[str, float]:
            yy = x["_y"].to_numpy()
            if yy.min() == yy.max():
                return {"auc": np.nan}
            return {
                "auc": auc(yy, x[f"p_gbm_{d}"].to_numpy()) - auc(yy, x[f"p_glm_{d}"].to_numpy())
            }

        ci = cluster_bootstrap(t, "member_id", diff, params["n_boot"], params["seed"])
        rows.append(ci.assign(attachment=d, model="gbm_minus_glm", positives=int(y.sum())))
    return pd.concat(rows, ignore_index=True), pd.concat(cal, ignore_index=True)


def evaluate_excess(
    member_excess: pd.DataFrame, attachments: list[float], params: dict
) -> pd.DataFrame:
    """Expected (HCC probability x GPD) vs actual loss above each attachment, test cohort."""
    t = member_excess[member_excess["split"] == "test"]
    rows = []
    for d in attachments:
        d = int(d)
        for m in MODELS:
            col = f"exp_excess_{m}_{d}"
            if col not in t:
                continue

            def stat(x: pd.DataFrame, d=d, col=col) -> dict[str, float]:
                n = len(x)
                return {
                    "expected_per_member": x[col].sum() / n,
                    "actual_per_member": x[f"act_excess_{d}"].sum() / n,
                    "actual_to_expected": x[f"act_excess_{d}"].sum() / x[col].sum(),
                }

            ci = cluster_bootstrap(t, "member_id", stat, params["n_boot"], params["seed"])
            rows.append(
                ci.assign(attachment=d, model=m, claimants=int((t["target_cost"] > d).sum()))
            )
    return pd.concat(rows, ignore_index=True)


def explain(
    features: pd.DataFrame, cost_models: dict, hcc_models: dict, params: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SHAP (LightGBM TreeSHAP) importance and plain-language drivers per test group.

    Contributions are on the log scale of the cost model, so a group's mean contribution for a
    feature, minus the test-population mean, gives the multiplicative effect on that group's
    predicted cost relative to an average group.
    """
    t = features[features["split"] == "test"].reset_index(drop=True)
    gbm = cost_models["gbm"]
    contrib = gbm.predict(t[FEATURES], num_iteration=gbm.best_iteration, pred_contrib=True)
    shap_df = pd.DataFrame(contrib[:, :-1], columns=FEATURES)
    imp = pd.DataFrame({"feature": FEATURES, "cost_mean_abs_shap": shap_df.abs().mean().values})
    for d, m in hcc_models.items():
        c = m["gbm"].predict(t[FEATURES], num_iteration=m["gbm"].best_iteration, pred_contrib=True)
        imp[f"hcc_{d}_mean_abs_shap"] = np.abs(c[:, :-1]).mean(axis=0)
    imp = imp.sort_values("cost_mean_abs_shap", ascending=False).reset_index(drop=True)

    rel = shap_df - shap_df.mean()
    rel["group_id"] = t["group_id"]
    g_shap = rel.groupby("group_id").mean()
    g_val = t.groupby("group_id")[FEATURES].mean()
    pop = t[FEATURES].mean()
    rows = []
    for gid, r in g_shap.iterrows():
        top = r.sort_values(key=np.abs, ascending=False).head(3)
        parts = []
        for f, v in top.items():
            direction = "raises" if v > 0 else "lowers"
            parts.append(
                f"{LABELS[f]} {_fmt(f, g_val.at[gid, f])} vs {_fmt(f, pop[f])} "
                f"({direction} cost {abs(np.expm1(v)):.1%})"
            )
        rows.append(
            {
                "group_id": gid,
                "relative_cost": float(np.exp(r.sum())),
                "drivers": "; ".join(parts),
            }
        )
    drivers = pd.DataFrame(rows).sort_values("relative_cost", ascending=False)
    return imp, drivers


def _fmt(feature: str, v: float) -> str:
    if LABELS[feature].startswith("share"):
        return f"{v:.0%}"
    if feature.startswith(("cost_", "max_")):
        return f"${v:,.0f}"
    return f"{v:.1f}"


def drift(features: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Population stability index per feature, training scoring year vs test scoring year.

    With `evidently: true` and the `drift` extra installed, also writes an Evidently data drift report (HTML) next to
    the other reporting outputs.
    """
    a = features[features["split"] == "train"]
    b = features[features["split"] == "test"]
    rows = []
    for f in FEATURES:
        edges = np.unique(np.quantile(a[f], np.linspace(0, 1, 11)))
        if len(edges) < 3:
            edges = np.unique(np.concatenate([edges, [a[f].min() - 1, a[f].max() + 1]]))
        edges[0], edges[-1] = -np.inf, np.inf
        pa = np.histogram(a[f], edges)[0] / len(a) + 1e-4
        pb = np.histogram(b[f], edges)[0] / len(b) + 1e-4
        rows.append(
            {
                "feature": f,
                "psi": float(np.sum((pb - pa) * np.log(pb / pa))),
                "train_mean": a[f].mean(),
                "test_mean": b[f].mean(),
            }
        )
    out = pd.DataFrame(rows).sort_values("psi", ascending=False)
    if not params["evidently"]:
        return out
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except ImportError:
        log.info("Evidently not installed (uv sync --extra drift); PSI only")
        return out
    path = Path(params["evidently_dir"])
    path.mkdir(parents=True, exist_ok=True)
    snap = Report([DataDriftPreset()]).run(reference_data=a[FEATURES], current_data=b[FEATURES])
    snap.save_html(str(path / "drift_report.html"))
    log.info("Evidently drift report: %s", path / "drift_report.html")
    return out

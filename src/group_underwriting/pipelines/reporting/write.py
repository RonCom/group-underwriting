"""Figures, the results page and MLflow logging."""

from __future__ import annotations

import logging
import pickle
import tempfile
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .nodes import LABELS, MODELS  # noqa: E402

log = logging.getLogger(__name__)


def _ci(est: float, lo: float, hi: float, f: str = "{:.3f}") -> str:
    return f"{f.format(est)} [{f.format(lo)}–{f.format(hi)}]"


def _row(ci: pd.DataFrame, metric: str, f: str = "{:.3f}") -> str:
    r = ci.set_index("metric").loc[metric]
    return _ci(r["estimate"], r["lo"], r["hi"], f)


def make_figures(
    deciles: pd.DataFrame,
    hcc_calibration: pd.DataFrame,
    mean_excess: pd.DataFrame,
    tail_qq: pd.DataFrame,
    tail_fit: pd.DataFrame,
    ibnr_completion: pd.DataFrame,
    shap_importance: pd.DataFrame,
    group_pricing: pd.DataFrame,
    params: dict,
) -> list[str]:
    out = Path(params["figures_dir"])
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(out / name, dpi=110)
        plt.close(fig)
        written.append(name)

    fig, ax = plt.subplots(figsize=(6, 4))
    for m, label in MODELS.items():
        d = deciles[deciles["model"] == m]
        ax.plot(d["decile"], d["predictive_ratio"], marker="o", label=label)
    ax.axhline(1, color="grey", lw=1, ls="--")
    ax.set(
        xlabel="Decile of predicted cost",
        ylabel="Predicted / actual",
        title="Predictive ratio by decile (test, 2010 cost)",
    )
    ax.legend()
    save(fig, "predictive_ratio_by_decile.png")

    atts = sorted(hcc_calibration["attachment"].unique())
    fig, axes = plt.subplots(1, len(atts), figsize=(4 * len(atts), 3.8), squeeze=False)
    for ax, a in zip(axes[0], atts, strict=True):
        for m, label in MODELS.items():
            d = hcc_calibration[
                (hcc_calibration["attachment"] == a) & (hcc_calibration["model"] == m)
            ]
            ax.plot(d["mean_predicted"], d["observed_rate"], marker="o", label=label)
        lim = max(
            hcc_calibration.loc[
                hcc_calibration["attachment"] == a, ["mean_predicted", "observed_rate"]
            ].max()
        )
        ax.plot([0, lim], [0, lim], color="grey", lw=1, ls="--")
        ax.set(title=f"P(cost > ${a:,})", xlabel="Mean predicted", ylabel="Observed rate")
    axes[0][0].legend(fontsize=8)
    save(fig, "hcc_calibration.png")

    u = tail_fit["threshold"].iloc[0]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(mean_excess["threshold"], mean_excess["mean_excess"], marker=".")
    axes[0].axvline(u, color="grey", ls="--", lw=1)
    axes[0].set(
        xlabel="Threshold ($)", ylabel="Mean excess ($)", title="Mean excess of annual member cost"
    )
    lim = max(tail_qq["empirical"].max(), tail_qq["gpd"].max())
    axes[1].scatter(tail_qq["gpd"], tail_qq["empirical"], s=8)
    axes[1].plot([u, lim], [u, lim], color="grey", ls="--", lw=1)
    axes[1].set(
        xlabel="GPD quantile ($)", ylabel="Empirical quantile ($)", title=f"QQ plot above ${u:,.0f}"
    )
    save(fig, "tail_mean_excess_qq.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    for v, d in ibnr_completion.groupby("valuation_date"):
        ax.plot(d["lag_months"], d["completion"], marker=".", label=f"valued {v}")
    ax.set(
        xlabel="Months after incurred month",
        ylabel="Share of ultimate paid",
        title="Completion factors (chain ladder)",
    )
    ax.legend()
    save(fig, "ibnr_completion.png")

    top = shap_importance.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.barh([LABELS[f] for f in top["feature"]], top["cost_mean_abs_shap"])
    ax.set(xlabel="Mean |SHAP| (log cost)", title="Cost model drivers (test members)")
    save(fig, "shap_importance.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    for m, gp in group_pricing.groupby("model", sort=False):
        label = gp["label"].iloc[0] if "label" in gp.columns else MODELS.get(m, m)
        ax.scatter(gp["members"], gp["actual_claims"] / gp["expected_claims"], s=14, label=label)
    ax.legend()
    ax.axhline(1, color="grey", ls="--", lw=1)
    ax.set_xscale("log")
    ax.set(
        xlabel="Group size (members)",
        ylabel="Actual / expected claims",
        title="Group actual-to-expected by size",
    )
    save(fig, "group_actual_to_expected.png")
    return written


def write_results(
    signal: pd.DataFrame,
    cost_ci: pd.DataFrame,
    deciles: pd.DataFrame,
    group_ci: pd.DataFrame,
    hcc: pd.DataFrame,
    excess: pd.DataFrame,
    tail_fit: pd.DataFrame,
    ibnr: pd.DataFrame,
    pricing: pd.DataFrame,
    trend: pd.DataFrame,
    psi: pd.DataFrame,
    shap_importance: pd.DataFrame,
    drivers: pd.DataFrame,
    features: pd.DataFrame,
    figures: list[str],
    params: dict,
) -> str:
    fig_rel = Path(params["figures_dir"]).relative_to(Path(params["results_file"]).parent)
    tr = features[features["split"] == "train"]
    te = features[features["split"] == "test"]
    L = [
        f"# Results ({params['label']} data)",
        "",
        f"Generated {date.today().isoformat()} by `kedro run`. Do not edit by hand.",
        "",
        f"Training: {len(tr):,} members, features {tr['feature_year'].iloc[0]} -> cost "
        f"{tr['feature_year'].iloc[0] + 1}. Test: {len(te):,} different members in "
        f"{te['group_id'].nunique()} synthetic groups, features {te['feature_year'].iloc[0]} -> "
        f"cost {te['feature_year'].iloc[0] + 1}. Intervals are 95% bootstrap intervals that "
        "resample members (member metrics) or groups (group metrics).",
        "",
        "## Signal check (2008 -> 2009, inner validation members)",
        "",
        "| Predictor | Gini |",
        "|---|---|",
        *[f"| {r.predictor} | {r.gini:.3f} |" for r in signal.itertuples()],
        "",
        f"Trend applied to test predictions ({trend['base_year'].iloc[0]} -> "
        f"{trend['next_year'].iloc[0]} PMPM at equal runout): {trend['trend'].iloc[0]:.3f}.",
        "",
        "## Member next-year cost (test)",
        "",
        "| Model | MAE ($) | Gini | Predicted / actual |",
        "|---|---|---|---|",
    ]
    for m, label in MODELS.items():
        L.append(
            f"| {label} | {_row(cost_ci, f'{m}_mae', '{:,.0f}')} | "
            f"{_row(cost_ci, f'{m}_gini')} | {_row(cost_ci, f'{m}_predicted_to_actual')} |"
        )
    L += [
        f"| LightGBM − GLM | {_row(cost_ci, 'gbm_minus_glm_mae', '{:,.0f}')} | "
        f"{_row(cost_ci, 'gbm_minus_glm_gini')} | |",
        "",
        "Predictive ratio (predicted / actual) by decile of predicted cost:",
        "",
        "| Decile | " + " | ".join(MODELS.values()) + " |",
        "|---|" + "---|" * len(MODELS),
    ]
    for dec in range(1, 11):
        vals = [
            deciles[(deciles["model"] == m) & (deciles["decile"] == dec)]["predictive_ratio"].iloc[
                0
            ]
            for m in MODELS
        ]
        L.append(f"| {dec} | " + " | ".join(f"{v:.2f}" for v in vals) + " |")
    L += [
        "",
        f"![Predictive ratio]({fig_rel}/predictive_ratio_by_decile.png)",
        "",
        "## Group PMPM (test)",
        "",
        "| Size band | Groups | Actual PMPM | GLM PMPM MAE | LightGBM PMPM MAE | "
        "LightGBM predicted / actual |",
        "|---|---|---|---|---|---|",
    ]
    for b, d in group_ci.groupby("size_band", sort=False):
        L.append(
            f"| {b} | {d['groups'].iloc[0]} | {_row(d, 'actual_pmpm', '{:,.0f}')} | "
            f"{_row(d, 'glm_pmpm_mae', '{:,.0f}')} | {_row(d, 'gbm_pmpm_mae', '{:,.0f}')} | "
            f"{_row(d, 'gbm_predicted_to_actual')} |"
        )
    L += [
        "",
        "## High-cost claimants (test)",
        "",
        "| Attachment | Claimants | Model | AUC | PR-AUC | Top-decile lift | Brier |",
        "|---|---|---|---|---|---|---|",
    ]
    for (a, m), d in hcc[hcc["model"].isin(list(MODELS))].groupby(
        ["attachment", "model"], sort=True
    ):
        L.append(
            f"| ${a:,} | {d['positives'].iloc[0]} | {MODELS[m]} | {_row(d, 'auc')} | "
            f"{_row(d, 'pr_auc')} | {_row(d, 'top_decile_lift', '{:.1f}')} | "
            f"{_row(d, 'brier', '{:.4f}')} |"
        )
    f = tail_fit.iloc[0]
    L += [
        "",
        "AUC difference, LightGBM − GLM (paired, resampling members): "
        + "; ".join(
            f"${a:,}: {_row(d, 'auc')}"
            for a, d in hcc[hcc["model"] == "gbm_minus_glm"].groupby("attachment")
        )
        + ".",
        "",
        f"![HCC calibration]({fig_rel}/hcc_calibration.png)",
        "",
        "## Tail",
        "",
        f"Generalized Pareto above ${f['threshold']:,.0f} on training members' 2009 cost: "
        f"shape ξ = {f['xi']:.3f}, scale σ = ${f['sigma']:,.0f}, {int(f['n_exceed'])} "
        f"exceedances ({f['p_exceed']:.1%} of members), KS p = {f['ks_pvalue']:.3g} (the KS "
        "p-value ignores that the parameters were fit, so it is optimistic).",
        "",
        "| Attachment | Claimants | HCC model | Expected excess / member | "
        "Actual excess / member | Actual / expected |",
        "|---|---|---|---|---|---|",
    ]
    for (a, m), d in excess.groupby(["attachment", "model"]):
        L.append(
            f"| ${a:,} | {d['claimants'].iloc[0]} | {MODELS[m]} | "
            f"{_row(d, 'expected_per_member', '${:,.0f}')} | "
            f"{_row(d, 'actual_per_member', '${:,.0f}')} | "
            f"{_row(d, 'actual_to_expected', '{:.2f}')} |"
        )
    L += [
        "",
        f"![Tail diagnostics]({fig_rel}/tail_mean_excess_qq.png)",
        "",
        "## Claims runout (IBNR)",
        "",
        "| Valuation | Method | Paid to date | Estimated IBNR | Actual IBNR | Error |",
        "|---|---|---|---|---|---|",
    ]
    if "method" not in ibnr.columns:
        ibnr = ibnr.assign(method="single")
    names = {"single": "One triangle", "by_source": "By claim type"}
    for (v, m), d in ibnr.groupby(["valuation_date", "method"]):
        est, act = d["estimated_ibnr"].sum(), d["actual_ibnr"].sum()
        L.append(
            f"| {v} | {names.get(m, m)} | ${d['paid_to_date'].sum():,.0f} | ${est:,.0f} | "
            f"${act:,.0f} | {est / act - 1:+.1%} |"
        )
    L += [
        "",
        f"![Completion]({fig_rel}/ibnr_completion.png)",
        "",
        "## Stop-loss pricing by group size (test)",
        "",
        "| Models | Size band | Groups | Members | Priced loss ratio | Actual loss ratio | "
        "Claims actual / expected | Specific actual / expected | Aggregate hits (expected) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in pricing.itertuples():
        L.append(
            f"| {MODELS.get(r.label, r.label)} | {r.size_band} | {r.groups} | {r.members:,} | "
            f"{r.priced_loss_ratio:.3f} | "
            f"{_ci(r.actual_loss_ratio, r.actual_loss_ratio_lo, r.actual_loss_ratio_hi)} | "
            f"{_ci(r.actual_to_expected, r.actual_to_expected_lo, r.actual_to_expected_hi, '{:.2f}')} | "
            f"{_ci(r.specific_a_to_e, r.specific_a_to_e_lo, r.specific_a_to_e_hi, '{:.2f}')} | "
            f"{r.aggregate_hits} ({r.expected_aggregate_hits:.1f}) |"
        )
    L += [
        "",
        f"![Group A/E]({fig_rel}/group_actual_to_expected.png)",
        "",
        "## Drivers",
        "",
        "| Feature | Mean \\|SHAP\\| (cost) |",
        "|---|---|",
        *[
            f"| {LABELS[r.feature]} | {r.cost_mean_abs_shap:.3f} |"
            for r in shap_importance.head(10).itertuples()
        ],
        "",
        f"![SHAP]({fig_rel}/shap_importance.png)",
        "",
        "Highest and lowest predicted-cost groups (cost relative to an average test group, "
        "top three drivers):",
        "",
        "| Group | Relative cost | Drivers |",
        "|---|---|---|",
    ]
    n = params["top_groups"]
    for r in pd.concat([drivers.head(n), drivers.tail(n)]).itertuples():
        L.append(f"| {r.group_id} | {r.relative_cost:.2f}× | {r.drivers} |")
    L += [
        "",
        "## Drift between scoring years (PSI, 2008 vs 2009 features)",
        "",
        "| Feature | PSI | 2008 mean | 2009 mean |",
        "|---|---|---|---|",
        *[
            f"| {LABELS[r.feature]} | {r.psi:.3f} | {r.train_mean:,.2f} | {r.test_mean:,.2f} |"
            for r in psi.head(8).itertuples()
        ],
        "",
    ]
    text = "\n".join(L)
    path = Path(params["results_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    log.info("Wrote %s", path)
    return text


def log_mlflow(
    cost_models: dict,
    hcc_models: dict,
    cost_ci: pd.DataFrame,
    hcc: pd.DataFrame,
    pricing: pd.DataFrame,
    model_params: dict,
    params: dict,
) -> None:
    cfg = params["mlflow"]
    if not cfg["enabled"]:
        log.info("MLflow logging disabled")
        return
    import mlflow

    mlflow.set_tracking_uri(cfg["tracking_uri"])
    mlflow.set_experiment(cfg["experiment"])
    with mlflow.start_run(run_name=f"{params['label']}-{date.today().isoformat()}"):
        mlflow.log_params(
            {
                "tweedie_power": model_params["tweedie_power"],
                "gbm_best_iteration": cost_models["gbm"].best_iteration,
                **{f"lgbm_{k}": v for k, v in model_params["lgbm"].items()},
            }
        )
        mlflow.log_metrics({r.metric: r.estimate for r in cost_ci.itertuples()})
        for r in hcc[hcc["metric"].isin(["auc", "pr_auc"])].itertuples():  # incl. AUC difference
            mlflow.log_metric(f"hcc_{r.attachment}_{r.model}_{r.metric}", r.estimate)
        for r in pricing[pricing["size_band"] == "All"].itertuples():
            mlflow.log_metric(f"pricing_{r.model}_actual_to_expected", r.actual_to_expected)
        with tempfile.TemporaryDirectory() as tmp:
            for name, obj in {"cost_models.pkl": cost_models, "hcc_models.pkl": hcc_models}.items():
                p = Path(tmp) / name
                p.write_bytes(pickle.dumps(obj))
                mlflow.log_artifact(str(p))
        info = mlflow.lightgbm.log_model(cost_models["gbm"], name="cost_gbm")
        if cfg["register_models"]:
            mlflow.register_model(info.model_uri, "group-underwriting-cost-gbm")
    log.info("Logged run to MLflow at %s", cfg["tracking_uri"])

from kedro.pipeline import Pipeline, node

from .nodes import (
    drift,
    evaluate_cost,
    evaluate_excess,
    evaluate_groups,
    evaluate_hcc,
    explain,
)
from .write import log_mlflow, make_figures, write_results


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                evaluate_cost,
                ["features", "predictions", "params:reporting"],
                ["cost_metrics", "predictive_ratio_deciles"],
                name="evaluate_cost",
            ),
            node(
                evaluate_groups,
                ["features", "predictions", "params:reporting"],
                "group_metrics",
                name="evaluate_groups",
            ),
            node(
                evaluate_hcc,
                ["features", "predictions", "params:attachment_points", "params:reporting"],
                ["hcc_metrics", "hcc_calibration"],
                name="evaluate_hcc",
            ),
            node(
                evaluate_excess,
                ["member_excess", "params:attachment_points", "params:reporting"],
                "excess_metrics",
                name="evaluate_excess",
            ),
            node(
                explain,
                ["features", "cost_models", "hcc_models", "params:reporting"],
                ["shap_importance", "group_drivers"],
                name="explain",
            ),
            node(drift, ["features", "params:reporting"], "feature_drift", name="drift"),
            node(
                make_figures,
                [
                    "predictive_ratio_deciles",
                    "hcc_calibration",
                    "mean_excess",
                    "tail_qq",
                    "tail_fit",
                    "ibnr_completion",
                    "shap_importance",
                    "group_pricing",
                    "params:reporting",
                ],
                "figure_files",
                name="make_figures",
            ),
            node(
                write_results,
                [
                    "signal_check",
                    "cost_metrics",
                    "predictive_ratio_deciles",
                    "group_metrics",
                    "hcc_metrics",
                    "excess_metrics",
                    "tail_fit",
                    "ibnr_estimates",
                    "pricing_by_band",
                    "trend",
                    "feature_drift",
                    "shap_importance",
                    "group_drivers",
                    "features",
                    "figure_files",
                    "params:reporting",
                ],
                "results_markdown",
                name="write_results",
            ),
            node(
                log_mlflow,
                [
                    "cost_models",
                    "hcc_models",
                    "cost_metrics",
                    "hcc_metrics",
                    "pricing_by_band",
                    "params:models",
                    "params:reporting",
                ],
                None,
                name="log_mlflow",
            ),
        ]
    )

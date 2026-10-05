from kedro.pipeline import Pipeline, node

from ..followup.pipeline import create_pipeline as followup_pipeline
from ..pricing.nodes import price_variants, summarize_by_band
from ..reporting.nodes import evaluate_excess
from ..tail.nodes import spliced_excess
from .nodes import check_disjoint_all, evaluate_level, write_holdout

KEEP = {
    "fu_load_members",
    "fu_load_claims",
    "fu_simulate_paid_dates",
    "fu_build_cohorts",
    "fu_assign_groups",
    "fu_build_features",
    "fu_estimate_trend",
    "fu_predict",
    "fu_expected_excess",
    "fu_evaluate_cost",
    "fu_evaluate_excess",
}


def create_pipeline(**kwargs) -> Pipeline:
    """Run with `--env holdout`: Sample 5 data; models, tails and level factors frozen."""
    base = Pipeline([n for n in followup_pipeline().nodes if n.name in KEEP])
    return base + Pipeline(
        [
            node(
                check_disjoint_all,
                ["features_raw", "params:holdout"],
                "features",
                name="ho_check_disjoint",
            ),
            node(
                spliced_excess,
                ["predictions", "tail_fit", "upper_tail_fit", "params:attachment_points"],
                "spliced_member_excess",
                name="ho_spliced_excess",
            ),
            node(
                evaluate_excess,
                ["spliced_member_excess", "params:attachment_points", "params:reporting"],
                "spliced_excess_metrics",
                name="ho_evaluate_spliced",
            ),
            node(
                price_variants,
                [
                    "features",
                    "predictions",
                    "member_excess",
                    "spliced_member_excess",
                    "cost_models",
                    "level_calibration",
                    "params:pricing_variants",
                    "params:pricing",
                ],
                "group_pricing",
                name="ho_price_variants",
            ),
            node(
                summarize_by_band,
                ["group_pricing", "params:pricing"],
                "pricing_by_band",
                name="ho_summarize_pricing",
            ),
            node(
                evaluate_level,
                ["predictions", "level_calibration", "params:reporting"],
                "level_metrics",
                name="ho_evaluate_level",
            ),
            node(
                write_holdout,
                [
                    "level_metrics",
                    "cost_metrics",
                    "level_calibration",
                    "excess_metrics",
                    "spliced_excess_metrics",
                    "pricing_by_band",
                    "features",
                    "params:holdout",
                ],
                "holdout_markdown",
                name="ho_write",
            ),
        ]
    )

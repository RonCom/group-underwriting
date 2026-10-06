from kedro.pipeline import Pipeline, node

from ..features.nodes import assign_groups, build_cohorts, build_features, estimate_trend
from ..ingest.nodes import load_claims, load_members, simulate_paid_dates
from ..models.nodes import predict
from ..pricing.nodes import price_groups, summarize_by_band
from ..reporting.nodes import evaluate_cost, evaluate_excess, evaluate_groups, evaluate_hcc
from ..tail.nodes import expected_excess
from .nodes import check_disjoint, rank_check, relative_pricing, write_followup


def create_pipeline(**kwargs) -> Pipeline:
    """Run with `--env followup`: data from the follow-up sample, models from the frozen run."""
    return Pipeline(
        [
            node(load_members, "params:raw_dir", "members", name="fu_load_members"),
            node(load_claims, "params:raw_dir", "claims_unpaid", name="fu_load_claims"),
            node(
                simulate_paid_dates,
                ["claims_unpaid", "params:paid_lag"],
                "claims",
                name="fu_simulate_paid_dates",
            ),
            node(build_cohorts, ["members", "params:cohorts"], "cohorts", name="fu_build_cohorts"),
            node(
                assign_groups,
                ["cohorts", "params:groups"],
                "member_groups",
                name="fu_assign_groups",
            ),
            node(
                build_features,
                ["claims", "member_groups", "params:features"],
                "features_raw",
                name="fu_build_features",
            ),
            node(
                check_disjoint,
                ["features_raw", "frozen_members"],
                "features",
                name="fu_check_disjoint",
            ),
            node(
                estimate_trend,
                ["claims", "members", "params:cohorts", "params:features"],
                "trend",
                name="fu_estimate_trend",
            ),
            node(
                predict,
                ["features", "cost_models", "hcc_models", "trend", "params:models"],
                "predictions",
                name="fu_predict",
            ),
            node(
                expected_excess,
                ["predictions", "tail_fit", "params:attachment_points"],
                "member_excess",
                name="fu_expected_excess",
            ),
            node(
                price_groups,
                ["features", "predictions", "member_excess", "cost_models", "params:pricing"],
                "group_pricing",
                name="fu_price_groups",
            ),
            node(
                summarize_by_band,
                ["group_pricing", "params:pricing"],
                "pricing_by_band",
                name="fu_summarize_pricing",
            ),
            node(
                evaluate_cost,
                ["features", "predictions", "params:reporting"],
                ["cost_metrics", "predictive_ratio_deciles"],
                name="fu_evaluate_cost",
            ),
            node(
                evaluate_groups,
                ["features", "predictions", "params:reporting"],
                "group_metrics",
                name="fu_evaluate_groups",
            ),
            node(
                evaluate_hcc,
                ["features", "predictions", "params:attachment_points", "params:reporting"],
                ["hcc_metrics", "hcc_calibration"],
                name="fu_evaluate_hcc",
            ),
            node(
                evaluate_excess,
                ["member_excess", "params:attachment_points", "params:reporting"],
                "excess_metrics",
                name="fu_evaluate_excess",
            ),
            node(rank_check, ["group_pricing", "params:reporting"], "group_rank", name="fu_rank"),
            node(
                rank_check,
                ["frozen_group_pricing", "params:reporting"],
                "frozen_group_rank",
                name="fu_frozen_rank",
            ),
            node(
                relative_pricing,
                ["frozen_group_pricing", "params:reporting"],
                "frozen_relative_pricing",
                name="fu_relative_pricing",
            ),
            node(
                write_followup,
                [
                    "cost_metrics",
                    "group_metrics",
                    "hcc_metrics",
                    "excess_metrics",
                    "pricing_by_band",
                    "group_pricing",
                    "group_rank",
                    "frozen_group_rank",
                    "frozen_relative_pricing",
                    "features",
                    "params:followup",
                ],
                "followup_markdown",
                name="fu_write",
            ),
        ]
    )

from kedro.pipeline import Pipeline, node

from ..followup.pipeline import create_pipeline as followup_pipeline
from ..holdout.nodes import check_disjoint_all
from ..pricing.nodes import build_residual_pool, price_variants, summarize_by_band
from ..tail.nodes import spliced_excess
from .nodes import evaluate_simulation, write_aggtest

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
}


def create_pipeline(**kwargs) -> Pipeline:
    """Run with `--env aggtest`: Sample 6 data; models, tails, level factor and pool frozen."""
    base = Pipeline([n for n in followup_pipeline().nodes if n.name in KEEP])
    return base + Pipeline(
        [
            node(
                check_disjoint_all,
                ["features_raw", "params:aggtest"],
                "features",
                name="ag_check_disjoint",
            ),
            node(
                spliced_excess,
                ["predictions", "tail_fit", "upper_tail_fit", "params:attachment_points"],
                "spliced_member_excess",
                name="ag_spliced_excess",
            ),
            node(
                build_residual_pool,
                "params:residual_pool",
                "residual_pool",
                name="ag_residual_pool",
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
                    "params:aggtest_variants",
                    "params:pricing",
                    "residual_pool",
                ],
                "group_pricing",
                name="ag_price_variants",
            ),
            node(
                summarize_by_band,
                ["group_pricing", "params:pricing"],
                "pricing_by_band",
                name="ag_summarize_pricing",
            ),
            node(
                evaluate_simulation,
                ["group_pricing", "params:reporting"],
                "simulation_metrics",
                name="ag_evaluate_simulation",
            ),
            node(
                write_aggtest,
                ["simulation_metrics", "pricing_by_band", "features", "params:aggtest"],
                "aggtest_markdown",
                name="ag_write",
            ),
        ]
    )

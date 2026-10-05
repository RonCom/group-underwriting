from kedro.pipeline import Pipeline, node

from ..followup.nodes import check_disjoint
from ..followup.pipeline import create_pipeline as followup_pipeline
from ..reporting.nodes import evaluate_excess
from ..tail.nodes import fit_upper_tail, spliced_excess
from .nodes import write_retest

KEEP = {
    "fu_load_members",
    "fu_load_claims",
    "fu_simulate_paid_dates",
    "fu_build_cohorts",
    "fu_assign_groups",
    "fu_build_features",
    "fu_check_disjoint",
    "fu_estimate_trend",
    "fu_predict",
    "fu_expected_excess",
    "fu_price_groups",
    "fu_summarize_pricing",
    "fu_evaluate_cost",
    "fu_evaluate_groups",
    "fu_evaluate_hcc",
    "fu_evaluate_excess",
}


def create_pipeline(**kwargs) -> Pipeline:
    """Run with `--env retest`: Sample 4 data, frozen Sample 2 models, Sample 3 for the upper tail."""
    base = Pipeline([n for n in followup_pipeline().nodes if n.name in KEEP])
    # second disjointness check, against the Sample 3 members
    renamed = Pipeline(
        [
            n
            if n.name != "fu_check_disjoint"
            else node(
                check_disjoint,
                ["features_raw", "frozen_members"],
                "features_s2_checked",
                name="rt_check_disjoint_s2",
            )
            for n in base.nodes
        ]
    )
    return renamed + Pipeline(
        [
            node(
                check_disjoint,
                ["features_s2_checked", "calibration_members"],
                "features",
                name="rt_check_disjoint_s3",
            ),
            node(
                fit_upper_tail,
                ["frozen_features", "calibration_features", "params:upper_tail"],
                "upper_tail_fit",
                name="rt_fit_upper_tail",
            ),
            node(
                spliced_excess,
                ["predictions", "tail_fit", "upper_tail_fit", "params:attachment_points"],
                "spliced_member_excess",
                name="rt_spliced_excess",
            ),
            node(
                evaluate_excess,
                ["spliced_member_excess", "params:attachment_points", "params:reporting"],
                "spliced_excess_metrics",
                name="rt_evaluate_spliced",
            ),
            node(
                write_retest,
                [
                    "cost_metrics",
                    "hcc_metrics",
                    "tail_fit",
                    "upper_tail_fit",
                    "excess_metrics",
                    "spliced_excess_metrics",
                    "pricing_by_band",
                    "features",
                    "params:retest",
                ],
                "retest_markdown",
                name="rt_write",
            ),
        ]
    )

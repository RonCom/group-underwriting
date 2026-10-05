from kedro.pipeline import Pipeline, node

from .nodes import expected_excess, fit_tail, fit_upper_tail_main, spliced_excess


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                fit_tail,
                ["features", "params:tail"],
                ["tail_fit", "mean_excess", "tail_qq"],
                name="fit_tail",
            ),
            node(
                expected_excess,
                ["predictions", "tail_fit", "params:attachment_points"],
                "member_excess",
                name="expected_excess",
            ),
            node(
                fit_upper_tail_main,
                ["features", "params:upper_tail"],
                "upper_tail_fit",
                name="fit_upper_tail",
            ),
            node(
                spliced_excess,
                ["predictions", "tail_fit", "upper_tail_fit", "params:attachment_points"],
                "spliced_member_excess",
                name="spliced_excess",
            ),
        ]
    )

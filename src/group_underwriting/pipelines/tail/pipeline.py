from kedro.pipeline import Pipeline, node

from .nodes import expected_excess, fit_tail


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
                ["predictions", "tail_fit", "params:attachment_points", "params:tail.hcc_model"],
                "member_excess",
                name="expected_excess",
            ),
        ]
    )

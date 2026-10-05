from kedro.pipeline import Pipeline, node

from .nodes import estimate_ibnr


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                estimate_ibnr,
                ["claims", "params:ibnr"],
                ["ibnr_completion", "ibnr_estimates"],
                name="estimate_ibnr",
            ),
        ]
    )

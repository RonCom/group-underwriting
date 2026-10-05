from kedro.pipeline import Pipeline, node

from .nodes import generate


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(generate, "params:synthetic", None, name="generate_synthetic_synpuf"),
        ]
    )

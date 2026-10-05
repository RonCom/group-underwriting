from kedro.pipeline import Pipeline, node

from .nodes import (
    level_calibration,
    predict,
    signal_check,
    train_cost_models,
    train_hcc_models,
)


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                train_cost_models,
                ["features", "params:models"],
                "cost_models",
                name="train_cost_models",
            ),
            node(
                train_hcc_models,
                ["features", "params:models", "params:attachment_points"],
                "hcc_models",
                name="train_hcc_models",
            ),
            node(
                predict,
                ["features", "cost_models", "hcc_models", "trend", "params:models"],
                "predictions",
                name="predict",
            ),
            node(
                level_calibration,
                "params:level_calibration",
                "level_calibration",
                name="level_calibration",
            ),
            node(signal_check, ["predictions", "features"], "signal_check", name="signal_check"),
        ]
    )

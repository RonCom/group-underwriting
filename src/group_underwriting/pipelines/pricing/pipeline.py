from kedro.pipeline import Pipeline, node

from .nodes import build_residual_pool, price_variants, summarize_by_band


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                build_residual_pool,
                "params:residual_pool",
                "residual_pool",
                name="build_residual_pool",
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
                    "residual_pool",
                ],
                "group_pricing",
                name="price_groups",
            ),
            node(
                summarize_by_band,
                ["group_pricing", "params:pricing"],
                "pricing_by_band",
                name="summarize_pricing_by_band",
            ),
        ]
    )

from kedro.pipeline import Pipeline, node

from .nodes import price_groups, summarize_by_band


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                price_groups,
                ["features", "predictions", "member_excess", "cost_models", "params:pricing"],
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

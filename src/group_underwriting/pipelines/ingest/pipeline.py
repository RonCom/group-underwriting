from kedro.pipeline import Pipeline, node

from .nodes import load_claims, load_members, simulate_paid_dates


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(load_members, "params:raw_dir", "members", name="load_members"),
            node(load_claims, "params:raw_dir", "claims_unpaid", name="load_claims"),
            node(
                simulate_paid_dates,
                ["claims_unpaid", "params:paid_lag"],
                "claims",
                name="simulate_paid_dates",
            ),
        ]
    )

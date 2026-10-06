from kedro.pipeline import Pipeline, node

from .nodes import reconcile, run_dbt


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                run_dbt, ["features", "claims", "params:warehouse"], "warehouse_db", name="run_dbt"
            ),
            node(
                reconcile,
                ["features", "warehouse_db", "params:warehouse"],
                "reconciliation",
                name="reconcile_dbt",
            ),
        ]
    )

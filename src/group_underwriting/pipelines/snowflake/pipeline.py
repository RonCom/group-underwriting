from kedro.pipeline import Pipeline, node

from .nodes import load_kedro_inputs, load_raw, reconcile_snowflake, run_dbt_snowflake


def create_pipeline(**kwargs) -> Pipeline:
    """Needs the `snowflake` extra, SNOWFLAKE_* env vars and a finished `warehouse` run."""
    return Pipeline(
        [
            node(load_raw, "params:snowflake", "sf_raw_loaded", name="sf_load_raw"),
            node(
                load_kedro_inputs,
                ["claims", "member_groups", "params:snowflake"],
                "sf_kedro_loaded",
                name="sf_load_kedro_inputs",
            ),
            node(
                run_dbt_snowflake,
                ["sf_raw_loaded", "sf_kedro_loaded", "params:snowflake"],
                "sf_dbt_done",
                name="sf_dbt_build",
            ),
            node(
                reconcile_snowflake,
                ["sf_dbt_done", "params:snowflake"],
                "sf_reconciliation",
                name="sf_reconcile",
            ),
        ]
    )

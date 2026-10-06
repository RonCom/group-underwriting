"""Load raw DE-SynPUF and Kedro inputs into Snowflake, build dbt there, reconcile with DuckDB."""

from .pipeline import create_pipeline

__all__ = ["create_pipeline"]

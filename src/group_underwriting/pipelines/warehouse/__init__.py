"""Build the dbt project and reconcile its feature mart with the Kedro features row for row."""

from .pipeline import create_pipeline

__all__ = ["create_pipeline"]

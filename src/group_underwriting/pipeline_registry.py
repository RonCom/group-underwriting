"""Project pipelines."""

from __future__ import annotations

from kedro.framework.project import find_pipelines
from kedro.pipeline import Pipeline


def register_pipelines() -> dict[str, Pipeline]:
    """All pipelines. `__default__` leaves out synthetic data generation and the dbt warehouse
    (which needs the `dbt` extra)."""
    pipelines = dict(find_pipelines(raise_errors=True))
    optional = {
        k: pipelines.pop(k)
        for k in ("synthetic", "warehouse", "followup", "retest")
        if k in pipelines
    }
    pipelines["__default__"] = sum(pipelines.values(), Pipeline([]))
    pipelines.update(optional)
    return pipelines

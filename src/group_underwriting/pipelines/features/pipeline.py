from kedro.pipeline import Pipeline, node

from .nodes import assign_groups, build_cohorts, build_features, estimate_trend


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(build_cohorts, ["members", "params:cohorts"], "cohorts", name="build_cohorts"),
            node(
                assign_groups, ["cohorts", "params:groups"], "member_groups", name="assign_groups"
            ),
            node(
                build_features,
                ["claims", "member_groups", "params:features"],
                "features",
                name="build_features",
            ),
            node(
                estimate_trend,
                ["claims", "members", "params:cohorts", "params:features"],
                "trend",
                name="estimate_trend",
            ),
        ]
    )

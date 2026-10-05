"""End-to-end synthetic run on a small population, written to a temporary directory."""

from pathlib import Path

import pandas as pd
from kedro.framework.session import KedroSession
from kedro.framework.startup import bootstrap_project

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_pipeline_end_to_end(tmp_path):
    bootstrap_project(ROOT)
    params = {
        "data_root": str(tmp_path / "data"),
        "synthetic": {"n_members": 8000},
        "reporting": {
            "results_file": str(tmp_path / "docs" / "results.md"),
            "figures_dir": str(tmp_path / "docs" / "figures"),
            "n_boot": 20,
        },
        "pricing": {"n_boot": 20, "n_sims": 100},
    }
    for pipeline in ("synthetic", "__default__"):
        with KedroSession.create(
            project_path=ROOT, env="synthetic", runtime_params=params
        ) as session:
            session.run(pipeline_names=[pipeline])

    results = (tmp_path / "docs" / "results.md").read_text()
    assert "## Stop-loss pricing by group size (test)" in results
    assert len(list((tmp_path / "docs" / "figures").glob("*.png"))) == 6

    f = pd.read_parquet(tmp_path / "data" / "04_feature" / "features.parquet")
    train = set(f.loc[f["split"] == "train", "member_id"])
    test = set(f.loc[f["split"] == "test", "member_id"])
    assert not train & test
    assert set(f.loc[f["split"] == "train", "feature_year"]) == {2008}
    assert set(f.loc[f["split"] == "test", "feature_year"]) == {2009}
    groups = f.groupby("group_id")["split"].nunique()
    assert (groups == 1).all()

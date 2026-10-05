import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from group_underwriting.metrics import auc, average_precision, cluster_bootstrap, gini


def test_auc_and_average_precision_match_sklearn_with_ties():
    rng = np.random.default_rng(0)
    y = (rng.random(4000) < 0.05).astype(int)
    p = np.round(rng.random(4000) + 0.3 * y, 2)
    assert np.isclose(auc(y, p), roc_auc_score(y, p))
    assert np.isclose(average_precision(y, p), average_precision_score(y, p))


def test_gini_is_one_for_perfect_order_and_near_zero_for_noise():
    rng = np.random.default_rng(1)
    y = rng.gamma(1.0, 1000, 5000)
    assert np.isclose(gini(y, y), 1.0)
    assert abs(gini(y, rng.random(5000))) < 0.05


def test_cluster_bootstrap_resamples_whole_clusters():
    df = pd.DataFrame({"g": np.repeat(["a", "b", "c"], [1, 2, 3]), "x": 1.0})
    seen = []

    def stat(d):
        seen.append(sorted(d.groupby("g").size().unique()))
        return {"n": len(d)}

    cluster_bootstrap(df, "g", stat, n_boot=50, seed=0)
    # each resampled cluster appears with a multiple of its own size
    for sizes in seen:
        assert all(s in {1, 2, 3, 4, 6, 9} for s in sizes)

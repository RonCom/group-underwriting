import numpy as np
from scipy import integrate, stats

from group_underwriting.pipelines.pricing.nodes import _tweedie_draws
from group_underwriting.pipelines.tail.nodes import gpd_stop_loss


def test_gpd_stop_loss_matches_numerical_integral():
    xi, sigma = 0.3, 20000.0
    for t in [0.0, 10000.0, 75000.0]:
        num, _ = integrate.quad(lambda y: stats.genpareto.sf(y, xi, 0, sigma), t, np.inf)
        assert np.isclose(gpd_stop_loss(t, xi, sigma), num, rtol=1e-6)


def test_gpd_stop_loss_exponential_limit():
    assert np.isclose(gpd_stop_loss(5000.0, 0.0, 10000.0), 10000 * np.exp(-0.5))


def test_tweedie_draws_have_target_mean_and_variance():
    rng = np.random.default_rng(0)
    mu, phi, p = np.array([5000.0]), np.array([800.0]), 1.5
    x = _tweedie_draws(rng, mu, phi, p, 200_000)[:, 0]
    assert np.isclose(x.mean(), 5000, rtol=0.02)
    assert np.isclose(x.var(), 800 * 5000**1.5, rtol=0.05)
    assert (x == 0).mean() > 0  # point mass at zero


def test_spliced_excess_matches_numerical_integral():
    import pandas as pd

    from group_underwriting.pipelines.tail.nodes import gpd_survival, spliced_excess

    f1 = pd.DataFrame([{"threshold": 25000, "xi": 0.1, "sigma": 16000}])
    f2 = pd.DataFrame([{"threshold": 100000, "xi": -0.1, "sigma": 30000}])
    pred = pd.DataFrame(
        {
            "member_id": ["a"],
            "split": ["test"],
            "group_id": ["g"],
            "target_cost": [0.0],
            "p_glm_25000": [0.5],
            "p_gbm_25000": [0.5],
        }
    )
    out = spliced_excess(pred, f1, f2, [25000, 50000, 100000, 150000])

    def surv(x):
        if x < 100000:
            return 0.5 * gpd_survival(x - 25000, 0.1, 16000)
        return 0.5 * gpd_survival(75000, 0.1, 16000) * gpd_survival(x - 100000, -0.1, 30000)

    for d in [25000, 50000, 100000, 150000]:
        num = integrate.quad(surv, d, 100000)[0] if d < 100000 else 0.0
        num += integrate.quad(surv, max(d, 100000), 100000 + 300000)[0]
        assert np.isclose(out[f"exp_excess_glm_{d}"].iloc[0], num, rtol=1e-5)

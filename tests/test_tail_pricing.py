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

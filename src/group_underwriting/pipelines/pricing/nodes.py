"""Expected specific and aggregate stop-loss cost per test group, against actual outcomes.

Each group is priced twice, with the GLM and with the LightGBM models. Per group g with
specific deductible d_g (set by size band):
- expected claims    E[S]    = sum of member predicted annualized cost x exposure
- expected specific  E[Spec] = sum of member E[(X - d_g)+] from the GPD tail
- expected net       E[N]    = E[S] - E[Spec]
- aggregate attachment A     = corridor x E[N]
- expected aggregate E[Agg]  = E[(N - A)+] by Monte Carlo: member costs are drawn from the fitted
  Tweedie (compound Poisson-gamma), capped at d_g, summed per group and rescaled so the
  simulated mean equals E[N].
Premium = (E[N] + E[Spec] + E[Agg]) x (1 + load). Priced loss ratio = expected claims / premium;
actual loss ratio = actual claims / premium.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ...metrics import cluster_bootstrap

log = logging.getLogger(__name__)


def _tweedie_draws(rng, mu: np.ndarray, phi: np.ndarray, p: float, n_sims: int) -> np.ndarray:
    """Compound Poisson-gamma draws with mean mu and variance phi * mu**p, shape (n_sims, n)."""
    lam = mu ** (2 - p) / (phi * (2 - p))
    alpha = (2 - p) / (p - 1)
    theta = phi * (p - 1) * mu ** (p - 1)
    n = rng.poisson(lam, size=(n_sims, len(mu)))
    return rng.gamma(n * alpha, 1.0) * theta


def price_groups(
    features: pd.DataFrame,
    predictions: pd.DataFrame,
    excess: pd.DataFrame,
    cost_models: dict,
    params: dict,
) -> pd.DataFrame:
    """Price every test group with each cost model (and the matching HCC model for specific)."""
    test = (
        features.loc[
            features["split"] == "test",
            ["member_id", "group_id", "size_band", "exposure", "target_cost"],
        ]
        .merge(
            predictions.loc[predictions["split"] == "test", ["member_id", "pred_glm", "pred_gbm"]],
            on="member_id",
        )
        .merge(
            excess.loc[excess["split"] == "test"].drop(
                columns=["split", "group_id", "target_cost"]
            ),
            on="member_id",
        )
    )
    deductible = {b: float(d) for b, d in params["specific_deductible_by_band"].items()}
    test["deductible"] = test["size_band"].map(deductible)
    if test["deductible"].isna().any():
        raise ValueError("Every size band needs a specific deductible")
    test["act_specific"] = np.clip(test["target_cost"] - test["deductible"], 0, None)
    d_col = test["deductible"].astype(int).astype(str)
    out = []
    for model in ("glm", "gbm"):
        rng = np.random.default_rng(params["seed"])
        t = test.assign(
            pred=test[f"pred_{model}"],
            mu=test[f"pred_{model}"] * test["exposure"],
            exp_specific=[
                test.at[i, f"exp_excess_{model}_{d}"]
                for i, d in zip(test.index, d_col, strict=True)
            ],
        )
        out.append(
            _price(t, rng, cost_models["tweedie_power"], cost_models["phi"][model], params).assign(
                model=model
            )
        )
    log.info("Priced %d groups with each cost model", out[0].shape[0])
    return pd.concat(out, ignore_index=True)


def _empirical_draws(
    rng, pred: np.ndarray, exposure: np.ndarray, pool: pd.DataFrame, n_sims: int
) -> np.ndarray:
    """Member annual costs as pred x exposure x a ratio resampled from already-seen members in
    the same band of predicted rate (`pool`: columns band_lo, band_hi, ratio). Shape (n_sims, n)."""
    edges = np.sort(pool["band_lo"].unique())
    band = np.searchsorted(edges, pred, side="right") - 1
    out = np.empty((n_sims, len(pred)))
    for b in np.unique(band):
        ratios = pool.loc[pool["band_lo"] == edges[b], "ratio"].to_numpy()
        cols = np.flatnonzero(band == b)
        out[:, cols] = rng.choice(ratios, size=(n_sims, len(cols)))
    return out * pred * exposure


def _price(
    test: pd.DataFrame, rng, p: float, phi: float, params: dict, pool: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Price each group. Member cost draws are Tweedie(mu, phi) unless `pool` is given, in which
    case they resample actual / predicted ratios (`_empirical_draws`)."""
    rows = []
    for gid, g in test.groupby("group_id", sort=True):
        e = g["exposure"].to_numpy()
        if pool is None:
            sims = _tweedie_draws(rng, g["pred"].to_numpy(), phi / e, p, params["n_sims"]) * e
        else:
            sims = _empirical_draws(rng, g["pred"].to_numpy(), e, pool, params["n_sims"])
        net_sims = np.minimum(sims, g["deductible"].to_numpy()).sum(axis=1)
        exp_claims = g["mu"].sum()
        exp_spec = g["exp_specific"].sum()
        exp_net = exp_claims - exp_spec
        net_sims *= exp_net / net_sims.mean()
        attach = params["aggregate_corridor"] * exp_net
        act_claims = g["target_cost"].sum()
        act_spec = g["act_specific"].sum()
        act_net = act_claims - act_spec
        rows.append(
            {
                "group_id": gid,
                "size_band": g["size_band"].iloc[0],
                "members": len(g),
                "member_months": 12 * e.sum(),
                "specific_deductible": g["deductible"].iloc[0],
                "expected_claims": exp_claims,
                "expected_specific": exp_spec,
                "expected_net": exp_net,
                "aggregate_attachment": attach,
                "expected_aggregate": np.mean(np.clip(net_sims - attach, 0, None)),
                "p_aggregate_hit": np.mean(net_sims > attach),
                "actual_claims": act_claims,
                "actual_specific": act_spec,
                "actual_net": act_net,
                "actual_aggregate": max(act_net - attach, 0.0),
                "net_sim_sd": float(net_sims.std()),
                # mid-rank PIT of the actual net claims within the simulated distribution
                "pit": float(np.mean(net_sims < act_net) + 0.5 * np.mean(net_sims == act_net)),
            }
        )
    out = pd.DataFrame(rows)
    out["premium"] = (
        out["expected_net"] + out["expected_specific"] + out["expected_aggregate"]
    ) * (1 + params["load"])
    out["expected_pmpm"] = out["expected_claims"] / out["member_months"]
    out["actual_pmpm"] = out["actual_claims"] / out["member_months"]
    out["priced_loss_ratio"] = out["expected_claims"] / out["premium"]
    out["actual_loss_ratio"] = out["actual_claims"] / out["premium"]
    return out


def summarize_by_band(priced: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Priced vs actual loss ratio by size band, intervals from resampling groups."""

    def stat(d: pd.DataFrame) -> dict[str, float]:
        return {
            "priced_loss_ratio": d["expected_claims"].sum() / d["premium"].sum(),
            "actual_loss_ratio": d["actual_claims"].sum() / d["premium"].sum(),
            "actual_to_expected": d["actual_claims"].sum() / d["expected_claims"].sum(),
            "specific_a_to_e": d["actual_specific"].sum() / d["expected_specific"].sum(),
        }

    rows = []
    bands = [*sorted(priced["size_band"].unique(), key=lambda b: int(b.split("-")[0])), "All"]
    for model, b in [(m, b) for m in priced["model"].unique() for b in bands]:
        pm = priced[priced["model"] == model]
        d = pm if b == "All" else pm[pm["size_band"] == b]
        ci = cluster_bootstrap(d, "group_id", stat, params["n_boot"], params["seed"])
        row = {
            "model": model,
            "label": pm["label"].iloc[0] if "label" in pm.columns else model,
            "size_band": b,
            "groups": len(d),
            "members": int(d["members"].sum()),
            "aggregate_hits": int((d["actual_aggregate"] > 0).sum()),
            "expected_aggregate_hits": float(d["p_aggregate_hit"].sum()),
        }
        for _, r in ci.iterrows():
            row[r["metric"]] = r["estimate"]
            row[f"{r['metric']}_lo"] = r["lo"]
            row[f"{r['metric']}_hi"] = r["hi"]
        rows.append(row)
    return pd.DataFrame(rows)


def price_variants(
    features: pd.DataFrame,
    predictions: pd.DataFrame,
    excess: pd.DataFrame,
    spliced: pd.DataFrame,
    cost_models: dict,
    calibration: pd.DataFrame,
    variants: dict,
    params: dict,
    residual_pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Price every test group under each named model configuration.

    A variant picks the cost model, the claimant model behind the specific excess, the tail
    (`single` GPD or `spliced`), whether the cost model's level calibration factor is applied,
    and the member-cost simulation (`tweedie`, the default, or `empirical`, which needs
    `residual_pool`).
    """
    test = features.loc[
        features["split"] == "test",
        ["member_id", "group_id", "size_band", "exposure", "target_cost"],
    ].merge(
        predictions.loc[predictions["split"] == "test", ["member_id", "pred_glm", "pred_gbm"]],
        on="member_id",
    )
    deductible = {b: float(d) for b, d in params["specific_deductible_by_band"].items()}
    test["deductible"] = test["size_band"].map(deductible)
    if test["deductible"].isna().any():
        raise ValueError("Every size band needs a specific deductible")
    test["act_specific"] = np.clip(test["target_cost"] - test["deductible"], 0, None)
    factors = dict(zip(calibration["model"], calibration["factor"], strict=True))
    tails = {"single": excess, "spliced": spliced}
    out = []
    for name, v in variants.items():
        frame = tails[v["tail"]].set_index("member_id").reindex(test["member_id"])
        exp_spec = np.array(
            [
                frame.at[m, f"exp_excess_{v['claimant']}_{int(d)}"]
                for m, d in zip(test["member_id"], test["deductible"], strict=True)
            ]
        )
        factor = factors[v["cost"]] if v["calibrate"] else 1.0
        pred = test[f"pred_{v['cost']}"] * factor
        t = test.assign(pred=pred, mu=pred * test["exposure"], exp_specific=exp_spec)
        rng = np.random.default_rng(params["seed"])
        empirical = v.get("simulation", "tweedie") == "empirical"
        if empirical and (residual_pool is None or residual_pool.empty):
            log.warning("Variant %s: no residual pool, simulating with Tweedie", name)
            empirical = False
        priced = _price(
            t,
            rng,
            cost_models["tweedie_power"],
            cost_models["phi"][v["cost"]],
            params,
            pool=residual_pool if empirical else None,
        )
        out.append(priced.assign(model=name, label=v["label"]))
        log.info("Priced variant %s (level factor %.4f)", name, factor)
    return pd.concat(out, ignore_index=True)


def build_residual_pool(params: dict) -> pd.DataFrame:
    """Actual / predicted annual cost ratios from already-seen samples scored by the frozen
    models, in `n_bands` equal-count bands of predicted rate. Predictions use the cost model and
    level factor named in `params`."""
    frames = [pd.read_parquet(f) for f in params["files"] if Path(f).exists()]
    if not frames:
        log.warning("No residual-pool files found; empirical variants fall back to Tweedie")
        return pd.DataFrame({"band_lo": [], "ratio": []})
    p = pd.concat(frames)
    p = p[p["split"] == "test"]
    rate = p[f"pred_{params['cost']}"] * params["level_factor"]
    ratio = p["target_cost"] / (rate * p["exposure"])
    edges = np.quantile(rate, np.linspace(0, 1, params["n_bands"] + 1)[:-1])
    edges[0] = -np.inf
    band = np.searchsorted(edges, rate, side="right") - 1
    log.info("Residual pool: %d members in %d bands", len(p), params["n_bands"])
    return pd.DataFrame({"band_lo": edges[band], "ratio": ratio.to_numpy()})

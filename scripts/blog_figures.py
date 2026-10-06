"""Figures for the blog post (docs/blog/posts/group-underwriting.md). Run after the real, followup, retest and holdout runs:

uv run python scripts/blog_figures.py
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from group_underwriting.pipelines.reporting.nodes import evaluate_excess  # noqa: E402

OUT = Path("docs/assets/group-underwriting")
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
    }
)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print("wrote", OUT / name)


def claims_by_year():
    d = duckdb.sql("""
        WITH c AS (SELECT year(from_dt) y, sum(allowed) a, count(*) n
                   FROM 'data/real/02_intermediate/claims.parquet' GROUP BY 1),
             m AS (SELECT year y, sum(least(months_a, months_b)) mm
                   FROM 'data/real/02_intermediate/members.parquet' WHERE months_hmo = 0 GROUP BY 1)
        SELECT c.y, a / mm AS pmpm FROM c JOIN m USING (y) WHERE c.y BETWEEN 2008 AND 2010 ORDER BY 1
    """).df()
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    colors = [BLUE, BLUE, ORANGE]
    ax.bar(d["y"].astype(str), d["pmpm"], color=colors, width=0.55)
    for x, v in zip(d["y"].astype(str), d["pmpm"], strict=True):
        ax.text(x, v + 12, f"${v:,.0f}", ha="center", color=INK)
    ax.set_ylabel("Allowed cost per member-month")
    ax.set_ylim(0, d["pmpm"].max() * 1.18)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("2010 claims drop 36% (DE-SynPUF Sample 2)")
    save(fig, "claims_by_year.png")


def ae_by_run():
    rows = [
        (
            "Sample 2, 2009 → 2010\n(frozen baseline)",
            "data/real/08_reporting/pricing_by_band.parquet",
            "baseline",
        ),
        (
            "Sample 3, 2008 → 2009\n(frozen baseline)",
            "data/sample3/08_reporting/pricing_by_band.parquet",
            "glm",
        ),
        (
            "Sample 4, 2008 → 2009\n(frozen baseline)",
            "data/sample4/08_reporting/pricing_by_band.parquet",
            "glm",
        ),
        (
            "Sample 5, 2008 → 2009\n(model of record)",
            "data/sample5/08_reporting/pricing_by_band.parquet",
            "recalibrated",
        ),
    ]
    recs = []
    for label, path, model in rows:
        p = pd.read_parquet(path)
        r = p[(p["model"] == model) & (p["size_band"] == "All")].iloc[0]
        recs.append(
            (label, r["actual_to_expected"], r["actual_to_expected_lo"], r["actual_to_expected_hi"])
        )
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for i, (_label, est, lo, hi) in enumerate(recs):
        c = ORANGE if i == 0 else BLUE
        ax.plot([lo, hi], [i, i], color=c, lw=2, solid_capstyle="round")
        ax.plot(est, i, "o", color=c, ms=8, mec=SURFACE, mew=2)
        ax.text(hi + 0.015, i, f"{est:.2f}", va="center", color=INK)
    ax.axvline(1, color=MUTED, lw=1, ls="--")
    ax.set_yticks(range(len(recs)), [r[0] for r in recs])
    ax.invert_yaxis()
    ax.set_xlim(0.5, 1.15)
    ax.set_xlabel("Group claims, actual / expected (95% interval)")
    ax.set_title("On target wherever the cost year is complete")
    save(fig, "actual_to_expected_by_run.png")


def tail():
    s5 = Path("data/sample5")
    single = evaluate_excess(
        pd.read_parquet(s5 / "07_model_output/member_excess.parquet"),
        [25000, 50000, 100000],
        {"n_boot": 500, "seed": 9},
    )
    spliced = evaluate_excess(
        pd.read_parquet(s5 / "07_model_output/spliced_member_excess.parquet"),
        [25000, 50000, 100000],
        {"n_boot": 500, "seed": 9},
    )
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for off, (name, tab, c) in enumerate(
        (("One Pareto above $25k", single, ORANGE), ("Spliced at $100k", spliced, BLUE))
    ):
        t = tab[(tab["model"] == "glm") & (tab["metric"] == "actual_to_expected")]
        for i, r in enumerate(t.itertuples()):
            y = i + (off - 0.5) * 0.28
            ax.plot([r.lo, r.hi], [y, y], color=c, lw=2, solid_capstyle="round")
            ax.plot(
                r.estimate,
                y,
                "o",
                color=c,
                ms=8,
                mec=SURFACE,
                mew=2,
                label=name if i == 0 else None,
            )
            ax.text(r.hi + 0.02, y, f"{r.estimate:.2f}", va="center", color=INK, fontsize=9)
    ax.axvline(1, color=MUTED, lw=1, ls="--")
    ax.set_yticks(range(3), ["Above $25k", "Above $50k", "Above $100k"])
    ax.invert_yaxis()
    ax.set_xlabel("Excess loss, actual / expected (Sample 5, 95% interval)")
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("A single Pareto tail overprices the far tail")
    save(fig, "tail_single_vs_spliced.png")


def loss_ratio_by_band():
    p = pd.read_parquet("data/sample5/08_reporting/pricing_by_band.parquet")
    p = p[(p["model"] == "recalibrated") & (p["size_band"] != "All")]
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for i, r in enumerate(p.itertuples()):
        ax.plot(
            [r.actual_loss_ratio_lo, r.actual_loss_ratio_hi],
            [i, i],
            color=BLUE,
            lw=2,
            solid_capstyle="round",
        )
        ax.plot(r.actual_loss_ratio, i, "o", color=BLUE, ms=8, mec=SURFACE, mew=2)
        ax.text(0.903, i, f"{r.groups} groups", va="center", color=MUTED, fontsize=9)
    priced = p["priced_loss_ratio"].iloc[0]
    ax.axvline(priced, color=MUTED, lw=1, ls="--")
    ax.text(priced + 0.001, -0.75, f"priced {priced:.2f}", color=MUTED, fontsize=9)
    ax.set_xlim(0.83, 0.92)
    ax.set_ylim(len(p) - 0.5, -1.0)
    ax.set_yticks(range(len(p)), [f"{b} lives" for b in p["size_band"]])
    ax.set_xlabel("Actual loss ratio (Sample 5, model of record, 95% interval)")
    ax.set_title("Small groups carry the most pricing noise")
    save(fig, "loss_ratio_by_band.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    claims_by_year()
    ae_by_run()
    tail()
    loss_ratio_by_band()

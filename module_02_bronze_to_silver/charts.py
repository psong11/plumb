"""
Module 02 · the pictures.

    python -m module_02_bronze_to_silver.charts

Two charts. The first one is the most important image in this repo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meridian.style import (BRASS, BRONZE, DANGER, GOOD, INK, INK2, INK3,
                            LINE, SILVER, figure, save)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "charts"


def chart_dwell_overlap(df: pd.DataFrame):
    """Why your bot filter can never hit 100%.

    Plot how fast each session moves between events. Bots cluster hard on the
    left — sub-second, metronomic. Humans sit on the right. And then there's the
    middle, where they OVERLAP, and the middle is full of real customers who
    happen to move fast: the `checker` persona looking up an order, the
    `restocker` who knows exactly where the paper towels are.

    Wherever you put the threshold line, you are choosing which mistake to make.
    Move it right, you catch more bots and delete more customers. Move it left,
    you keep every customer and your pageviews stay inflated.

    There is no position on this axis that is correct. That is the entire lesson,
    and no summary statistic can show it to you — only the picture can.
    """
    df = df.sort_values(["session_id", "event_ts"])
    gaps = df.groupby("session_id")["event_ts"].diff().dt.total_seconds()
    feats = pd.DataFrame({
        "median_gap": gaps.groupby(df["session_id"]).median(),
        "depth": df.groupby("session_id").size(),
        "truth": df.groupby("session_id")["_is_bot"].any().astype(bool),
    }).dropna()
    feats = feats[feats["depth"] >= 8]

    fig, ax = figure(title="The bot filter's tradeoff, drawn",
                     subtitle="every session with 8+ events. wherever you put the line, you are choosing which mistake to make.")
    bins = np.logspace(np.log10(.03), np.log10(200), 62)
    ax.hist(feats.loc[~feats["truth"], "median_gap"], bins=bins, color=GOOD,
            alpha=.72, label="real people")
    ax.hist(feats.loc[feats["truth"], "median_gap"], bins=bins, color=DANGER,
            alpha=.72, label="actual bots")
    ax.set_xscale("log")
    ax.axvline(1.6, color=INK, lw=1.8, ls="--")
    ax.text(1.6, ax.get_ylim()[1] * .92, "  our threshold: 1.6s",
            color=INK, fontsize=10, fontweight="600")
    ax.text(.62, ax.get_ylim()[1] * .72,
            "bots we catch", color=DANGER, fontsize=10, fontweight="600")
    ax.text(2.4, ax.get_ylim()[1] * .55,
            "customers we keep", color=GOOD, fontsize=10, fontweight="600")
    ax.set_xlabel("median seconds between events in a session  (log)", color=INK2, fontsize=10)
    ax.set_ylabel("sessions", color=INK2, fontsize=10)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")
    return save(fig, OUT / "02_bot_overlap.png")


def chart_restatement(df: pd.DataFrame):
    """Sessions hold still. Conversion doesn't.

    Report each day twice: once at 6am the next morning, once after every
    straggler has landed. Traffic looks rock solid — and conversion moves,
    because the events that arrive late are the ones at the END of a session,
    which is where the money is.
    """
    d = df.copy()
    d["event_date"] = d["event_ts"].dt.floor("D")
    report_at = d["event_date"] + pd.Timedelta(days=1) + pd.Timedelta(hours=6)
    early = d[d["ingested_at"] <= report_at]

    def conv(x):
        g = x.groupby("event_date")
        sess = g["derived_session_id"].nunique()
        buys = g.apply(lambda s: int((s["event_name"] == "purchase").sum()),
                       include_groups=False)
        return (buys / sess.replace(0, 1)), sess

    ce, se = conv(early)
    cf, sf = conv(d)
    keep = sf[sf > 50].index
    ce, cf, se, sf = ce[keep], cf[keep], se[keep], sf[keep]
    x = np.arange(len(keep))
    lbl = [i.strftime("%a\n%m-%d") for i in keep]

    fig, (a1, a2) = __import__("matplotlib.pyplot", fromlist=["x"]).subplots(
        1, 2, figsize=(12.5, 4.8), dpi=150)
    fig.patch.set_facecolor("#FFFDF8")
    for ax, (early_v, final_v, ttl, sub, fmt) in zip(
            (a1, a2),
            [(se, sf, "Sessions barely move", "traffic looks stable. it is.", "{:,.0f}"),
             (ce * 100, cf * 100, "Conversion moves a lot",
              "same days, same definition, days apart.", "{:.1f}%")]):
        ax.set_facecolor("#FFFDF8")
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        for s in ("left", "bottom"): ax.spines[s].set_color(LINE)
        ax.grid(axis="y", color=LINE, lw=.7); ax.set_axisbelow(True)
        ax.bar(x - .19, early_v, .38, color=SILVER, label="reported next morning")
        ax.bar(x + .19, final_v, .38, color=BRASS, label="final, after stragglers")
        ax.set_xticks(x); ax.set_xticklabels(lbl, fontsize=8, color=INK3)
        ax.tick_params(colors=INK3, labelsize=9)
        ax.set_title(ttl, color=INK, fontsize=13, fontweight="600", loc="left", pad=18)
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=9.5, va="bottom")
        ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2)
    return save(fig, OUT / "02_restatement.png")


def main():
    silver = ROOT / "data" / "silver_events.parquet"
    if not silver.exists():
        sys.exit("no silver data — run: python -m module_02_bronze_to_silver.run")
    df = pd.read_parquet(silver)
    print()
    for fn in (chart_dwell_overlap, chart_restatement):
        p = fn(df)
        print(f"  ✓ {p.relative_to(ROOT)}")
        print(f"    {' '.join(fn.__doc__.strip().splitlines()[0].split())}\n")


if __name__ == "__main__":
    main()

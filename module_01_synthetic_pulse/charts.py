"""
Module 01 · the pictures.

    python -m module_01_synthetic_pulse.charts

Writes PNGs to charts/. Three things that are invisible in a summary table and
obvious the second you plot them.
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


def chart_lag(df: pd.DataFrame):
    """Ingestion lag — and why 'average latency' is a lie.

    Almost everything lands in under two seconds. Then there's a population
    sitting hours to days out to the right: the phones that were offline. Those
    two groups are not one distribution with a big variance. They're two
    different physical situations sharing a column, and a single p95 hides that
    completely.
    """
    lag = (df["ingested_at"] - df["_true_ts"]).dt.total_seconds().clip(lower=.05)
    # NOTE: parquet round-trips these ground-truth flags as object dtype holding
    # True/None, so `~col` would do integer negation and silently produce garbage
    # indices instead of a boolean mask. `.astype(bool)` is load-bearing.
    buf = df.get("_was_buffered", pd.Series(False, index=df.index)).fillna(False).astype(bool)

    fig, ax = figure(title="Ingestion lag has two populations, not one",
                     subtitle="log scale. the hump on the right is phones that were offline — same column, different physics.")
    bins = np.logspace(np.log10(.05), np.log10(max(lag.max(), 10)), 70)
    ax.hist(lag[~buf], bins=bins, color=SILVER, label="arrived normally", alpha=.9)
    ax.hist(lag[buf], bins=bins, color=DANGER, label="flushed after going offline", alpha=.95)
    ax.set_xscale("log")
    # y is ALSO log, and that is not a stylistic choice. The offline population is
    # ~700 events against ~70,000 normal ones; on a linear axis it is literally
    # invisible and the chart contradicts its own title. Rare-but-consequential
    # is the whole shape of data quality work, and linear axes hide it every time.
    ax.set_yscale("log")
    ax.set_xlabel("seconds between the event happening and us receiving it", color=INK2, fontsize=10)
    ax.set_ylabel("events  (log)", color=INK2, fontsize=10)
    for secs, lbl in [(60, "1 min"), (3600, "1 hr"), (86400, "1 day")]:
        if secs < lag.max():
            ax.axvline(secs, color=LINE, lw=1, ls="--")
            ax.text(secs, ax.get_ylim()[1] * .96, f" {lbl}", color=INK3, fontsize=8, va="top")
    late = lag[buf]
    if len(late):
        top = ax.get_ylim()[1]
        ax.annotate(f"{len(late):,} events, up to {late.max()/3600:.0f} hours late",
                    (late.median(), top * .30), textcoords="offset points", xytext=(0, 34),
                    ha="center", color=DANGER, fontsize=10, fontweight="600",
                    arrowprops=dict(arrowstyle="->", color=DANGER, lw=1.2))
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")
    return save(fig, OUT / "01_ingestion_lag.png")


def chart_traffic(df: pd.DataFrame):
    """The diurnal curve — why fake data needs SHAPE.

    If this were flat, a timezone bug would be invisible. Because it has a real
    evening peak, a timezone bug looks like the peak moved to 3am, which you'd
    catch in one glance. Give your synthetic data shape so that errors look like
    errors.
    """
    ok = df[(df["event_ts"] > "2020-01-01") & (df["event_ts"] < "2030-01-01")]
    by_hour = ok.groupby(ok["event_ts"].dt.hour)["session_id"].nunique()

    fig, ax = figure(h=4.4, title="Traffic has a heartbeat, and that's deliberate",
                     subtitle="a flat curve hides bugs. a real evening peak makes a timezone error visible in one glance.")
    ax.fill_between(by_hour.index, by_hour.values, color=BRASS, alpha=.18)
    ax.plot(by_hour.index, by_hour.values, color=BRASS, lw=2.2)
    peak = by_hour.idxmax()
    ax.scatter([peak], [by_hour.max()], color=BRASS, s=48, zorder=5)
    ax.annotate(f"peak {peak:02d}:00 — couch time", (peak, by_hour.max()),
                textcoords="offset points", xytext=(-12, 14), color=INK, fontsize=10, fontweight="600")
    ax.set_xticks(range(0, 24, 3))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_xlabel("hour of day (UTC)", color=INK2, fontsize=10)
    ax.set_ylabel("sessions", color=INK2, fontsize=10)
    return save(fig, OUT / "01_traffic_shape.png")


def chart_bot_share(df: pd.DataFrame):
    """The one number that reframes everything: 6% of sessions, 32% of events.

    A scraper views forty products; a human views four. So bots are a rounding
    error in your session count and a third of your pageviews. Any metric with
    pageviews in the denominator is already wrong, and nothing errored.
    """
    s = df.groupby("session_id")["_is_bot"].any().astype(bool)
    sess = [int((~s).sum()), int(s.sum())]
    bot = df["_is_bot"].fillna(False).astype(bool)
    ev = [int((~bot).sum()), int(bot.sum())]

    fig, ax = figure(h=3.6, title="Bots are 6% of your sessions and a third of your pageviews",
                     subtitle="same traffic, two denominators. this is why the metric you pick decides the answer you get.")
    for i, (vals, lbl) in enumerate([(sess, "sessions"), (ev, "events")]):
        tot = sum(vals)
        ax.barh(i, vals[0] / tot * 100, color=SILVER, height=.5)
        ax.barh(i, vals[1] / tot * 100, left=vals[0] / tot * 100, color=DANGER, height=.5)
        ax.text(vals[0] / tot * 100 + vals[1] / tot * 50, i, f"{vals[1]/tot:.1%} bot",
                ha="center", va="center", color="white", fontsize=11, fontweight="700")
    ax.set_yticks([0, 1]); ax.set_yticklabels(["sessions", "events"], fontsize=11, color=INK)
    ax.set_xlim(0, 100); ax.set_xlabel("% of total", color=INK2, fontsize=10)
    ax.grid(False); ax.spines["left"].set_visible(False)
    return save(fig, OUT / "01_bot_share.png")


def main():
    bronze = ROOT / "data" / "bronze_events.parquet"
    if not bronze.exists():
        sys.exit("no bronze data — run: python -m module_01_synthetic_pulse.run")
    df = pd.read_parquet(bronze)
    print()
    for fn in (chart_lag, chart_traffic, chart_bot_share):
        p = fn(df)
        print(f"  ✓ {p.relative_to(ROOT)}")
        print(f"    {' '.join(fn.__doc__.strip().splitlines()[0].split())}\n")


if __name__ == "__main__":
    main()

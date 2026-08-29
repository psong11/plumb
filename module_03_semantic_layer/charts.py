"""
Module 03 · the pictures.

    python -m module_03_semantic_layer.charts

Two charts about the same uncomfortable idea: the number you get depends on a
decision somebody made, and most of those decisions are invisible by default.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meridian.style import (BRASS, BRONZE, DANGER, GOOD, INK, INK2, INK3,
                            LINE, SILVER, figure, save)
from module_03_semantic_layer import compiler as C
from module_03_semantic_layer.engine import connect, execute

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "charts"


def chart_two_conversions(layer, con):
    """Two governed definitions of one word — and the gap between them BREATHES.

    This chart taught me something I did not expect when I built it, so read it
    carefully.

    Per day, the two definitions are ~6% apart. Over the full two weeks, they're
    ~46% apart. Same two definitions. Same data. Same SQL.

    Why: within a single day most visitors have exactly one session, so
    "per session" and "per visitor" are nearly the same question. Stretch the
    window to two weeks and a visitor accumulates several sessions, the
    per-session denominator inflates, and the two definitions pull apart.

    So the ambiguity isn't a fixed offset you could footnote once and forget.
    **It scales with the reporting period.** A daily conversion rate and a
    monthly conversion rate computed from the same governed definition are not
    on the same scale, and stacking them in one deck is an apples-to-oranges
    comparison that looks completely legitimate.

    Two things fall out of this, and they're the reason the chart is here:

      · TRENDS survive definitional ambiguity — both lines move together, so
        week-over-week direction is safe from either definition.
      · LEVELS do not. "We convert at 6%" is quoting a choice, not a fact, and
        the choice includes the window length, which nobody says out loud.

    In a meeting, "over what window, and per what?" is the highest-value
    question you can ask about any rate. It is almost never on the slide.
    """
    rows = {}
    for metric in ("conversion_rate_sessions", "conversion_rate_visitors"):
        spec = C.MetricSpec(metric=metric, dimensions=["event_date"])
        C.validate_spec(spec, layer)
        ans = execute(spec, layer, C.compile_spec(spec, layer), con=con)
        d = pd.DataFrame(ans.rows)
        d = d[d["value"].notna()]
        rows[metric] = d.set_index("event_date")["value"] * 100

    a = rows["conversion_rate_sessions"]
    b = rows["conversion_rate_visitors"]
    idx = a.index.intersection(b.index)[1:-1]
    a, b = a[idx], b[idx]

    fig, ax = figure(title="One question. Two governed answers. Neither is wrong.",
                     subtitle="the gap is not error — it's the denominator. and it grows with the window.")
    ax.fill_between(range(len(idx)), a.values, b.values, color=BRASS, alpha=.13)
    ax.plot(range(len(idx)), b.values, color=BRASS, lw=2.4, marker="o", ms=4,
            label="per visitor  ·  owner: finance")
    ax.plot(range(len(idx)), a.values, color=SILVER, lw=2.4, marker="o", ms=4,
            label="per session  ·  owner: web-analytics")
    ax.set_xticks(range(len(idx)))
    ax.set_xticklabels([pd.Timestamp(i).strftime("%m-%d") for i in idx], fontsize=8.5)
    ax.set_ylabel("conversion rate (%)", color=INK2, fontsize=10)
    # the aggregate over the whole window, for contrast — this is the payload
    agg = {}
    for m in ("conversion_rate_sessions", "conversion_rate_visitors"):
        sp = C.MetricSpec(metric=m)
        C.validate_spec(sp, layer)
        agg[m] = execute(sp, layer, C.compile_spec(sp, layer), con=con).value or 0
    whole = agg["conversion_rate_visitors"] / max(agg["conversion_rate_sessions"], 1e-9) - 1

    mid = len(idx) // 2
    ax.annotate(f"{(b.mean()/a.mean()-1):.0%} apart on any given day…",
                (mid, (a.values[mid] + b.values[mid]) / 2),
                textcoords="offset points", xytext=(14, -4), color=INK,
                fontsize=10.5, fontweight="600", va="center")
    ax.text(.5, -.20, f"…but {whole:.0%} apart over the whole {len(idx)}-day window. "
                      f"Same definitions. The ambiguity scales with the reporting period.",
            transform=ax.transAxes, ha="center", color=DANGER,
            fontsize=11, fontweight="600")
    fig.subplots_adjust(bottom=.26)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=INK2, loc="lower left")
    fig.tight_layout(rect=(0, .07, 1, 1))
    return save(fig, OUT / "03_two_conversions.png")


def chart_default_filters(layer, con):
    """What the default filters silently remove before you ever see a number.

    `exclude_bots` and `closed_days_only` are on for every metric unless someone
    explicitly waives them. That's the right default — but notice how much
    traffic disappears between "everything we logged" and "what the metric
    counts," and notice that a reader of the final number sees none of it.

    This is why the answer envelope carries the quality manifest. The filters
    are defensible. Their invisibility is not.
    """
    counts = []
    labels = ["everything in silver", "− suspected bots", "− past the watermark"]
    for waive in (["exclude_bots", "closed_days_only"], ["closed_days_only"], []):
        spec = C.MetricSpec(metric="pageviews", waive_default_filters=waive)
        C.validate_spec(spec, layer)
        ans = execute(spec, layer, C.compile_spec(spec, layer), con=con)
        counts.append(ans.value or 0)

    fig, ax = figure(h=4.2, title="What the defaults remove before you see the number",
                     subtitle="pageviews. every step is a defensible decision. none of them are visible in the answer.")
    colors = [SILVER, BRASS, BRASS]
    ax.barh(range(3), counts, color=colors, height=.55)
    for i, v in enumerate(counts):
        drop = (v / counts[0] - 1) if i else 0
        ax.text(v * 1.01, i, f"  {v:,.0f}" + (f"   ({drop:+.1%})" if i else ""),
                va="center", color=INK, fontsize=10.5,
                fontweight="600" if i else "400")
    ax.set_yticks(range(3)); ax.set_yticklabels(labels, fontsize=10.5, color=INK)
    ax.invert_yaxis(); ax.grid(False); ax.spines["left"].set_visible(False)
    ax.set_xlim(0, max(counts) * 1.3)
    ax.set_xlabel("pageviews counted", color=INK2, fontsize=10)
    return save(fig, OUT / "03_default_filters.png")


def main():
    if not (ROOT / "data" / "silver_events.parquet").exists():
        sys.exit("no silver data — run: python -m module_02_bronze_to_silver.run")
    layer = C.load_semantic_layer()
    con = connect()
    try:
        print()
        for fn in (chart_two_conversions, chart_default_filters):
            p = fn(layer, con)
            print(f"  ✓ {p.relative_to(ROOT)}")
            print(f"    {' '.join(fn.__doc__.strip().splitlines()[0].split())}\n")
    finally:
        con.close()


if __name__ == "__main__":
    main()

"""
Module 01 runner.

    python -m module_01_synthetic_pulse.run --answers      # see the destination
    python -m module_01_synthetic_pulse.run                # your own code
    python -m module_01_synthetic_pulse.run --sessions 20000 --days 14

Writes data/bronze_events.parquet — the raw, unretouched, deeply cursed event
log that Module 02 has to make sense of. Do not clean it here. Bronze is
immutable and bronze is honest; cleaning belongs downstream where it can be
audited and re-run. If you find yourself "just fixing this one thing" in
Module 01, you have accidentally invented an untraceable silent data mutation,
which is how most bad warehouses begin.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module_01_synthetic_pulse.generator import generate_clean_events
from module_01_synthetic_pulse.pathologies import Chaos, LOSS_LEDGER, corrupt

OUT = Path(__file__).resolve().parents[1] / "data" / "bronze_events.parquet"


def summarize(clean: list[dict], dirty: list[dict]) -> None:
    """Print the before/after. This table IS the lesson — screenshot it."""
    d = pd.DataFrame(dirty)
    sessions_clean = len({e["session_id"] for e in clean})
    sessions_dirty = d["session_id"].nunique()
    dupes = int(d.get("_is_duplicate", pd.Series(dtype=bool)).fillna(False).sum())
    buffered = int(d.get("_was_buffered", pd.Series(dtype=bool)).fillna(False).sum())
    drifted = int(d.get("_drifted", pd.Series(dtype=bool)).fillna(False).sum())
    bots = int(d["_is_bot"].sum())
    bot_sessions = int(d.loc[d["_is_bot"], "session_id"].nunique())
    purch_clean = sum(1 for e in clean if e["event_name"] == "purchase")
    purch_dirty = int((d["event_name"] == "purchase").sum())

    lag = (d["ingested_at"] - d["_true_ts"]).dt.total_seconds()

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  WHAT JUST HAPPENED TO YOUR DATA                                     ║
╚══════════════════════════════════════════════════════════════════════╝

  events        {len(clean):>10,}  clean  →  {len(dirty):>10,}  bronze
  sessions      {sessions_clean:>10,}  clean  →  {sessions_dirty:>10,}  bronze
  PURCHASES     {purch_clean:>10,}  clean  →  {purch_dirty:>10,}  bronze   ← {purch_clean - purch_dirty} vanished

  duplicate rows in bronze .................. {dupes:>8,}
  events flushed late from offline devices .. {buffered:>8,}
  events with drifted schema (item_id) ...... {drifted:>8,}
  bot SESSIONS .............................. {bot_sessions:>8,}  ({bot_sessions / max(sessions_dirty, 1):.1%} of sessions)
  bot EVENTS ................................ {bots:>8,}  ({bots / max(len(dirty), 1):.1%} of events)
     ^^ read those two lines again. Bots are a rounding error in your
        session count and a QUARTER of your pageviews, because a scraper
        views 40 products while a human views 4. Any metric with pageviews
        in the denominator is already lying to you and nothing errored.
  beacons that never fired .................. {LOSS_LEDGER.get('dropped', 0):>8,}
    ...of which were PURCHASES .............. {LOSS_LEDGER.get('dropped_purchases', 0):>8,}

  ingestion lag   p50 {lag.quantile(.50):>10.1f}s
                  p95 {lag.quantile(.95):>10.1f}s
                  max {lag.max():>10,.0f}s   ← that's {lag.max() / 3600:.1f} hours

  event_ts range  {d['event_ts'].min()}
               →  {d['event_ts'].max()}
                  (if you see 1970 or 2038 in there, that's pathology 3
                   working correctly and your future self screaming)

  ──────────────────────────────────────────────────────────────────────
  You just lost {purch_clean - purch_dirty} orders and gained {dupes:,} phantom events, and NOT ONE
  ERROR WAS RAISED. No exception. No failed job. No alert. If you loaded
  this straight into a dashboard it would render beautifully and be wrong.

  That silence is the entire reason this repo exists.

  →  Module 02. Go get your numbers back.
  ──────────────────────────────────────────────────────────────────────
""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=8000)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--answers", action="store_true",
                    help="use the reference implementations for 5-7")
    args = ap.parse_args()

    clean = generate_clean_events(n_sessions=args.sessions, days=args.days, seed=args.seed)
    dirty = corrupt([dict(e) for e in clean], Chaos(), use_answers=args.answers)

    df = pd.DataFrame(dirty).sort_values("ingested_at").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)

    summarize(clean, dirty)
    print(f"  wrote {OUT}  ({len(df):,} rows, {len(df.columns)} cols)\n")


if __name__ == "__main__":
    main()

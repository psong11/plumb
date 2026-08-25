"""
Module 02 runner.

    python -m module_02_bronze_to_silver.run --answers
    python -m module_02_bronze_to_silver.run

Reads data/bronze_events.parquet, writes data/silver_events.parquet and
data/quality_manifest.json. Run Module 01 first or there's nothing to read.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module_02_bronze_to_silver import silver as S
from module_02_bronze_to_silver.quality import (
    print_scorecard, restatement_demo, score_bot_filter)

ROOT = Path(__file__).resolve().parents[1]
BRONZE = ROOT / "data" / "bronze_events.parquet"
SILVER = ROOT / "data" / "silver_events.parquet"
QUARANTINE = ROOT / "data" / "quarantine_events.parquet"
MANIFEST = ROOT / "data" / "quality_manifest.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", action="store_true")
    ap.add_argument("--lateness-hours", type=float, default=72.0)
    args = ap.parse_args()

    if not BRONZE.exists():
        sys.exit("no bronze data — run: python -m module_01_synthetic_pulse.run --answers")

    quarantine = S._answer_quarantine            if args.answers else S.quarantine_impossible_timestamps
    dedupe     = S._answer_deduplicate           if args.answers else S.deduplicate
    drift      = S._answer_resolve_schema_drift  if args.answers else S.resolve_schema_drift
    bots       = S._answer_classify_bots         if args.answers else S.classify_bots
    sess       = S._answer_sessionize            if args.answers else S.sessionize

    df = pd.read_parquet(BRONZE)
    m = S.Manifest(rows_in=len(df))

    df, q = quarantine(df, m)
    df = dedupe(df, m)
    df = drift(df, m)
    df = bots(df, m)
    df = sess(df, m)
    df = S.apply_watermark(df, m, lateness_hours=args.lateness_hours)
    m.rows_out = len(df)

    SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SILVER, index=False)
    if len(q):
        q.to_parquet(QUARANTINE, index=False)
    MANIFEST.write_text(json.dumps(asdict(m), indent=2, default=str))

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  DATA QUALITY MANIFEST                                               ║
║  the thing your agent will read before it opens its mouth            ║
╚══════════════════════════════════════════════════════════════════════╝

  rows in  (bronze) ......................... {m.rows_in:>10,}
  rows out (silver) ......................... {m.rows_out:>10,}

  quarantined: impossible timestamps ........ {m.quarantined_timestamps:>10,}  ({m.rate(m.quarantined_timestamps):.2%})
  removed:     duplicate deliveries ......... {m.duplicates_removed:>10,}  ({m.rate(m.duplicates_removed):.2%})
  recovered:   drifted schema (item_id) ..... {m.drifted_rows_recovered:>10,}  ({m.rate(m.drifted_rows_recovered):.2%})
  flagged:     suspected bot events ......... {m.bot_events_flagged:>10,}  ({m.rate(m.bot_events_flagged):.2%})
  flagged:     suspected bot sessions ....... {m.bot_sessions_flagged:>10,}
  derived:     server-side sessions ......... {m.sessions_derived:>10,}
  rejected:    arrived past the watermark ... {m.events_after_watermark:>10,}
""")
    for n in m.notes:
        print(f"  • {n}\n")

    print_scorecard(score_bot_filter(df))

    print("  ┌─ THE SAME DAY, REPORTED TWICE ─────────────────────────────────────┐")
    print(restatement_demo(df).to_string())
    print("""
     LOOK AT WHICH COLUMN MOVED.

     Sessions: rock solid. Purchases: not. Because a session's first event
     arrives on time — the phone still had signal — and it's the TAIL that
     gets stuck in the tunnel. And the tail of a session is add_to_cart,
     begin_checkout, purchase. The money.

     So late data leaves your traffic dashboard looking perfect while quietly
     deflating conversion, then "fixing" it days later. Two dashboards, both
     wrong, neither erroring. THAT is why watermarks exist.

  →  Module 03. Now let's make sure only ONE of these numbers can be called
     "sessions," and that a machine can look up which one.
""")
    print(f"  wrote {SILVER.name}, {MANIFEST.name}"
          + (f", {QUARANTINE.name}" if len(q) else "") + "\n")


if __name__ == "__main__":
    main()

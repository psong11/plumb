"""
Module 03 demo.
    python -m module_03_semantic_layer.run

Needs data/silver_events.parquet from Module 02.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module_03_semantic_layer import compiler as C
from module_03_semantic_layer.engine import connect, execute


def main() -> None:
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    layer = C.load_semantic_layer()
    con = connect()

    def ask(name: str, **kw):
        r = resolve(name, layer)
        spec = C.MetricSpec(metric=r["resolved"], **kw)
        validate(spec, layer)
        sql = compile_(spec, layer)
        return execute(spec, layer, sql, con=con, ambiguity=r["message"])

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  "WHAT'S OUR CONVERSION RATE?"                                               ║
║  One question. Two governed answers. Both correct.                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    a = ask("conversion_rate")
    print(a.render())
    print()
    b = ask("conversion_rate_visitors")
    print(b.render())

    if a.value and b.value:
        print(f"""
  ────────────────────────────────────────────────────────────────────────────
  {a.value:.2%}  vs  {b.value:.2%}   — a {abs(b.value / a.value - 1):.0%} difference,
  and NEITHER IS WRONG. Different denominators. Different owners. Both governed.

  An agent that picked one and answered "our conversion rate is {a.value:.1%}"
  would have been fast, confident, helpful, and would have quietly deleted a
  real disagreement between two departments.

  That's the whole job. Not answering. Refusing to flatten.
  ────────────────────────────────────────────────────────────────────────────
""")

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SLICING — the allowlist in action                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    s = ask("sessions", dimensions=["device"])
    for row in s.rows:
        print(f"    {row['device']:<14} {row['value']:>10,.0f}")
    print(f"\n{s.render()}\n")

    print("""╔══════════════════════════════════════════════════════════════════════════════╗
║  THE COMPILED SQL — deterministic, auditable, boring                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    print("    " + s.compiled_sql.replace("\n", "\n    "))

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  WHAT HAPPENS WHEN THE MODEL ASKS FOR SOMETHING IT CAN'T HAVE                ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    for bad in (
        C.MetricSpec(metric="sessions", dimensions=["store_id"]),
        C.MetricSpec(metric="profit_margin"),
        C.MetricSpec(metric="sessions", limit=9_999_999),
        C.MetricSpec(metric="sessions", start_date="2026-08-20", end_date="2026-08-01"),
    ):
        try:
            validate(bad, layer)
            print(f"    ✗ NOT CAUGHT: {bad}")
        except C.SpecError as e:
            print(f"    ✓ rejected → {e}\n")

    print("""    Read those messages again. Every one names the ALLOWED values.

    That's deliberate: when validation fails you hand this string straight back
    to the model and let it retry. "invalid dimension" produces a second wrong
    guess. "allowed: [event_date, device, ...]" produces a correct one.

    Error messages are a prompt-engineering surface. Almost nobody treats them
    that way, and it is most of the difference between an agent that recovers
    and an agent that loops.

  →  Module 04: give this compiler to an LLM as three tools and let it drive.
     Notice how little is left to build. That's the point — the hard part was
     never the agent.
""")
    con.close()


if __name__ == "__main__":
    main()

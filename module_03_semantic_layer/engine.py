"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 03 · THE ENGINE AND THE ENVELOPE                                     ║
║  Where the number gets its caveats permanently stapled to it.                ║
╚══════════════════════════════════════════════════════════════════════════════╝

I wrote this one, and I want to point at the `MetricAnswer` dataclass below and
say: **that is the actual deliverable of this whole repo.**

Not the number. The envelope around the number.

Here's the failure mode it exists to prevent, and you will watch it happen in
real life within a month of shipping any agent over data:

    Marketing's agent asks your agent for conversion rate.
    Your agent returns 5.9%, plus three caveats about grain, bot filtering,
    and the fact that the last two days are still moving.
    Marketing's agent writes "Conversion rate: 5.9%" on a slide.
    The caveats evaporate. Silently. Instantly.
    A VP reads 5.9% as gospel and makes a decision.

The number survived the handoff. The uncertainty didn't. And nobody lied —
every agent in that chain behaved reasonably.

So the answer cannot be a float. It has to be a STRUCTURE that carries its own
provenance: which definition, which query, how fresh, what's suspect, who owns
it. Downstream consumers can still throw it away — you can't stop them — but
they have to do it on purpose, and the record exists.

Wallpaper rule 05, made concrete. This is the shape.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from module_03_semantic_layer.compiler import MetricSpec

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "data" / "silver_events.parquet"
MANIFEST = ROOT / "data" / "quality_manifest.json"


@dataclass
class MetricAnswer:
    """A number that cannot be separated from what it means.

    Every field here is load-bearing:

      metric / definition_sql   WHICH definition. Not "conversion rate" — the
                                exact governed SQL, so two answers can be
                                compared or proven incomparable.
      query_hash                Deterministic id of the spec. Same question →
                                same hash → cacheable, loggable, reproducible.
      caveats                   From the yaml. Rides along, always.
      data_quality              The manifest from Module 02. The ± .
      freshness                 When silver was last built. An answer without a
                                timestamp is a rumour.
      owner                     A human to argue with.
    """
    metric: str
    label: str
    owner: str
    grain: str
    value: float | None
    rows: list[dict]
    definition_sql: str
    compiled_sql: str
    query_hash: str
    caveats: list[str] = field(default_factory=list)
    data_quality: dict = field(default_factory=dict)
    freshness: str | None = None
    ambiguity_warning: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def render(self) -> str:
        """What a human sees. Note that the caveats are not in a footnote —
        they're in the body, above the fold, unskippable."""
        head = f"{self.label}: " + (
            f"{self.value:,.4g}" if self.value is not None else "—")
        lines = [head, f"  definition  {self.metric}  (owner: {self.owner}, "
                       f"grain: {self.grain})",
                 f"  as of       {self.freshness}"]
        if self.ambiguity_warning:
            lines.append(f"  ⚠ AMBIGUOUS  {self.ambiguity_warning}")
        dq = self.data_quality
        if dq:
            lines.append(
                f"  quality     bot events excluded {dq.get('bot_event_rate', 0):.1%} · "
                f"dupes removed {dq.get('duplicate_rate', 0):.2%} · "
                f"quarantined {dq.get('quarantine_rate', 0):.2%} · "
                f"{dq.get('events_after_watermark', 0)} events past watermark")
        for c in self.caveats:
            lines.append(f"  ⓘ {' '.join(c.split())}")
        lines.append(f"  query_hash  {self.query_hash}")
        return "\n".join(lines)


def spec_hash(spec: MetricSpec) -> str:
    """Stable id for a question.

    Sorted keys, so `{a,b}` and `{b,a}` hash the same. That's the whole reason
    this is a function and not an inline f-string: two agents asking the same
    question in a different field order should hit the same cache entry.
    """
    payload = {
        "metric": spec.metric, "dimensions": sorted(spec.dimensions),
        "start": spec.start_date, "end": spec.end_date,
        "filters": dict(sorted(spec.filters.items())),
        "waived": sorted(spec.waive_default_filters), "limit": spec.limit,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def load_quality_context() -> dict:
    """Turn Module 02's manifest into the ± that rides with every answer."""
    if not MANIFEST.exists():
        return {}
    m = json.loads(MANIFEST.read_text())
    n = max(m.get("rows_in", 0), 1)
    return {
        "rows_in": m.get("rows_in", 0),
        "rows_out": m.get("rows_out", 0),
        "duplicate_rate": m.get("duplicates_removed", 0) / n,
        "quarantine_rate": m.get("quarantined_timestamps", 0) / n,
        "bot_event_rate": m.get("bot_events_flagged", 0) / n,
        "schema_drift_rate": m.get("drifted_rows_recovered", 0) / n,
        "events_after_watermark": m.get("events_after_watermark", 0),
        "notes": m.get("notes", []),
    }


def connect(silver: Path = SILVER) -> duckdb.DuckDBPyConnection:
    """DuckDB over the silver parquet, registered as `silver_events`.

    Why DuckDB and not Spark? Because a cluster is a distraction while you're
    learning the idea. Everything here — the compiled SQL, the semantic layer,
    the envelope — ports to Databricks unchanged. The only thing that changes is
    what executes the string. Learn the idea on your laptop in 40ms; scale it
    when scale is the actual problem.
    """
    if not silver.exists():
        raise FileNotFoundError(
            f"{silver} missing — run module 02 first")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW silver_events AS SELECT * FROM read_parquet('{silver}')")
    return con


def execute(spec: MetricSpec, layer: dict, sql: str,
            con: duckdb.DuckDBPyConnection | None = None,
            ambiguity: str | None = None) -> MetricAnswer:
    """Run the compiled SQL and wrap the result in its provenance."""
    own = con is None
    con = con or connect()
    try:
        params = getattr(spec, "_params", [])
        df: pd.DataFrame = con.execute(sql, params).df()
    finally:
        if own:
            con.close()

    meta = layer["metrics"][spec.metric]
    scalar = float(df["value"].iloc[0]) if len(df) == 1 and "value" in df else None

    return MetricAnswer(
        metric=spec.metric,
        label=meta.get("label", spec.metric),
        owner=meta.get("owner", "unowned"),
        grain=meta.get("grain", "unknown"),
        value=scalar,
        rows=df.to_dict("records"),
        definition_sql=" ".join(meta["sql"].split()),
        compiled_sql=sql,
        query_hash=spec_hash(spec),
        caveats=list(meta.get("caveats", [])),
        data_quality=load_quality_context(),
        freshness=(datetime.fromtimestamp(SILVER.stat().st_mtime, tz=timezone.utc)
                   .isoformat(timespec="seconds") if SILVER.exists() else None),
        ambiguity_warning=ambiguity,
    )

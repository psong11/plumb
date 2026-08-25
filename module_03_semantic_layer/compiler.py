"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 03 · THE METRIC COMPILER                                             ║
║  ~150 lines that are worth more than any agent you will ever build.          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Alright. Modules 01 and 02 were data engineering. This one is the actual idea.

Here's the thing everybody builds first, and here's why it fails.

    THE THING EVERYBODY BUILDS:
        user question → LLM → SQL → warehouse → answer

    It demos beautifully. Then:
      · it joins events to sessions and quietly double-counts (fan-out)
      · it computes "conversion rate" three different ways on three different
        days and nobody notices because each one is individually plausible
      · it writes a cross join over a petabyte and that costs real money
      · nobody can audit what it did, because the SQL was invented once and
        never seen again

    THE THING THAT WORKS:
        user question → LLM → MetricSpec → *your compiler* → SQL → answer

The LLM's job shrinks from "author correct SQL over a schema you've never seen"
to "fill in a form with four fields." That is a dramatically smaller problem,
and — this is the part that matters — it is VERIFIABLE. You can validate a form.
You cannot validate arbitrary SQL.

Wallpaper rule 02. This file is where it becomes real.

┌────────────────────────────────────────────────────────────────────────────┐
│   1. validate_spec    ← YOU   the allowlist. the whole safety story.       │
│   2. compile_spec     ← YOU   spec → SQL, deterministically                │
│   3. resolve_metric   ← YOU   when a word means three things, say so       │
└────────────────────────────────────────────────────────────────────────────┘

  ⌘K ⌘0 folds the answer keys.    pytest module_03_semantic_layer -q
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).parent / "metrics.yaml"


# ══════════════════════════════════════════════════════════════════════════════
#  The form the LLM fills out
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class MetricSpec:
    """The entire interface between a language model and your warehouse.

    Look how small it is. Four fields and a couple of options. That's the whole
    surface area an LLM is allowed to touch, and everything outside it is code
    you wrote and tested.

    Compare that to "the model can write any SQL it wants." One of these you can
    reason about at 2am during an incident. The other you cannot.
    """
    metric: str
    dimensions: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    filters: dict[str, str] = field(default_factory=dict)   # dimension → value
    waive_default_filters: list[str] = field(default_factory=list)
    limit: int = 500


class SpecError(ValueError):
    """Raised when a spec asks for something that isn't allowed.

    IMPORTANT DESIGN NOTE, and it's a real one:

    The error message is written for the MODEL to read, not for a human. When
    validation fails, you hand the message back to the LLM and let it retry.
    So "unknown dimension 'store_id'; allowed: [event_date, device, ...]" is
    infinitely better than "invalid dimension" — the first one gets fixed on
    retry, the second one produces a second wrong guess.

    Error messages are a prompt-engineering surface. Almost nobody treats them
    that way and it's most of the difference between an agent that recovers and
    an agent that loops.
    """


def load_semantic_layer(path: Path = SPEC_PATH) -> dict:
    return yaml.safe_load(path.read_text())


# ══════════════════════════════════════════════════════════════════════════════
#  1 · VALIDATE_SPEC                                                 ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  This function is your security boundary, your cost control, and your
#  correctness guarantee, and it is about forty lines of `if` statements.
#
#  I want to be really clear about something, because it's the most common
#  mistake people make when they first build one of these:
#
#      YOU DO NOT ASK THE MODEL NICELY. YOU DO NOT PUT "only use approved
#      dimensions" IN THE PROMPT. YOU CHECK.
#
#  A prompt is a suggestion to a probabilistic system. This function is a
#  guarantee. Wallpaper rule 12 is the same idea one layer up: authorization
#  lives in the catalog, not the prompt. Same instinct, different layer.
#
#  And notice this is where cost control lives too. An unbounded date range over
#  a petabyte is a four-figure query. Here you cap it, and the cap is a number in
#  a config file that a human approved, not a vibe the model had.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   validate_spec(spec, layer) -> None   (raise SpecError, or return)
# │
# │ CHECK   1. spec.metric exists in layer["metrics"]. If not, raise with the
# │            list of valid metric names IN the message — the model reads it.
# │         2. every dimension in spec.dimensions is in layer["dimensions"].
# │         3. every key in spec.filters is a known dimension.
# │         4. every name in spec.waive_default_filters is a real default filter.
# │         5. 1 <= spec.limit <= 10_000.
# │         6. if both dates present, start_date <= end_date.
# │
# │ TRAP 1  Include the ALLOWED values in every error message. This is the
# │         difference between a model that self-corrects and one that loops.
# │ TRAP 2  Do not "helpfully" coerce an unknown dimension to a close match.
# │         Silent fuzzy-matching is how an agent answers a question nobody
# │         asked and everybody believes it.
# │ TRAP 3  Raise on the FIRST problem or collect all of them — your call, but
# │         collecting all of them means one retry instead of four. (I collect.)
# ╰──────────────────────────────────────────────────────────────────────────────
def validate_spec(spec: MetricSpec, layer: dict) -> None:
    raise NotImplementedError("the allowlist is the product.")


# region 🔒 ANSWER KEY 01
def _answer_validate_spec(spec: MetricSpec, layer: dict) -> None:
    metrics, dims = layer["metrics"], layer["dimensions"]
    defaults = layer.get("default_filters", {})
    problems: list[str] = []

    if spec.metric not in metrics:
        problems.append(
            f"unknown metric {spec.metric!r}; allowed: {sorted(metrics)}")

    for d in spec.dimensions:
        if d not in dims:
            problems.append(f"unknown dimension {d!r}; allowed: {sorted(dims)}")

    for k in spec.filters:
        if k not in dims:
            problems.append(f"cannot filter on {k!r}; filterable: {sorted(dims)}")

    for w in spec.waive_default_filters:
        if w not in defaults:
            problems.append(
                f"unknown default filter {w!r}; waivable: {sorted(defaults)}")

    if not 1 <= spec.limit <= 10_000:
        problems.append(f"limit {spec.limit} out of range 1..10000")

    if spec.start_date and spec.end_date and spec.start_date > spec.end_date:
        problems.append(f"start_date {spec.start_date} is after end_date {spec.end_date}")

    if problems:
        raise SpecError("; ".join(problems))
# endregion


# ══════════════════════════════════════════════════════════════════════════════
#  2 · COMPILE_SPEC                                                  ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  Now the payoff. A validated spec becomes SQL, and the SQL is DETERMINISTIC —
#  same spec in, byte-identical query out, every time, forever.
#
#  That property is worth more than it sounds. It means:
#    · you can cache on a hash of the spec
#    · you can log the spec instead of the SQL and reconstruct any answer
#    · two people asking the same question get literally the same query
#    · your test suite can assert on exact SQL strings
#
#  None of those are available when a model writes the SQL. Not one.
#
#  Also — every metric's `sql` comes from the yaml. You are never writing an
#  aggregate here. If you catch yourself typing COUNT( in this function, stop:
#  that's a definition, and definitions live in the semantic layer or they drift.
#  Rule 03.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   compile_spec(spec, layer) -> str
# │
# │ BUILD   SELECT  <dim sql> AS <dim name>, ... , <metric sql> AS value
# │         FROM    <source_table>
# │         WHERE   <default filters not waived>
# │           AND   event_ts >= / < date bounds   (if given)
# │           AND   <dimension filters, as parameters>
# │         GROUP BY <dim names>       (omit entirely if no dimensions)
# │         ORDER BY <first dim>       (omit if no dimensions)
# │         LIMIT   <limit>
# │
# │ TRAP 1  end_date must be INCLUSIVE of the whole day. `event_ts < end + 1 day`,
# │         not `<= end`, or you silently drop everything after midnight on the
# │         last day. This bug has shipped at every company you've heard of.
# │ TRAP 2  Filter VALUES must be parameterised, never f-stringed in. The value
# │         came from a language model that read a user's message. Treat it as
# │         hostile input, because rule 13 says an LLM's output is not
# │         trustworthy just because you wrote the prompt.
# │         → return SQL with `?` placeholders; engine.py binds them in order.
# │ TRAP 3  No dimensions = a single scalar row. Do NOT emit a bare GROUP BY.
# │ HINT    return the SQL string; put the ordered param values on
# │         spec._params (the engine looks for it). Ugly? A little. Ship it.
# ╰──────────────────────────────────────────────────────────────────────────────
def compile_spec(spec: MetricSpec, layer: dict) -> str:
    raise NotImplementedError("spec in, deterministic SQL out.")


# region 🔒 ANSWER KEY 02
def _answer_compile_spec(spec: MetricSpec, layer: dict) -> str:
    metric = layer["metrics"][spec.metric]
    dims = layer["dimensions"]
    params: list = []

    selects = [f'{dims[d]["sql"]} AS {d}' for d in spec.dimensions]
    selects.append(f'{" ".join(metric["sql"].split())} AS value')

    where: list[str] = []
    for name, f in layer.get("default_filters", {}).items():
        if name not in spec.waive_default_filters:
            where.append(f["sql"])

    if spec.start_date:
        where.append("event_ts >= ?")
        params.append(spec.start_date)
    if spec.end_date:
        # INCLUSIVE of the final day. `<= end_date` silently drops 23h59m of it.
        where.append("event_ts < CAST(? AS TIMESTAMP) + INTERVAL 1 DAY")
        params.append(spec.end_date)

    for k, v in spec.filters.items():
        where.append(f'{dims[k]["sql"]} = ?')
        params.append(v)

    sql = "SELECT\n  " + ",\n  ".join(selects)
    sql += f'\nFROM {layer["source_table"]}'
    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    if spec.dimensions:
        sql += "\nGROUP BY " + ", ".join(spec.dimensions)
        sql += f"\nORDER BY {spec.dimensions[0]}"
    sql += f"\nLIMIT {int(spec.limit)}"

    spec._params = params  # type: ignore[attr-defined]
    return sql
# endregion


# ══════════════════════════════════════════════════════════════════════════════
#  3 · RESOLVE_METRIC                                                ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  Last one, and it's the least technical and the most important.
#
#  Someone asks: "what's our conversion rate?"
#
#  There are two in the yaml. `conversion_rate_sessions`, owned by web-analytics.
#  `conversion_rate_visitors`, owned by finance. Different denominators. Both
#  correct. They will differ by a lot.
#
#  What should the agent do?
#
#  The tempting answer is "pick the default and answer." Fast, clean, feels
#  helpful. It is the single most damaging thing this system can do, because the
#  ambiguity is REAL and the agent just deleted it. Finance reads a
#  web-analytics number, calls it conversion rate, and now two departments are
#  quietly disagreeing with a machine's confidence stamped on it.
#
#  The right answer is: **surface the conflict, name the owners, and answer with
#  the default anyway — clearly labelled.** Don't stonewall the user. Don't hide
#  the fork. Do both.
#
#  This is the part of your job that isn't engineering. The reason "active user"
#  has six definitions is not that nobody wrote it down — it's that six teams
#  each need a different one and each is right. Your job is not to be the
#  arbiter of which is correct. It's to make the fork VISIBLE, assign it an
#  owner, and make the choice explicit every time.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   resolve_metric(name, layer) -> dict
# │
# │ OUT     {
# │           "resolved":    "<metric key you'd use>",
# │           "ambiguous":   bool,
# │           "candidates":  [{"key","label","owner","grain","description"}, ...],
# │           "message":     str | None   # human-readable, only when ambiguous
# │         }
# │
# │ DO      1. exact key match → resolved, ambiguous only if it declares
# │            `conflicts_with` (still list the alternatives!)
# │         2. no exact match → fuzzy: match on label, or on any metric whose
# │            key starts with the requested name. e.g. "conversion_rate" →
# │            both conversion_rate_* metrics.
# │         3. 2+ candidates → ambiguous=True, resolved = the first candidate
# │            sorted by key (deterministic), and a `message` naming every
# │            alternative WITH ITS OWNER.
# │         4. 0 candidates → raise SpecError listing valid metric names.
# │
# │ TRAP 1  Never return ambiguous=False when conflicts_with is populated. The
# │         conflict is a permanent property of the definition, not of the query.
# │ TRAP 2  Deterministic ordering. "Whichever dict key came first" is a bug
# │         that will make an answer change between runs for no visible reason.
# ╰──────────────────────────────────────────────────────────────────────────────
def resolve_metric(name: str, layer: dict) -> dict:
    raise NotImplementedError("three teams, three definitions, all correct.")


# region 🔒 ANSWER KEY 03
def _answer_resolve_metric(name: str, layer: dict) -> dict:
    metrics = layer["metrics"]
    n = name.strip().lower().replace(" ", "_")

    keys: list[str] = []
    if n in metrics:
        keys = [n] + [k for k in metrics[n].get("conflicts_with", []) if k in metrics]
    else:
        keys = [k for k, m in metrics.items()
                if k.startswith(n) or m.get("label", "").lower().replace(" ", "_") == n]

    if not keys:
        raise SpecError(f"unknown metric {name!r}; allowed: {sorted(metrics)}")

    keys = sorted(dict.fromkeys(keys))
    candidates = [{
        "key": k,
        "label": metrics[k].get("label", k),
        "owner": metrics[k].get("owner", "unowned"),
        "grain": metrics[k].get("grain", "unknown"),
        "description": " ".join(metrics[k].get("description", "").split()),
    } for k in keys]

    ambiguous = len(candidates) > 1
    resolved = keys[0] if n not in metrics else n

    message = None
    if ambiguous:
        others = [c for c in candidates if c["key"] != resolved]
        alts = "; ".join(
            f'{c["key"]} (owner: {c["owner"]}, grain: {c["grain"]})' for c in others)
        if n in metrics:
            # Exact match, but the definition declares a known conflict. We still
            # answer — the user was specific — but the fork stays visible.
            message = (
                f'{resolved} has {len(others)} governed sibling definition(s) that '
                f'answer the same business question differently: {alts}. Not '
                f'interchangeable — different denominators. Do not compare across them.')
        else:
            message = (
                f'"{name}" maps to {len(candidates)} governed definitions; answering '
                f'with {resolved} (owner: {metrics[resolved].get("owner","unowned")}). '
                f'Alternatives: {alts}. These are NOT interchangeable — they use '
                f'different denominators. Say which you meant, or ask the owner.')

    return {"resolved": resolved, "ambiguous": ambiguous,
            "candidates": candidates, "message": message}
# endregion

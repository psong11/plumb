<h1 align="center">plumb</h1>

<p align="center">
  <em>A plumb line is the reference you hold something against to see whether it's true.</em><br>
  <em>It's also, obviously, plumbing.</em>
</p>

---

Everyone is building AI agents over their data warehouse. Most of them are going to
produce confident, well-formatted, wrong numbers — not because the models are bad, but
because **the layer underneath was never built.**

`plumb` is a hands-on course in that layer. You build a realistic clickstream pipeline
for a fictional online bulk retailer, break it on purpose in the seven ways real
clickstream actually breaks, put it back together while measuring exactly what you lost,
and then put a governed semantic layer on top so that an agent physically cannot invent
a metric.

It's a learning repo. The commentary is loud on purpose.

---

## The thesis

> **The semantic layer is the product. The agent is just distribution.**

Bet everything on the agent and a mediocre v1 demo kills the program. Build the
substrate — governed definitions, data contracts, quantified loss — and the agent becomes
the thing that finally makes people *care* about the substrate. Even a disappointing agent
leaves a durable asset behind.

## The modules

| | | You build |
|---|---|---|
| **01** | [Synthetic Pulse](module_01_synthetic_pulse/) | A clickstream generator, then seven pathologies that ruin it: at-least-once duplicates, clock skew, bot spoofing, offline buffering, dropped beacons, unmanaged schema drift. |
| **02** | [Bronze → Silver](module_02_bronze_to_silver/) | Quarantine, dedup, drift resolution, behavioral bot classification (scored against ground truth), server-side sessionization, watermarks — every step emitting a data-quality manifest. |
| **03** | [Semantic Layer](module_03_semantic_layer/) | A metric compiler. Natural language → validated `MetricSpec` → deterministic SQL. Definitions live in YAML with owners and caveats; the compiler never writes an aggregate. |
| 04 | Agent *(next)* | Three tools, no raw SQL. |
| 05 | Evals *(next)* | 50 gold questions. A thumbs-down becomes a permanent test. |
| 06 | Red team *(next)* | Spend a week trying to make your own agent lie. |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

```bash
python -m module_01_synthetic_pulse.run && python -m module_02_bronze_to_silver.run && python -m module_03_semantic_layer.run
```

Then the charts — some of this is only visible as a distribution:

```bash
python -m module_01_synthetic_pulse.charts && python -m module_02_bronze_to_silver.charts && python -m module_03_semantic_layer.charts
```

```bash
pytest -q
```

## How to read it

Everything is implemented and runnable — this is a repo you **read and interrogate**, not
one you fill in. Each module's README lists the files in reading order. The commentary
lives in the code on purpose: traps are named where they happen, and every non-obvious
choice carries a `# DECISION:` note explaining why it went that way.

```python
    # DECISION: keep first-seen. A duplicate is by definition identical in
    # payload, so the only thing the later copy adds is a later ingested_at —
    # which would poison the watermark and make re-runs non-reproducible.
    out = (df.sort_values("ingested_at", kind="mergesort")
             .drop_duplicates(subset="event_id", keep="first"))
```

Read the tests too, and read only their docstrings. A test suite is the one piece of
documentation that cannot lie, because it runs.

## Why synthetic data

Because when you find something weird in someone else's dataset, you don't know if it's a
bug, a business rule, or you being dumb — and you can burn four hours on a null and never
find out. When *you* inject the mess, you know exactly what's in there. So when Module 02
gives you a session count 3% high, you don't guess: *"that's my duplicate injector, I set
it to 1.5%, why did 1.5% become 3%?"* That question has an answer, and the answer teaches
you something permanent about join fan-out.

You're building the answer key to your own exam.

It also means **every column has ground truth alongside it** (`_is_bot`, `_true_ts`), so
your bot filter gets a real confusion matrix instead of a vibe. Pipeline code that reads
those columns fails a test — label leakage is the most seductive bug in this discipline.

## Fourteen things that decide whether the number is true

The rules the repo is organized around:

**Architecture** — the semantic layer is the product · never language→SQL, always
language→metric spec · a glossary in prose drifts, a glossary that *is* the SQL can't

**The data** — don't chase lossless, chase quantified loss · uncertainty has to survive
into the answer · event time ≠ processing time · fix it at the producer or eat it for years

**The model** — RAG for documents, tool calls for numbers · facts live in tools, behavior
lives in weights · thumbs-down → eval case → forever, *that's* your RL · optimize for
satisfaction, harvest confident lies

**The guardrail** — authorization lives in the catalog, never in the prompt · private data
+ untrusted text + an outbound path = a leak

**The job** — the demo is easy; the boring layer is the whole job

---

<p align="center"><sub>Meridian Goods is invented. Any resemblance to a real retailer is the point of a well-chosen fiction.</sub></p>

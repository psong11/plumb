# Module 02 — Bronze → Silver

**Get your numbers back. Most of them. And know exactly which ones you didn't.**

---

## The reframe

You don't fix bronze. You **characterize** it.

Bronze is immutable and honest — exactly what arrived, warts included, never edited.
Silver is bronze plus *judgment*: deduplicated, sessionized, bot-scored, schema-reconciled.
Every one of those words is a **decision someone made**, and the difference between a
data platform and a pile of notebooks is whether those decisions are written down,
versioned, tested, and attached to the data as metadata.

So every transform here emits not just rows but **a count of what it did**. Those counts
become the quality manifest, the manifest rides to Module 03, and by Module 04 your agent
says *"42,100 sessions, ±3%, 6% suspected bot"* instead of *"42,100 sessions."*

## Run it

```bash
python -m module_02_bronze_to_silver.run --answers
```

## What you write

| # | Function | The thing it teaches |
|---|---|---|
| 1 | `quarantine_impossible_timestamps` | Quarantine ≠ filter. A filter hides the incident; a quarantine table reports it. |
| 2 | `deduplicate` | *Which* copy you keep is a policy decision with downstream consequences. |
| 3 | `resolve_schema_drift` | The coalesce is the easy half. Shouting about it is the point. |
| 4 | `classify_bots` | You will not hit 100%, and the false positives are your best customers. |
| 5 | `sessionize` | The 30-minute timeout is from 2005 and nobody can justify it. |

I wrote #6, `apply_watermark`, because the concept is subtle enough that seeing it beats
guessing at it. Read it carefully — it's the answer to the tunnel story.

```bash
pytest module_02_bronze_to_silver -q
```

21 tests. One of them reads your source code and fails if your pipeline touches a
ground-truth column (`_is_bot`, `_true_ts`, …). That isn't being cute: **label leakage is
the most seductive bug in this discipline.** Your filter hits 100%, you feel like a
genius, and it does nothing in production because `_is_bot` was never a real column.

---

## The two things you should stare at

**1. Your bot scorecard.** Something like 89% precision / 98% recall. That's a good filter.
It also means ~50 sessions you flagged were real people — and if you go read them, some
are `checker` and `restocker` personas: fast, deep, low-cart. Your most efficient customers
look exactly like robots. **Every point of recall costs you precision on the people who
matter most.** The deliverable was never a perfect filter. It's a filter with a *known*
precision and recall, published next to the number.

**2. The restatement table.** Same day, reported twice — once at 6am the next morning,
once after the stragglers landed:

```
             sessions_early  sessions_final   purchases_early  purchases_final  conv_moved
Wed 08-19               508             508                30               33     +10.00%
```

Sessions: identical. Purchases: **+10%.**

Why? A session's *first* event arrives on time — the phone still had signal. It's the
**tail** that gets stuck in the tunnel. And the tail of a session is `add_to_cart`,
`begin_checkout`, `purchase`. The money.

So late data leaves your traffic dashboard looking rock solid while quietly deflating
conversion, then "correcting" it days later. Two dashboards, both wrong, neither erroring.

**Freshness bias is not uniform across a funnel. It concentrates exactly where the value is.**

That's why watermarks exist, and why *"sessions look fine so the pipeline is fine"* should
make you nervous for the rest of your career.

---

**→ Module 03. Now let's make sure only one of these numbers can be called "sessions."**

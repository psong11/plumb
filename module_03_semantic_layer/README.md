# Module 03 — The Semantic Layer

**~150 lines that are worth more than any agent you will ever build.**

---

## The whole idea, in two diagrams

```
WHAT EVERYBODY BUILDS FIRST
    question → LLM → SQL → warehouse → answer
```

Demos beautifully. Then it joins events to sessions and double-counts. Then it computes
"conversion rate" three different ways on three different days, each individually
plausible. Then it writes a cross join that costs four figures. And nobody can audit any
of it, because the SQL was invented once and never seen again.

```
WHAT WORKS
    question → LLM → MetricSpec → your compiler → SQL → answer
```

The model's job shrinks from *"author correct SQL over a schema you've never seen"* to
*"fill in a form with four fields."* Smaller problem — and, crucially, a **verifiable**
one. You can validate a form. You cannot validate arbitrary SQL.

## Run it

```bash
python -m module_03_semantic_layer.run --answers
```

## What you write

| # | Function | The thing it teaches |
|---|---|---|
| 1 | `validate_spec` | The allowlist. Security, cost control, and correctness in forty lines of `if`. |
| 2 | `compile_spec` | Deterministic SQL. Same spec in, byte-identical query out, forever. |
| 3 | `resolve_metric` | When one word means three things, surface the fork — don't flatten it. |

```bash
pytest module_03_semantic_layer -q
```

---

## The moment this module exists for

Ask for "conversion rate" and you get:

```
Conversion rate (order / session):   6.47%   owner: web-analytics   grain: session
Conversion rate (order / visitor):   9.41%   owner: finance         grain: visitor
```

**A 46% difference. Neither is wrong.** Different denominators, different owners, both
governed, both defensible.

An agent that picked one and said *"our conversion rate is 6.5%"* would have been fast,
confident, helpful — and would have quietly deleted a real disagreement between two
departments, with a machine's authority stamped on it.

**That's the job. Not answering. Refusing to flatten.**

The reason "active user" has six definitions was never that nobody wrote it down. It's
that six teams each need a different one and each is right. You are not the arbiter of
which is correct. You make the fork visible, give it an owner, and force the choice to be
explicit every single time.

---

## Two details worth stealing for real work

**Error messages are a prompt-engineering surface.**

```
✓ rejected → unknown dimension 'store_id'; allowed: ['app_version', 'category',
             'device', 'event_date', 'membership_tier']
```

When validation fails you hand that string straight back to the model and let it retry.
`"invalid dimension"` produces a second wrong guess. Naming the allowed values produces a
correct one. This is most of the difference between an agent that recovers and one that loops.

**The answer is a structure, not a float.** `MetricAnswer` carries the definition id, the
compiled SQL, a query hash, the caveats, the quality manifest, and a freshness timestamp.
Because here's what happens otherwise: your agent returns 5.9% plus three caveats, the
calling agent writes "Conversion rate: 5.9%" on a slide, and the caveats evaporate
instantly. Nobody lied. Every agent behaved reasonably. The number survived the handoff
and the uncertainty didn't.

You can't stop a downstream consumer from throwing the envelope away — but they have to
do it *on purpose*, and the record exists.

---

**→ Module 04: hand this compiler to an LLM as three tools and let it drive. Notice how
little is left to build. That's the point — the hard part was never the agent.**

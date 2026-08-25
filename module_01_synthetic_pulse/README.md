# Module 01 — Synthetic Pulse

**Build a clickstream generator, then break it on purpose.**

---

## Why you're doing this

You could learn this on a messy public dataset. Here's why that's worse: when you
find something weird in someone else's data, you don't know whether it's a bug, a
business rule, or you being dumb. You can burn four hours on a null and never find out.

When *you* inject the mess, you know exactly what's in there. So when Module 02
gives you a session count that's 3% high, you don't guess — you go *"that's my
duplicate injector, I set it to 1.5%, why did 1.5% become 3%?"* And that question
has an answer that will teach you something permanent about join fan-out.

**You are building the answer key to your own exam.** That's the trick.

---

## Run it

```bash
python -m module_01_synthetic_pulse.run --answers
```

That uses my implementations so you can see the destination before you start walking.
Read the summary table it prints. Then drop `--answers` and go earn it.

## What you write

Open `pathologies.py`. Hit **⌘K ⌘0** immediately — that folds every answer key in
the file so your eyes can't cheat. (**⌘K ⌘J** unfolds, if you must.)

I wrote pathologies 1–4. Read them; #5 depends on a column #2 creates.
You write three:

| # | Function | The thing it teaches |
|---|---|---|
| 5 | `buffer_offline_events` | Event time ≠ processing time. Tuesday's number changes on Friday. |
| 6 | `drop_beacons` | Your most valuable event is your most fragile one. |
| 7 | `drift_schema` | One renamed field upstream = silent nulls downstream, forever. |

Each has a spec box with the traps called out. Grade yourself:

```bash
pytest module_01_synthetic_pulse -q
```

15 tests. Green means done. Each test's docstring tells you which trap you hit.

---

## Done when

`pytest module_01_synthetic_pulse -q` is green **without** `PLUMB_ANSWERS=1`, and
`data/bronze_events.parquet` exists.

Then look at what you made:

```
PURCHASES   487 clean  →  464 bronze   ← 23 vanished
bot SESSIONS    6.1% of sessions
bot EVENTS     32.3% of events
```

Twenty-three orders gone. A third of your pageviews are a scraper. **Not one error
was raised.** No exception, no failed job, no alert. Load that into a dashboard and
it renders beautifully and it's wrong.

That silence is the whole reason this repo exists.

**→ Module 02. Go get your numbers back.**

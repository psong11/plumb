# Module 01 — Synthetic Pulse

Build a realistic clickstream for a fictional bulk retailer, then break it in the seven
ways real clickstream actually breaks.

## Run

```bash
python -m module_01_synthetic_pulse.run
python -m module_01_synthetic_pulse.charts
```

## Read, in this order

| File | Why |
|---|---|
| `../meridian/world.py` | The world. Six visitor personas — note that `checker` and `bot` deliberately overlap. |
| `generator.py` | Clean traffic. Perfect, and therefore fictional. Nobody has ever had this data. |
| `pathologies.py` | The seven ways it breaks. Start at `Chaos`, then read 1→7, then `corrupt()` at the bottom. |
| `tests/test_pathologies.py` | What each pathology actually guarantees. The docstrings are the design decisions. |

## The thing to notice

```
PURCHASES     487 clean  →  464 bronze    ← 23 vanished
bot SESSIONS  6.1% of sessions
bot EVENTS   32.3% of events
```

Twenty-three orders gone, a third of your pageviews are a scraper, **and not one error was
raised.** No exception, no failed job, no alert. That silence is the whole subject.

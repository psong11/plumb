# Module 02 — Bronze → Silver

You don't *fix* bronze. You characterize it. Every transform here emits not just rows but
a count of what it did — and those counts become the ± that rides on every answer.

## Run

```bash
python -m module_02_bronze_to_silver.run
python -m module_02_bronze_to_silver.charts
```

## Read, in this order

| File | Why |
|---|---|
| `silver.py` → `Manifest` | Twelve fields. The most important object in the module and it looks like nothing. |
| `silver.py` 1–5 | quarantine · dedup · drift · bots · sessionize. Each one is a *decision*, not a fix. |
| `silver.py` → `apply_watermark` | "When is a day done?" — a business SLA wearing a technical costume. |
| `quality.py` | The scorer and the restatement demo. Read `restatement_demo`'s docstring twice. |
| `tests/test_silver.py` | Ends with a test that reads the pipeline's own source for label leakage. |

## The thing to notice

Sessions hold still. Conversion doesn't.

```
             sessions_early  sessions_final   purchases_early  purchases_final  conv_moved
Wed 08-19               508             508                30               33     +10.00%
```

A session's first event arrives on time — the phone still had signal. The **tail** gets
stuck in the tunnel, and the tail is `add_to_cart`, `begin_checkout`, `purchase`.
Freshness bias isn't uniform across a funnel. It concentrates where the money is.

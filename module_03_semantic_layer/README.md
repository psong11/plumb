# Module 03 — The Semantic Layer

Natural language → validated `MetricSpec` → deterministic SQL. The model fills out a form;
your code writes the query.

## Run

```bash
python -m module_03_semantic_layer.run
python -m module_03_semantic_layer.charts
```

## Read, in this order

| File | Why |
|---|---|
| `metrics.yaml` | Start here. This file is the product. Ten metrics, each with a grain, an owner, and caveats. |
| `compiler.py` → `MetricSpec` | Four fields. That is the entire surface a language model is allowed to touch. |
| `compiler.py` → `validate_spec` | Security, cost control and correctness, in forty lines of `if`. |
| `compiler.py` → `compile_spec` | Note the `GROUP BY` comment — a real collision I hit building this. |
| `engine.py` → `MetricAnswer` | The envelope. The actual deliverable of the whole repo. |

## The thing to notice

```
Conversion rate (order / session)   6.47%   owner: web-analytics   grain: session
Conversion rate (order / visitor)   9.41%   owner: finance         grain: visitor
```

46% apart over two weeks — but only **6% apart on any single day**. The ambiguity isn't a
fixed offset you can footnote once. It scales with the reporting window. Trends survive
definitional ambiguity; levels do not.

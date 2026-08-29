"""
Smoke tests for the entry points.

╔══════════════════════════════════════════════════════════════════════════════╗
║  WHY THIS FILE EXISTS — a real bug, caught embarrassingly late               ║
╚══════════════════════════════════════════════════════════════════════════════╝

While rewriting this repo, a refactor silently deleted the alias lines at the
top of two `run.py` files. Every single one of the 60 tests stayed green.

Read that again. Sixty passing tests, and `python -m module_02_bronze_to_silver.run`
crashed instantly with a NameError.

The tests covered every TRANSFORM. Nothing covered the thing a human actually
types. The entry point was the one piece of code with zero test coverage, and
it was the only piece the user ever touches.

That gap has a name in review: **testing the units and not the seam.** It is
one of the most common ways a green build ships a broken product, and it is
worth looking for specifically whenever you review a change — "is there a test
that exercises this the way a person would actually invoke it?"

These four tests take three seconds and would have caught it instantly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent

ENTRY_POINTS = [
    "module_01_synthetic_pulse.run",
    "module_01_synthetic_pulse.charts",
    "module_02_bronze_to_silver.run",
    "module_02_bronze_to_silver.charts",
    "module_03_semantic_layer.run",
    "module_03_semantic_layer.charts",
]


@pytest.mark.parametrize("mod", ENTRY_POINTS)
def test_entry_point_runs(mod):
    """Actually invoke it the way a person would. No mocks, no imports — the
    real command line, in a subprocess, exactly as documented in the README."""
    r = subprocess.run([sys.executable, "-m", mod], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, (
        f"`python -m {mod}` exited {r.returncode}\n"
        f"--- stderr ---\n{r.stderr[-2000:]}")

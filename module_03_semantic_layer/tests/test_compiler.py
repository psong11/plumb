"""
Your grader for Module 03.

    pytest module_03_semantic_layer -q
    PLUMB_ANSWERS=1 pytest module_03_semantic_layer -q

The SQL-execution tests need data/silver_events.parquet; they skip without it.
Everything else runs on the yaml alone.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from module_03_semantic_layer import compiler as C
from module_03_semantic_layer.engine import SILVER, connect, execute, spec_hash

USE_KEY = os.environ.get("PLUMB_ANSWERS") == "1"
validate = C._answer_validate_spec  if USE_KEY else C.validate_spec
compile_ = C._answer_compile_spec   if USE_KEY else C.compile_spec
resolve  = C._answer_resolve_metric if USE_KEY else C.resolve_metric


@pytest.fixture(scope="module")
def layer():
    return C.load_semantic_layer()


# ── 1 · validate ──────────────────────────────────────────────────────────────
def test_valid_spec_passes(layer):
    validate(C.MetricSpec(metric="sessions", dimensions=["device"]), layer)


def test_unknown_metric_is_rejected(layer):
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="profit_margin"), layer)


def test_unknown_dimension_is_rejected(layer):
    """The allowlist is the entire safety story. If this passes, you have
    text-to-SQL with extra steps."""
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="sessions", dimensions=["store_id"]), layer)


def test_errors_name_the_allowed_values(layer):
    """Written for the MODEL to read. 'invalid dimension' produces a second
    wrong guess; a list of valid options produces a correct retry."""
    with pytest.raises(C.SpecError) as e:
        validate(C.MetricSpec(metric="sessions", dimensions=["store_id"]), layer)
    assert "device" in str(e.value), "error must list what IS allowed"


def test_absurd_limit_is_rejected(layer):
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="sessions", limit=9_999_999), layer)


def test_backwards_date_range_is_rejected(layer):
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="sessions",
                              start_date="2026-08-20", end_date="2026-08-01"), layer)


def test_unknown_filter_key_is_rejected(layer):
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="sessions", filters={"zip_code": "72712"}), layer)


def test_unknown_waiver_is_rejected(layer):
    with pytest.raises(C.SpecError):
        validate(C.MetricSpec(metric="sessions",
                              waive_default_filters=["disable_everything"]), layer)


# ── 2 · compile ───────────────────────────────────────────────────────────────
def test_compile_is_deterministic(layer):
    """Same spec → byte-identical SQL. This is what makes caching, logging,
    and reproducing an answer possible at all."""
    a = compile_(C.MetricSpec(metric="sessions", dimensions=["device"]), layer)
    b = compile_(C.MetricSpec(metric="sessions", dimensions=["device"]), layer)
    assert a == b


def test_compile_applies_default_filters(layer):
    sql = compile_(C.MetricSpec(metric="sessions"), layer)
    assert "is_suspected_bot" in sql
    assert "arrived_after_watermark" in sql


def test_waiving_a_default_filter_removes_it(layer):
    sql = compile_(C.MetricSpec(metric="sessions",
                                waive_default_filters=["exclude_bots"]), layer)
    assert "is_suspected_bot" not in sql


def test_no_dimensions_means_no_group_by(layer):
    sql = compile_(C.MetricSpec(metric="sessions"), layer)
    assert "GROUP BY" not in sql.upper()


def test_end_date_is_inclusive_of_the_whole_day(layer):
    """`<= end_date` silently drops 23h59m of the final day. This bug has
    shipped at every company you have heard of."""
    spec = C.MetricSpec(metric="sessions", end_date="2026-08-20")
    sql = compile_(spec, layer)
    assert "INTERVAL 1 DAY" in sql.upper() or "+ 1" in sql, (
        "end_date must cover the entire final day")


def test_filter_values_are_parameterised_not_interpolated(layer):
    """The value came from an LLM that read a user's message. Treat it as
    hostile input — rule 13."""
    spec = C.MetricSpec(metric="sessions", filters={"device": "'; DROP TABLE x;--"})
    sql = compile_(spec, layer)
    assert "DROP TABLE" not in sql.upper(), "you f-stringed a model's output into SQL"
    assert "?" in sql
    assert "'; DROP TABLE x;--" in getattr(spec, "_params", [])


def test_metric_sql_comes_from_the_yaml(layer):
    """If you typed an aggregate in compile_spec, that's a definition living
    outside the semantic layer, and it will drift. Rule 03."""
    import inspect
    src = inspect.getsource(C.compile_spec if not USE_KEY else C._answer_compile_spec)
    assert "COUNT(" not in src.upper().replace("COUNT(*)", ""), (
        "no aggregates in the compiler — definitions live in metrics.yaml")


# ── 3 · resolve ───────────────────────────────────────────────────────────────
def test_exact_key_resolves_to_itself(layer):
    assert resolve("sessions", layer)["resolved"] == "sessions"


def test_ambiguous_name_is_flagged(layer):
    r = resolve("conversion_rate", layer)
    assert r["ambiguous"] is True
    assert len(r["candidates"]) >= 2
    assert r["message"]


def test_ambiguity_message_names_the_owners(layer):
    """A fork without an owner is a fork nobody can close."""
    r = resolve("conversion_rate", layer)
    assert "finance" in r["message"] and "web-analytics" in r["message"]


def test_declared_conflict_stays_ambiguous_even_on_exact_match(layer):
    """conflicts_with is a permanent property of the definition, not of the
    query. Asking precisely doesn't make the disagreement go away."""
    r = resolve("conversion_rate_sessions", layer)
    assert r["ambiguous"] is True


def test_resolution_is_deterministic(layer):
    a = [resolve("conversion_rate", layer)["resolved"] for _ in range(5)]
    assert len(set(a)) == 1


def test_unknown_name_raises_with_options(layer):
    with pytest.raises(C.SpecError) as e:
        resolve("vibes", layer)
    assert "sessions" in str(e.value)


# ── end to end ────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not SILVER.exists(), reason="run module 02 first")
def test_compiled_sql_actually_runs(layer):
    con = connect()
    try:
        for metric in layer["metrics"]:
            spec = C.MetricSpec(metric=metric, dimensions=["device"])
            validate(spec, layer)
            ans = execute(spec, layer, compile_(spec, layer), con=con)
            assert ans.rows
            assert ans.query_hash
    finally:
        con.close()


@pytest.mark.skipif(not SILVER.exists(), reason="run module 02 first")
def test_answer_carries_its_caveats_and_quality(layer):
    """The deliverable is not the number. It's the envelope."""
    con = connect()
    try:
        spec = C.MetricSpec(metric="conversion_rate_sessions")
        validate(spec, layer)
        ans = execute(spec, layer, compile_(spec, layer), con=con)
        assert ans.caveats, "an answer with no caveats is a rumour"
        assert ans.data_quality.get("bot_event_rate", 0) > 0
        assert ans.freshness
        assert ans.owner == "finance" or ans.owner == "web-analytics"
    finally:
        con.close()


def test_spec_hash_ignores_key_order(layer):
    a = C.MetricSpec(metric="sessions", filters={"device": "app", "category": "pantry"})
    b = C.MetricSpec(metric="sessions", filters={"category": "pantry", "device": "app"})
    assert spec_hash(a) == spec_hash(b)

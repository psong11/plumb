"""
The contract Module 02 actually guarantees.

    pytest module_02_bronze_to_silver -q

Needs data/bronze_events.parquet. Run Module 01 first.

Note the last test in this file. It reads the pipeline's own source and fails
if any of it touches a ground-truth column. That is an unusual kind of test —
it asserts on the CODE, not on the output — and it exists because label leakage
is the most seductive bug in this discipline. Your filter hits 100%, you feel
like a genius, and it does nothing in production because `_is_bot` was never a
real column.

Worth knowing that this kind of test exists. When you're reviewing a data or ML
change, "could this have leaked the label?" is one of the three questions that
catches the most real bugs.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from module_02_bronze_to_silver import silver as S
from module_02_bronze_to_silver.quality import score_bot_filter

quarantine = S.quarantine_impossible_timestamps
deduplicate = S.deduplicate
resolve_drift = S.resolve_schema_drift
classify_bots = S.classify_bots
sessionize = S.sessionize


BRONZE = ROOT / "data" / "bronze_events.parquet"


@pytest.fixture(scope="module")
def bronze():
    if not BRONZE.exists():
        pytest.skip("run `python -m module_01_synthetic_pulse.run` first")
    return pd.read_parquet(BRONZE)


@pytest.fixture
def m():
    return S.Manifest(rows_in=0)


# ── 1 · quarantine ────────────────────────────────────────────────────────────
def test_quarantine_returns_two_frames(bronze, m):
    m.rows_in = len(bronze)
    clean, bad = quarantine(bronze, m)
    assert isinstance(clean, pd.DataFrame) and isinstance(bad, pd.DataFrame)
    assert len(clean) + len(bad) == len(bronze), "you lost or duplicated rows"


def test_quarantine_catches_the_1970_events(bronze, m):
    """Pathology 3 planted these. If none are caught, your bounds are wrong."""
    m.rows_in = len(bronze)
    clean, bad = quarantine(bronze, m)
    assert len(bad) > 0
    assert (clean["event_ts"] >= S.PLAUSIBLE_START).all()


def test_quarantine_labels_the_reason(bronze, m):
    """A quarantine table without a reason column is a landfill, not a tool."""
    m.rows_in = len(bronze)
    _, bad = quarantine(bronze, m)
    assert "quarantine_reason" in bad.columns
    assert set(bad["quarantine_reason"].unique()) <= {"before_launch", "future_dated"}


def test_quarantine_uses_ingestion_as_the_future_bound(bronze, m):
    """You cannot receive an event before it happens. Free upper bound."""
    m.rows_in = len(bronze)
    clean, _ = quarantine(bronze, m)
    assert (clean["event_ts"] <= clean["ingested_at"] + S.FUTURE_TOLERANCE).all()


# ── 2 · deduplicate ───────────────────────────────────────────────────────────
def test_dedup_leaves_one_row_per_event_id(bronze, m):
    out = deduplicate(bronze, m)
    assert out["event_id"].is_unique


def test_dedup_keeps_first_seen(bronze, m):
    """Keeping the LAST arrival poisons the watermark and breaks re-runs."""
    out = deduplicate(bronze, m)
    expected = bronze.groupby("event_id")["ingested_at"].min()
    got = out.set_index("event_id")["ingested_at"]
    assert (got.sort_index() == expected.sort_index()).all()


def test_dedup_counts_what_it_removed(bronze, m):
    out = deduplicate(bronze, m)
    assert m.duplicates_removed == len(bronze) - len(out)
    assert m.duplicates_removed > 0


# ── 3 · schema drift ──────────────────────────────────────────────────────────
def test_drift_creates_sku(bronze, m):
    out = resolve_drift(bronze, m)
    assert "sku" in out.columns


def test_drift_recovers_the_orphaned_rows(bronze, m):
    """Rows that only had item_id must end up with a populated sku."""
    out = resolve_drift(bronze, m)
    orphans = out[out["product_id"].isna() & out["item_id"].notna()]
    assert len(orphans) > 0, "no drift found — did Module 01 run with pathology 7?"
    assert orphans["sku"].notna().all()
    assert m.drifted_rows_recovered == len(orphans)


def test_drift_shouts_about_it(bronze, m):
    """A silent coalesce is worse than the bug. Somebody has to be told."""
    resolve_drift(bronze, m)
    assert any("item_id" in n or "SCHEMA" in n.upper() for n in m.notes), (
        "you healed the column but told nobody — the producer will do it again")


def test_drift_preserves_lineage(bronze, m):
    """Keep the originals. You will need to prove what happened."""
    out = resolve_drift(bronze, m)
    assert "product_id" in out.columns and "item_id" in out.columns


# ── 4 · bots ──────────────────────────────────────────────────────────────────
def test_bot_flag_is_constant_within_a_session(bronze, m):
    out = classify_bots(bronze, m)
    per = out.groupby("session_id")["is_suspected_bot"].nunique()
    assert (per == 1).all(), "a session is a bot or it isn't — don't flag half of it"


def test_bot_filter_beats_a_coin_flip_by_a_lot(bronze, m):
    """The bar is 'genuinely useful', not 'perfect'. Perfect is not available."""
    out = classify_bots(bronze, m)
    s = score_bot_filter(out)
    assert s["recall"] > 0.70, f"recall {s['recall']:.1%} — you're missing real bots"
    assert s["precision"] > 0.70, f"precision {s['precision']:.1%} — you're eating customers"


def test_bot_filter_is_not_perfect(bronze, m):
    """Yes, this test asserts that you FAILED a little. On purpose.

    A behavioral filter scoring 100% on data with a deliberately overlapping
    `checker` persona means you found a shortcut — almost always a ground-truth
    column, or a rule so tight it only works on this seed. Both are worse than
    a good 90%.
    """
    out = classify_bots(bronze, m)
    s = score_bot_filter(out)
    assert s["fp"] + s["fn"] > 0, (
        "100% on overlapping personas means you cheated or overfit the seed")


def test_bot_filter_spares_paying_sessions(bronze, m):
    """A bot that gives you money is a customer. Never delete revenue."""
    out = classify_bots(bronze, m)
    bought = out[out["event_name"] == "purchase"]["session_id"].unique()
    flagged = out[out["is_suspected_bot"]]["session_id"].unique()
    assert not set(bought) & set(flagged)


# ── 5 · sessionize ────────────────────────────────────────────────────────────
def test_sessionize_adds_a_derived_id(bronze, m):
    out = sessionize(bronze, m)
    assert "derived_session_id" in out.columns
    assert out["derived_session_id"].notna().all()


def test_sessionize_splits_on_the_timeout(bronze, m):
    """No derived session may contain a gap longer than the timeout."""
    out = sessionize(bronze, m)
    o = out.sort_values(["derived_session_id", "event_ts"])
    gaps = o.groupby("derived_session_id")["event_ts"].diff().dropna()
    assert gaps.max() <= pd.Timedelta(minutes=S.SESSION_TIMEOUT_MINUTES)


def test_sessionize_never_merges_two_visitors(bronze, m):
    out = sessionize(bronze, m)
    per = out.groupby("derived_session_id")["visitor_id"].nunique()
    assert (per == 1).all()


def test_sessionize_disagrees_with_the_client(bronze, m):
    """If your derived count exactly matches the client's, you rebuilt the
    client's opinion instead of forming your own. That's the whole point of
    doing it server-side.
    """
    out = sessionize(bronze, m)
    assert m.sessions_derived != bronze["session_id"].nunique()


def test_sessionize_respects_a_custom_timeout(bronze, m):
    """Thirty minutes is a parameter, not a law. Prove yours is one too."""
    a = sessionize(bronze, S.Manifest(), timeout_minutes=5)
    b = sessionize(bronze, S.Manifest(), timeout_minutes=120)
    assert a["derived_session_id"].nunique() > b["derived_session_id"].nunique()


# ── the guard ─────────────────────────────────────────────────────────────────
def test_no_ground_truth_leakage():
    """Read your source. Fail if the pipeline peeks at the answer key."""
    for fn in (S.quarantine_impossible_timestamps, S.deduplicate,
               S.resolve_schema_drift, S.classify_bots, S.sessionize):
        S.assert_no_truth_leakage(inspect.getsource(fn))

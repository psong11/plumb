"""
Your grader.

    pytest module_01_synthetic_pulse -q                 # grade YOUR code
    PLUMB_ANSWERS=1 pytest module_01_synthetic_pulse -q # sanity-check the keys

These tests exist so you never have to ask me "is this right?" — you can find
out in 400ms. That matters more than it sounds. The thing that kills a
build-to-learn project is a stall, and "I think this is done but I'm not sure"
is a stall. Run the tests, get a red or a green, keep moving.

Each test says WHY it exists, not just what it asserts. If a test fails, read
its docstring first — it usually tells you exactly which trap you hit.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from meridian.world import DEVICES
from module_01_synthetic_pulse.generator import generate_clean_events
from module_01_synthetic_pulse import pathologies as P

USE_KEY = os.environ.get("PLUMB_ANSWERS") == "1"

buffer_offline_events = P._answer_buffer_offline_events if USE_KEY else P.buffer_offline_events
drop_beacons          = P._answer_drop_beacons          if USE_KEY else P.drop_beacons
drift_schema          = P._answer_drift_schema          if USE_KEY else P.drift_schema


@pytest.fixture
def staged():
    """Clean events, run through pathologies 1-4 only. Your input."""
    chaos = P.Chaos()
    ev = [dict(e) for e in generate_clean_events(n_sessions=1200, days=7, seed=7)]
    ev = P.apply_clock_skew(ev, chaos)
    ev = P.spoof_bot_identity(ev, chaos)
    ev = P.stamp_ingestion_time(ev, chaos)
    return ev, chaos


# ══════════════════════════════════════════════════════════════════════════════
#  5 · buffer_offline_events
# ══════════════════════════════════════════════════════════════════════════════
def test_buffer_preserves_every_event(staged):
    """Buffering DELAYS events, it never deletes them. That's pathology 6's job.

    If this fails you probably filtered instead of mutating. The phone kept the
    events — that's the entire point of a native app versus a web page.
    """
    ev, chaos = staged
    n_before = len(ev)
    out = buffer_offline_events(ev, chaos)
    assert len(out) == n_before


def test_buffer_never_touches_event_ts(staged):
    """THE trap. Late arrival changes when you RECEIVED it, not when it HAPPENED.

    If this fails, reread the tunnel story at the top of pathology 5. A user who
    browsed on Tuesday browsed on Tuesday. Friday is when you found out.
    """
    ev, chaos = staged
    before = {id(e): e["event_ts"] for e in ev}
    out = buffer_offline_events(ev, chaos)
    for e in out:
        assert e["event_ts"] == before[id(e)]


def test_buffer_only_affects_devices_that_can_buffer(staged):
    """Web can't hold events on disk across a network drop. Only `app` can.

    If mobile_web sessions show up buffered, you rolled per-event or forgot the
    DEVICES[...]["can_buffer_offline"] gate.
    """
    ev, chaos = staged
    out = buffer_offline_events(ev, chaos)
    for e in out:
        if e.get("_was_buffered"):
            assert DEVICES[e["device"]]["can_buffer_offline"], (
                f"{e['device']} cannot buffer offline — only native apps can")


def test_buffer_flushes_a_session_tail_together(staged):
    """One reconnection, one flush. Every buffered event in a session shares
    the same added delay — because they all rode the same reconnect.

    If this fails you drew a fresh random delay per event, which models 40
    separate reconnections in one session. Move the rng call outside the loop.
    """
    ev, chaos = staged
    out = buffer_offline_events(ev, chaos)
    by_session = defaultdict(list)
    for e in out:
        if e.get("_was_buffered"):
            by_session[e["session_id"]].append(e)

    assert by_session, "no sessions were buffered at all — check your rate/gating"
    for sid, evs in by_session.items():
        delays = {round((e["ingested_at"] - e["_true_ts"]).total_seconds() / 60)
                  for e in evs}
        spread = max(delays) - min(delays)
        assert spread < 30, (
            f"session {sid} flushed over {spread} min — one delay for the tail")


def test_buffer_produces_genuinely_late_data(staged):
    """We need multi-hour lateness or Module 02's watermark has nothing to catch."""
    ev, chaos = staged
    out = buffer_offline_events(ev, chaos)
    lags = [(e["ingested_at"] - e["_true_ts"]) for e in out if e.get("_was_buffered")]
    assert lags, "nothing was buffered"
    assert max(lags) > timedelta(hours=1)


# ══════════════════════════════════════════════════════════════════════════════
#  6 · drop_beacons
# ══════════════════════════════════════════════════════════════════════════════
def test_drop_actually_drops(staged):
    ev, chaos = staged
    out = drop_beacons(ev, chaos)
    assert len(out) < len(ev)
    assert len(out) > len(ev) * 0.9, "you deleted way too much — check your rates"


def test_drop_preserves_order(staged):
    """Dropping is a filter, not a shuffle. Downstream code assumes order."""
    ev, chaos = staged
    ids = [id(e) for e in ev]
    out = drop_beacons(ev, chaos)
    pos = {i: n for n, i in enumerate(ids)}
    seq = [pos[id(e)] for e in out]
    assert seq == sorted(seq)


def test_drop_hits_trailing_events_harder(staged):
    """The whole point. The last event of a session loses the race with unload.

    If this fails you applied one flat rate. Go find the last event per session
    and give it the higher rate INSTEAD of the base rate.
    """
    ev, chaos = staged
    by_session = defaultdict(list)
    for e in ev:
        by_session[e["session_id"]].append(e)
    trailing = {max(evs, key=lambda x: x["_true_ts"])["event_id"] for evs in by_session.values()}

    kept = {e["event_id"] for e in drop_beacons(ev, chaos)}
    trail_loss = 1 - len(trailing & kept) / len(trailing)
    other = {e["event_id"] for e in ev} - trailing
    other_loss = 1 - len(other & kept) / len(other)

    assert trail_loss > other_loss * 1.5, (
        f"trailing loss {trail_loss:.1%} vs other {other_loss:.1%} — "
        "trailing events should die noticeably more often")


def test_drop_writes_a_loss_ledger(staged):
    """You can't publish a loss rate you didn't count. Rule 04 starts here."""
    ev, chaos = staged
    out = drop_beacons(ev, chaos)
    assert P.LOSS_LEDGER, "LOSS_LEDGER is empty — count what you destroy"
    assert set(P.LOSS_LEDGER) >= {"dropped", "dropped_purchases", "kept"}
    assert P.LOSS_LEDGER["kept"] == len(out)
    assert P.LOSS_LEDGER["dropped"] + P.LOSS_LEDGER["kept"] == len(ev)


def test_drop_eats_real_purchases(staged):
    """If no purchases die, Module 02 has no revenue gap to reconcile.

    This is the uncomfortable one. Your most valuable event is your most
    fragile event. The test asserting that is on purpose.
    """
    ev, chaos = staged
    drop_beacons(ev, chaos)
    assert P.LOSS_LEDGER["dropped_purchases"] > 0


# ══════════════════════════════════════════════════════════════════════════════
#  7 · drift_schema
# ══════════════════════════════════════════════════════════════════════════════
def test_drift_gives_every_row_an_item_id_key(staged):
    """Consistent columns, or parquet will fight you and Module 02 will crash."""
    ev, chaos = staged
    out = drift_schema(ev, chaos)
    assert all("item_id" in e for e in out)


def test_drift_moves_the_id_rather_than_copying_it(staged):
    """A rename means the old field goes NULL. If both stay populated, the bug
    is invisible and you've modelled the wrong incident. Real renames hurt
    precisely because product_id becomes null and nobody notices.
    """
    ev, chaos = staged
    out = drift_schema(ev, chaos)
    drifted = [e for e in out if e.get("_drifted")]
    assert drifted, "nothing drifted — check your cutover fraction and gating"
    assert all(e["product_id"] is None for e in drifted)
    assert any(e["item_id"] is not None for e in drifted)


def test_drift_is_app_only_and_after_the_cutover(staged):
    ev, chaos = staged
    lo = min(e["_true_ts"] for e in ev)
    hi = max(e["_true_ts"] for e in ev)
    cut = lo + (hi - lo) * chaos.drift_at_fraction
    for e in drift_schema(ev, chaos):
        if e.get("_drifted"):
            assert e["device"] == "app"
            assert e["_true_ts"] >= cut
            assert e["app_version"] == "2.4.0"


def test_drift_adoption_is_sticky_per_visitor(staged):
    """A phone that updated stays updated. Roll once per visitor_id.

    If this fails you rolled per event, so the same device flickers between
    2.3.0 and 2.4.0 — which would make the incident trivially detectable and
    therefore useless as practice.
    """
    ev, chaos = staged
    out = drift_schema(ev, chaos)
    lo = min(e["_true_ts"] for e in ev)
    hi = max(e["_true_ts"] for e in ev)
    cut = lo + (hi - lo) * chaos.drift_at_fraction

    versions = defaultdict(set)
    for e in out:
        if e["device"] == "app" and e["_true_ts"] >= cut:
            versions[e["visitor_id"]].add(e["app_version"])
    flapping = [v for v, s in versions.items() if len(s) > 1]
    assert not flapping, f"{len(flapping)} visitors flip-flopped app versions"


# ══════════════════════════════════════════════════════════════════════════════
#  end to end
# ══════════════════════════════════════════════════════════════════════════════
def test_full_corruption_pipeline_runs():
    """All seven, in order, without exploding. Green here = Module 01 done."""
    clean = [dict(e) for e in generate_clean_events(n_sessions=600, days=5, seed=3)]
    out = P.corrupt(clean, P.Chaos(), use_answers=USE_KEY)
    assert out
    cols = set(out[0])
    assert {"event_id", "event_ts", "ingested_at", "item_id", "_true_ts"} <= cols

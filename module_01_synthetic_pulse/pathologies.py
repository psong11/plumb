"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 01 · THE PATHOLOGIES                                                 ║
║  Where we take that beautiful clean data and hurt it on purpose.             ║
╚══════════════════════════════════════════════════════════════════════════════╝

OK. Deep breath. This is the most important file in Module 01 and probably one
of the three most important in the whole repo, so let me tell you why before you
write anything.

You could learn data engineering by downloading a messy public dataset. Loads of
people do. Here's why that's worse: when you find something weird in a public
dataset, you don't know if it's a bug, a business rule, or you being dumb. You
can spend four hours on a null and never find out which one it was.

When YOU inject the mess, you know exactly what's in there. So in Module 02,
when your session count comes out 3% high, you don't guess — you go
"that's my duplicate injector, I set it to 1.5%, and 1.5% of events landing in
the wrong place produced 3% inflation, WHY IS IT DOUBLE?" and that question has
a real answer that will teach you something permanent about fan-out.

You are building the answer key to your own exam. That's the whole trick.

┌────────────────────────────────────────────────────────────────────────────┐
│  THE SEVEN PATHOLOGIES                                                     │
│                                                                            │
│  I wrote 1–4. You write 5–7. Read mine first — not to be polite, but        │
│  because 5 literally depends on the column that 2 creates.                  │
│                                                                            │
│   1. deliver_at_least_once   Kafka hands you the same event twice.          │
│   2. stamp_ingestion_time    The clock that isn't the event's clock.        │
│   3. apply_clock_skew        Devices lie about what time it is.             │
│   4. spoof_bot_identity      The scraper says it's a MacBook.               │
│  ─────────────────────────────────────────────────────────────────────     │
│   5. buffer_offline_events   ← YOU.  The parking-garage phone.              │
│   6. drop_beacons            ← YOU.  The events that never arrive.          │
│   7. drift_schema            ← YOU.  A bad app release renames a field.     │
└────────────────────────────────────────────────────────────────────────────┘

HOW THE "YOUR TURN" BLOCKS WORK
    Each one has a spec box, a stub that raises, and a folded ANSWER KEY below.

    ⌘K ⌘0   fold every region in this file  ← do this the second you open it
    ⌘K ⌘J   unfold everything (surrender)

    And you can run the FULL pipeline before you've written a thing:
        python -m module_01_synthetic_pulse.run --answers
    That uses my implementations so you can see where you're headed. Then drop
    the flag and make your own pass the tests. Momentum > purity.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from datetime import timedelta

from meridian.world import DEVICES


# ══════════════════════════════════════════════════════════════════════════════
#  THE CHAOS DIAL
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Chaos:
    """Every knob, in one place, with real-world defaults.

    These numbers aren't invented. They're the middle of the range you'd see on
    a large consumer retail site. I've put the reasoning next to each one,
    because "why is it 1.5% and not 15%?" is a question you should be able to
    answer in a meeting someday.

    Turn any of them to 0.0 to switch that pathology off — which is exactly how
    you debug Module 02. Something's wrong with your session counts? Zero out
    the duplicates, rerun, see if it goes away. Bisecting your own chaos is a
    legitimately elite debugging move and almost nobody thinks to do it.
    """
    # 1 · duplicates. Kafka retries on consumer rebalance / failed commit.
    #     Quiet days: <1%. During a deploy or a partition reassignment: 5%+.
    duplicate_rate: float = 0.015

    # 2 · ingestion lag. Even a healthy pipeline isn't instant.
    base_lag_seconds: tuple[float, float] = (0.4, 12.0)

    # 3 · clock skew. Share of DEVICES (not events) with a wrong clock.
    #     Most are seconds off. A few are absurd — dead battery reset to 1970,
    #     kid changed the date to get a free life in a game. Those exist. Really.
    skewed_device_rate: float = 0.06
    absurd_clock_rate: float = 0.004

    # 4 · bot spoofing. Share of bots that bother to lie about their device.
    #     Lazy scrapers don't. Commercial price-intelligence vendors always do.
    bot_spoof_rate: float = 0.75

    # 5 · offline buffering. Share of APP sessions that go offline mid-session.
    #     Elevators, subways, rural dead zones, airplane mode, phone died.
    offline_session_rate: float = 0.10
    offline_flush_hours: tuple[float, float] = (1.0, 80.0)   # up to ~3 days late

    # 6 · dropped beacons. Ad blockers, tab-close races, battery saver.
    #     `trailing` is higher because the LAST event of a session is the one
    #     most likely to lose the race with the page unloading. And the last
    #     event of a converting session is... the purchase. Yeah. Exactly.
    beacon_drop_rate: float = 0.018
    trailing_beacon_drop_rate: float = 0.055

    # 7 · schema drift. App release 2.4.0 renames product_id → item_id.
    #     Set to a fraction of the run's timespan: 0.6 == "shipped 60% of the
    #     way through the window." Nobody told the data team. They never do.
    drift_at_fraction: float = 0.62
    drift_adoption_rate: float = 0.55   # not everyone updates their app at once

    seed: int = 4242


# ══════════════════════════════════════════════════════════════════════════════
#  1 · DELIVER AT LEAST ONCE                                            (worked)
# ══════════════════════════════════════════════════════════════════════════════
def deliver_at_least_once(events: list[dict], chaos: Chaos) -> list[dict]:
    """Kafka's actual guarantee, honestly implemented.

    People say "Kafka is at-least-once" the way they say "the sky is blue" —
    true, agreed, moving on. Then they build a pipeline that assumes exactly-once
    and are baffled six months later when their numbers run hot.

    So: at-least-once means AT LEAST. The same event_id can hit your topic two,
    three, four times. A consumer reads a batch, processes it, dies before
    committing its offset; the next consumer picks up from the last commit and
    reprocesses everything after it. Nothing was "broken." That's the design.

    Two things I want you to notice in the code below:

    (a) The duplicate is a genuine COPY with the SAME event_id. That's what makes
        it fixable — event_id is your dedup key and it survives the retry. If the
        producer generated a fresh uuid on retry you would be completely sunk,
        which is why "generate the id at the source, once" is a producer-side
        requirement you should fight for. Rule 07. Producer side. Always.

    (b) The duplicate gets a LATER ingested_at but the SAME event_ts. That is
        not a detail — that is the entire shape of the problem. Two rows,
        identical event time, different arrival time. Every dedup strategy you
        will ever write is a policy about which of those two clocks wins.
    """
    rng = random.Random(chaos.seed + 1)
    out: list[dict] = []
    for e in events:
        out.append(e)
        while rng.random() < chaos.duplicate_rate:
            dupe = copy.deepcopy(e)
            dupe["_is_duplicate"] = True          # truth column. tests only.
            if "ingested_at" in dupe and dupe["ingested_at"] is not None:
                dupe["ingested_at"] += timedelta(seconds=rng.uniform(0.2, 240))
            out.append(dupe)
            # `while`, not `if` — triple deliveries are rarer but real, and a
            # dedup that only ever handles pairs is a dedup that fails on the
            # worst day of the year. Test with n>2. Always test with n>2.
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  2 · STAMP INGESTION TIME                                             (worked)
# ══════════════════════════════════════════════════════════════════════════════
def stamp_ingestion_time(events: list[dict], chaos: Chaos) -> list[dict]:
    """Add `ingested_at` — the second clock, and the one you can trust.

    Right now every event has ONE timestamp: `event_ts`, which the user's own
    device wrote. Wallpaper rule 06. This function adds the other one.

        event_ts     when it happened      (client says so; client may be lying)
        ingested_at  when WE received it   (our server; boring; reliable)

    You need both, forever, on every event, and the discipline to know which one
    each metric uses. Here's the rule that took the industry a decade to agree on:

        Report on EVENT time.  Operate on INGESTION time.

    "How many sessions did we have Tuesday?" → event time. Obviously. The user's
    Tuesday is the Tuesday that happened.

    "Which files do I need to reprocess in tonight's batch?" → ingestion time.
    Because you cannot query for data you haven't received yet, and a pipeline
    that partitions by event time has to go rewrite old partitions every single
    run when late data shows up.

    Getting this backwards is THE classic clickstream bug. It doesn't crash. It
    doesn't error. It just makes yesterday's number quietly different tomorrow,
    and by the time someone notices, it's in a board deck.
    """
    rng = random.Random(chaos.seed + 2)
    lo, hi = chaos.base_lag_seconds
    for e in events:
        # Lag is lognormal-ish, not uniform: usually fast, occasionally awful.
        # Real latency distributions have a long right tail and if you model
        # them as uniform your p99 alerting will be a fantasy.
        lag = min(hi, lo * (1.0 / max(rng.random(), 0.02)) ** 0.55)
        e["ingested_at"] = e["_true_ts"] + timedelta(seconds=lag)
    return events
    # NOTE: we lag off `_true_ts`, not `event_ts`. `_true_ts` is what actually
    # happened; `event_ts` is what the device *claimed*. Pathology 3 is about to
    # make those diverge, and if ingestion lag were computed off a lying clock
    # you'd get events that arrived before they occurred. Which does happen in
    # production, and is horrible, and is a bug — not a thing to reproduce here.


# ══════════════════════════════════════════════════════════════════════════════
#  3 · APPLY CLOCK SKEW                                                 (worked)
# ══════════════════════════════════════════════════════════════════════════════
def apply_clock_skew(events: list[dict], chaos: Chaos) -> list[dict]:
    """Some devices think it's a different time than it is. Some by a LOT.

    First: we snapshot the honest timestamp into `_true_ts` before touching
    anything, because we're going to need ground truth to grade ourselves later.

    Skew is per-DEVICE, not per-event, and that detail matters. A phone whose
    clock is 90 seconds fast is 90 seconds fast for every event it ever sends.
    That means skew doesn't average out into noise — it shows up as a coherent
    block of events landing in the wrong minute, hour, or in the funniest cases,
    the wrong decade. If you model it per-event you'll build a filter that works
    on your fake data and does nothing in production.

    The absurd bucket is real. Dead battery → clock resets to epoch. Kids change
    the date to farm daily rewards in games. Some Android builds report UTC as
    local. You WILL have events dated 1970 and 2038 in your warehouse, and if
    your bronze→silver job does `min(event_ts)` anywhere without a sanity bound,
    one of them will eat your partition pruning and your query will scan
    everything you own.
    """
    rng = random.Random(chaos.seed + 3)
    skew_by_visitor: dict[str, timedelta] = {}

    for e in events:
        e["_true_ts"] = e["event_ts"]              # ground truth, stashed first

        vid = e["visitor_id"]
        if vid not in skew_by_visitor:
            r = rng.random()
            if r < chaos.absurd_clock_rate:
                skew_by_visitor[vid] = timedelta(days=rng.choice([-20455, -3650, 4380]))
            elif r < chaos.skewed_device_rate:
                skew_by_visitor[vid] = timedelta(seconds=rng.gauss(0, 240))
            else:
                skew_by_visitor[vid] = timedelta(0)

        e["event_ts"] = e["_true_ts"] + skew_by_visitor[vid]
    return events


# ══════════════════════════════════════════════════════════════════════════════
#  4 · SPOOF BOT IDENTITY                                               (worked)
# ══════════════════════════════════════════════════════════════════════════════
def spoof_bot_identity(events: list[dict], chaos: Chaos) -> list[dict]:
    """Make the bots stop announcing themselves.

    Right now your bot sessions are trivially findable: persona == "bot". In
    production, obviously, nobody labels their scraper for you. Commercial
    price-intelligence bots deliberately blend in — plausible user agent,
    residential proxy IPs, sometimes even randomized delays.

    So we strip the tell. After this runs, a bot session is a `desktop` session
    that happens to view 40 products in 90 seconds and never carts anything.

    And now here's the thing I actually want you to take away:

        You will never remove all the bots. Set that goal down.

    Bot filtering is a precision/recall tradeoff with money on both sides.
    Filter too hard and you delete real high-intent power users — the
    "restocker" persona looks a LOT like a bot on paper. Filter too soft and
    your pageviews are inflated and your conversion rate is deflated, because
    bots swell the denominator and never touch the numerator.

    That last sentence is worth reading twice. **Bots make you look worse than
    you are, on exactly the metric executives stare at.** Which is why the honest
    move isn't a perfect filter — it's publishing your bot share as a number
    right next to the metric. Wallpaper rules 04 and 05, in the wild.
    """
    rng = random.Random(chaos.seed + 4)
    spoofed_sessions = {}

    for e in events:
        if not e.get("_is_bot"):
            continue
        sid = e["session_id"]
        if sid not in spoofed_sessions:
            spoofed_sessions[sid] = rng.random() < chaos.bot_spoof_rate
        if spoofed_sessions[sid]:
            e["device"] = rng.choices(["desktop", "mobile_web"], weights=[0.8, 0.2])[0]
            e["membership_tier"] = "guest"
            e["_bot_spoofed"] = True
    return events


# ══════════════════════════════════════════════════════════════════════════════
#
#   ██   ██  ██████  ██    ██ ██████       ████████ ██    ██ ██████  ███    ██
#    ██ ██  ██    ██ ██    ██ ██   ██         ██    ██    ██ ██   ██ ████   ██
#     ███   ██    ██ ██    ██ ██████          ██    ██    ██ ██████  ██ ██  ██
#    ██ ██  ██    ██ ██    ██ ██   ██         ██    ██    ██ ██   ██ ██  ██ ██
#   ██   ██  ██████   ██████  ██   ██         ██     ██████  ██   ██ ██   ████
#
#  Three functions. They are the three that matter. Here's the pitch for each,
#  and then I'm going to get out of your way.
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  5 · BUFFER OFFLINE EVENTS                                          ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  Remember when I told you dedup was the whole game? I lied. Well — I let you
#  believe it, which is worse.
#
#  Here's what dedup can't touch. Somebody opens the Meridian app on the train.
#  Browses six products. Train goes into the tunnel. The app is a NATIVE app, so
#  unlike a website it doesn't just lose those events — it's smart, it writes
#  them to local storage and holds them. Phone comes out of the tunnel eight
#  hours later, or Friday, or never.
#
#  When those events finally arrive, they carry TUESDAY'S event_ts.
#
#  So on Wednesday morning you run your daily job, you report Tuesday = 41,200
#  sessions, somebody puts it in a deck. On Friday the tunnel events land. Now
#  Tuesday is 41,900 sessions. The number CHANGED. Nothing broke. No error, no
#  alert, no failed job. Tuesday is just different now, forever, and the deck is
#  wrong and nobody knows.
#
#  THAT is why event time ≠ processing time is a wallpaper rule and not a
#  footnote. Every mature streaming system — Flink, Beam, Spark Structured
#  Streaming — has an entire concept called a WATERMARK that exists solely to
#  answer "how long do I wait for stragglers before I'm allowed to call a day
#  done?" You'll build one in Module 02. Tonight you build the straggler.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   buffer_offline_events(events, chaos) -> list[dict]
# │
# │ IN      events   list of dicts, each already having `ingested_at`
# │                  (so this MUST run after stamp_ingestion_time)
# │         chaos    .offline_session_rate, .offline_flush_hours, .seed
# │
# │ DO      1. Find candidate sessions: only devices where
# │            DEVICES[device]["can_buffer_offline"] is True. Web can't buffer.
# │            It just dies. Only `app` qualifies.
# │         2. Roll per SESSION (not per event) at chaos.offline_session_rate.
# │         3. For a chosen session, pick a random cut point somewhere in the
# │            MIDDLE of its events (not the first — they got online fine).
# │         4. Every event from the cut onward: push `ingested_at` forward by a
# │            random delay in chaos.offline_flush_hours. LEAVE `event_ts` ALONE.
# │         5. Mark them `_was_buffered = True` (ground truth for your tests).
# │
# │ OUT     the same list, same length, same order. You are moving one column.
# │
# │ TRAP 1  The whole tail flushes TOGETHER when the phone reconnects. Same
# │         delay for all of them, not a fresh random per event. Get this wrong
# │         and you've modelled 40 separate reconnections, which is nonsense.
# │ TRAP 2  Do not touch event_ts. If you find yourself editing event_ts you
# │         have misunderstood the pathology — reread the tunnel story.
# │ TRAP 3  Group events by session_id first. Iterating the flat sorted list and
# │         deciding per-row cannot produce a coherent "session went dark."
# │
# │ HINT    collections.defaultdict(list) to group; the events are already in
# │         timestamp order within a session, so index math works fine.
# ╰──────────────────────────────────────────────────────────────────────────────
def buffer_offline_events(events: list[dict], chaos: Chaos) -> list[dict]:
    raise NotImplementedError("the phone is in the tunnel. go get it.")


# region 🔒 ANSWER KEY 05 — fold me (⌘K ⌘0)
def _answer_buffer_offline_events(events: list[dict], chaos: Chaos) -> list[dict]:
    from collections import defaultdict
    rng = random.Random(chaos.seed + 5)

    by_session: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_session[e["session_id"]].append(e)

    for sid, evs in by_session.items():
        if not DEVICES.get(evs[0]["device"], {}).get("can_buffer_offline"):
            continue
        if len(evs) < 3 or rng.random() >= chaos.offline_session_rate:
            continue
        cut = rng.randrange(1, len(evs))
        delay = timedelta(hours=rng.uniform(*chaos.offline_flush_hours))
        for e in evs[cut:]:                      # one delay, applied to the tail
            e["ingested_at"] += delay
            e["_was_buffered"] = True
    return events
# endregion


# ══════════════════════════════════════════════════════════════════════════════
#  6 · DROP BEACONS                                                   ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  Pathology 5 was events arriving LATE. This one is events that never arrive.
#
#  A "beacon" is the little HTTP request the page fires to say something
#  happened. It dies for boring reasons: an ad blocker matched the URL, the
#  user closed the tab before it flushed, battery saver killed background
#  requests, the network was garbage, Safari's ITP got opinionated.
#
#  Nobody logs a beacon that didn't fire. There is no error. The event simply
#  does not exist, and no amount of downstream engineering will conjure it back.
#
#  AND NOW THE PART THAT SHOULD GENUINELY BOTHER YOU.
#
#  The drop rate is not uniform. The LAST event of a session dies far more often
#  than the middle ones, because it's racing the page unload. And what is the
#  last event of a session that converted?
#
#  The purchase.
#
#  Your most valuable event. The only one attached to money. It is the single
#  most likely event in your entire warehouse to silently not exist.
#
#  This is exactly why wallpaper rule 04 says stop chasing lossless. You cannot
#  win this. What you CAN do — and what separates a real data org from a
#  hopeful one — is reconcile against a system of record. The order service
#  knows about every order. Your clickstream doesn't. The DIFFERENCE between
#  those two numbers is your beacon loss rate, and once you can measure it you
#  can publish it, and once you can publish it your agent can carry it into the
#  answer. Rule 05. It all connects.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   drop_beacons(events, chaos) -> list[dict]
# │
# │ DO      Return a NEW list with some events removed.
# │           · every event: drop with prob chaos.beacon_drop_rate
# │           · the LAST event of each session: instead use
# │             chaos.trailing_beacon_drop_rate (higher). Not both. The trailing
# │             rate REPLACES the base rate for that one event.
# │
# │ OUT     a shorter list, original relative order preserved.
# │
# │ ALSO    Return-by-side-channel: set the module-level dict LOSS_LEDGER to
# │           {"dropped": n, "dropped_purchases": p, "kept": k}
# │         Yes, a global is ugly. Do it anyway, and then ask yourself why it
# │         feels bad. (Answer in Module 02: this wants to be a first-class
# │         data-quality manifest, not a side effect. You'll build that properly.
# │         Feeling the ugliness now is the point.)
# │
# │ TRAP 1  "Last event of each session" — after dedup, a session's events may
# │         not be contiguous in the list. Group by session_id, find the max
# │         event_ts within it, and identify that event_id.
# │ TRAP 2  Do NOT drop by index while iterating the list you're iterating.
# │         Build a set of event_ids to kill, then filter. You know this. I'm
# │         saying it anyway because everyone does it once at 1am.
# │ TRAP 3  Duplicates share an event_id. If you kill by event_id you kill all
# │         copies at once — which is arguably WRONG (the retry might succeed
# │         even if the first send failed). Pick a behavior, then write a comment
# │         saying which you picked and why. That comment is the deliverable.
# ╰──────────────────────────────────────────────────────────────────────────────
LOSS_LEDGER: dict = {}


def drop_beacons(events: list[dict], chaos: Chaos) -> list[dict]:
    raise NotImplementedError("some of these were never going to make it.")


# region 🔒 ANSWER KEY 06 — fold me (⌘K ⌘0)
def _answer_drop_beacons(events: list[dict], chaos: Chaos) -> list[dict]:
    from collections import defaultdict
    rng = random.Random(chaos.seed + 6)

    last_in_session: dict[str, tuple] = {}
    for i, e in enumerate(events):
        sid = e["session_id"]
        key = (e["_true_ts"], i)
        if sid not in last_in_session or key > last_in_session[sid][0]:
            last_in_session[sid] = (key, i)
    trailing_idx = {idx for _, idx in last_in_session.values()}

    kept, dropped, dropped_purchases = [], 0, 0
    for i, e in enumerate(events):
        # DECISION: we roll per ROW, not per event_id. A retry is a separate
        # network attempt, so one copy dying while another lands is the honest
        # model — and it means dedup still has something to dedup.
        rate = chaos.trailing_beacon_drop_rate if i in trailing_idx else chaos.beacon_drop_rate
        if rng.random() < rate:
            dropped += 1
            if e["event_name"] == "purchase":
                dropped_purchases += 1
            continue
        kept.append(e)

    LOSS_LEDGER.clear()
    LOSS_LEDGER.update({"dropped": dropped, "dropped_purchases": dropped_purchases,
                        "kept": len(kept)})
    return kept
# endregion


# ══════════════════════════════════════════════════════════════════════════════
#  7 · DRIFT SCHEMA                                                   ← YOUR TURN
# ══════════════════════════════════════════════════════════════════════════════
#
#  Last one, and it's the one that'll actually show up in your real job.
#
#  A mobile engineer ships app 2.4.0. In it, someone tidied up an event payload
#  and renamed `product_id` to `item_id`, because `item_id` matched the naming
#  in their own module and it looked cleaner in the PR. Reasonable person.
#  Reasonable change. Passed code review. Nobody on that PR has ever heard of
#  your gold tables.
#
#  Users update over about two weeks, so you don't get a clean cutover — you get
#  a slow bleed where an increasing share of your events have a null where
#  product_id used to be. Your "product views by SKU" dashboard doesn't break.
#  It just drifts downward. Slowly. Like a business trend.
#
#  Somebody will spend a week analyzing that "trend."
#
#  THIS is wallpaper rule 07 and it is the highest-leverage unglamorous thing in
#  all of data engineering: a schema registry with backward-compatibility checks
#  wired into the PRODUCER's CI. Make the rename fail THEIR build, in the PR, in
#  four seconds, with a message saying "product_id is consumed by 34 downstream
#  tables." Then this whole class of incident stops existing forever.
#
#  You cannot fix this downstream. You can only detect it — and you'll write
#  that detector in Module 02, which is genuinely one of the more satisfying
#  things in this repo.
#
# ╭─ SPEC ───────────────────────────────────────────────────────────────────────
# │ WRITE   drift_schema(events, chaos) -> list[dict]
# │
# │ DO      1. Find the run's time window from `_true_ts` (min → max).
# │         2. drift_ts = min + (max - min) * chaos.drift_at_fraction
# │         3. For events at/after drift_ts, on `app` devices only:
# │            with prob chaos.drift_adoption_rate, this event came from an
# │            UPDATED app, so:
# │              · set  e["item_id"] = e["product_id"]
# │              · set  e["product_id"] = None
# │              · set  e["app_version"] = "2.4.0"
# │              · set  e["schema_version"] = "2.4.0"
# │              · mark e["_drifted"] = True
# │         4. Every OTHER event must still have an `item_id` key set to None,
# │            so the final dataset has a consistent set of columns.
# │
# │ TRAP 1  Adoption is per VISITOR, not per event. A phone that updated stays
# │         updated. Roll once per visitor_id and remember the answer — same
# │         shape as the clock-skew code in pathology 3, go crib from it.
# │ TRAP 2  Use `_true_ts` for the cutover, not `event_ts`. A device with a
# │         broken clock did not time-travel to a different app version.
# │ TRAP 3  Events with product_id=None already (home page, search) are fine —
# │         they just carry None in both columns. Don't special-case them.
# ╰──────────────────────────────────────────────────────────────────────────────
def drift_schema(events: list[dict], chaos: Chaos) -> list[dict]:
    raise NotImplementedError("someone shipped 2.4.0 and did not tell you.")


# region 🔒 ANSWER KEY 07 — fold me (⌘K ⌘0)
def _answer_drift_schema(events: list[dict], chaos: Chaos) -> list[dict]:
    rng = random.Random(chaos.seed + 7)
    if not events:
        return events

    lo = min(e["_true_ts"] for e in events)
    hi = max(e["_true_ts"] for e in events)
    drift_ts = lo + (hi - lo) * chaos.drift_at_fraction

    updated: dict[str, bool] = {}
    for e in events:
        e.setdefault("item_id", None)
        if e["device"] != "app" or e["_true_ts"] < drift_ts:
            continue
        vid = e["visitor_id"]
        if vid not in updated:
            updated[vid] = rng.random() < chaos.drift_adoption_rate
        if updated[vid]:
            e["item_id"] = e["product_id"]
            e["product_id"] = None
            e["app_version"] = "2.4.0"
            e["schema_version"] = "2.4.0"
            e["_drifted"] = True
    return events
# endregion


# ══════════════════════════════════════════════════════════════════════════════
#  THE ORCHESTRATOR — order is not negotiable
# ══════════════════════════════════════════════════════════════════════════════
def corrupt(events: list[dict], chaos: Chaos | None = None, use_answers: bool = False) -> list[dict]:
    """Run the seven pathologies in the only order that makes physical sense.

    Trace one event through this pipeline in your head before you run it:

      skew        the device writes a (possibly wrong) event_ts
      drift       the app version determines which field name it uses
      spoof       the bot decides what to claim it is
      ────────────── the event leaves the device ──────────────
      stamp       our servers record when it landed
      buffer      ...unless the phone was in a tunnel, in which case, later
      duplicate   Kafka hands it to us more than once
      drop        or the beacon never fired and none of this happened

    Everything above the line is the CLIENT lying. Everything below is the
    NETWORK losing. Those are the two enemies, and every real clickstream bug
    you ever debug will be one of them wearing a hat.
    """
    chaos = chaos or Chaos()
    _buffer = _answer_buffer_offline_events if use_answers else buffer_offline_events
    _drop   = _answer_drop_beacons          if use_answers else drop_beacons
    _drift  = _answer_drift_schema          if use_answers else drift_schema

    events = apply_clock_skew(events, chaos)
    events = _drift(events, chaos)
    events = spoof_bot_identity(events, chaos)
    events = stamp_ingestion_time(events, chaos)
    events = _buffer(events, chaos)
    events = deliver_at_least_once(events, chaos)
    events = _drop(events, chaos)
    return events

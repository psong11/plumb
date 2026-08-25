"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 01 · THE ENGINE                                                      ║
║  Clean traffic. Perfect traffic. Traffic that has never known suffering.     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Read this file top to bottom before you write a line of your own code. You don't
have to write any of it — I wrote it so you can spend your night on the part
that actually teaches you something. But you DO have to understand it, because
in `pathologies.py` you're going to take this beautiful clean stream and
absolutely ruin it, and you can't ruin something you don't understand.

WHAT THIS FILE MAKES:
    A list of events. That's it. Each event is one dict, one thing a person did.
    A `page_view`. A `search`. An `add_to_cart`. Real clickstream is exactly this
    and nothing more — it just arrives a billion times a day and lies to you.

THE ONE IDEA YOU NEED:
    Events are generated per SESSION, and sessions are generated per PERSONA.
    A "bouncer" session and a "researcher" session come out of the same function
    but look nothing alike. That mixture is what makes the data feel real, and
    it's why almost every real analytics question turns out to be "which
    persona's share moved?" wearing a business costume.

WHAT THIS FILE DOES *NOT* DO:
    Nothing here is broken. No duplicates, no late arrivals, no bots lying about
    their user agent, no dropped beacons. Every event is perfect and arrives
    instantly in order.

    Which means this file is a fantasy. It has never once resembled production.
    It's the "before" photo.

    ...and honestly? If we stopped here you'd learn nothing. The interesting
    part of this entire repo is what we do to this data in the NEXT file.
    Get through this one. Then go break things.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone

from meridian.world import (
    CATALOG, CATEGORIES, PERSONAS, MEMBERSHIP_TIERS, DEVICES,
    HOURLY_SHAPE, WEEKDAY_SHAPE, EVENT_SCHEMA_VERSION,
)

# Search terms people actually type. Note the typos and the vague ones — those
# are not a joke, they're ~30% of real site search and they wreck naive
# "search term → category" mappings.
SEARCH_TERMS = [
    "paper towels", "papertowls", "toilet paper", "tp", "olive oil", "rice",
    "coffee", "ribeye", "tv", "65 inch tv", "vacuum", "robot vac", "grill",
    "propane", "vitamins", "allergy", "reading glasses", "strawberries",
    "chicken", "bulk", "deals", "what time does my club close", "returns",
    "cheap", "sale", "asdfgh", "gift card balance",
]


# ══════════════════════════════════════════════════════════════════════════════
#  A tiny bit of structure
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Visitor:
    """A device, not a person.

    THIS DISTINCTION WILL HAUNT YOU. `visitor_id` is a cookie or a device id. It
    is NOT a human. One human = phone + laptop + tablet = three visitor_ids. Two
    humans sharing an iPad = one visitor_id.

    Every "unique visitors" number you have ever seen in your life is really
    "unique devices we managed to cookie," and the gap between those two things
    is called the identity graph. It is the single biggest determinant of whether
    your top-line number means anything. We model just enough of it here to make
    the problem visible in Module 02.
    """
    visitor_id: str
    device: str
    membership_tier: str
    member_id: str | None = None      # None until they log in. Most never do.
    app_version: str = "2.3.0"


@dataclass
class Session:
    session_id: str
    visitor: Visitor
    persona: str
    started_at: datetime
    events: list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
#  Weighted choice, because random.choices' API is annoying to read inline
# ══════════════════════════════════════════════════════════════════════════════
def _pick(rng: random.Random, weighted: dict, key: str = "share") -> str:
    names = list(weighted)
    weights = [weighted[n][key] if isinstance(weighted[n], dict) else weighted[n] for n in names]
    return rng.choices(names, weights=weights, k=1)[0]


# ══════════════════════════════════════════════════════════════════════════════
#  When did this session start?
# ══════════════════════════════════════════════════════════════════════════════
def _sample_timestamp(rng: random.Random, day: datetime) -> datetime:
    """Pick a start time inside `day`, shaped like real retail traffic.

    Why not just `random.uniform(0, 86400)`? Because a flat traffic curve makes
    every downstream chart a straight line, and straight lines hide bugs. When
    your hourly sessions chart has a real evening peak, a timezone mistake looks
    like the peak moved to 3am — instantly, visually obvious.

    Make your fake data have SHAPE. Shape is what makes errors look like errors.
    """
    hour = rng.choices(range(24), weights=HOURLY_SHAPE, k=1)[0]
    return day.replace(
        hour=hour,
        minute=rng.randrange(60),
        second=rng.randrange(60),
        microsecond=rng.randrange(1_000_000),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  One event
# ══════════════════════════════════════════════════════════════════════════════
def _event(
    session: Session,
    ts: datetime,
    event_name: str,
    page_type: str,
    *,
    product_id: str | None = None,
    search_term: str | None = None,
    category: str | None = None,
    order_id: str | None = None,
    order_total: float | None = None,
) -> dict:
    """Build one event dict — the atom of this entire repo.

    Look hard at these field names, because in `pathologies.py` you are going to
    rename one of them mid-stream to simulate a bad app release, and every table
    built downstream will silently start emitting nulls. That's rule 07 on your
    wallpaper, and you're about to feel it in your hands.

    `event_ts` is CLIENT time. The device's own clock said this. Devices lie:
    they're in the wrong timezone, their clock is 40 seconds fast, the user set
    the date to 2031 to cheat at a mobile game. There is no `ingested_at` here
    yet — that gets stamped by the delivery layer, which is a separate concern
    and, not coincidentally, a separate file.
    """
    return {
        "event_id":        str(uuid.uuid4()),
        "session_id":      session.session_id,
        "visitor_id":      session.visitor.visitor_id,
        "member_id":       session.visitor.member_id,
        "event_ts":        ts,
        "event_name":      event_name,
        "page_type":       page_type,
        "product_id":      product_id,
        "category":        category,
        "search_term":     search_term,
        "device":          session.visitor.device,
        "membership_tier": session.visitor.membership_tier,
        "app_version":     session.visitor.app_version,
        "order_id":        order_id,
        "order_total":     order_total,
        "schema_version":  EVENT_SCHEMA_VERSION,
        "_persona":        session.persona,   # ← GROUND TRUTH. See note below.
        "_is_bot":         session.persona == "bot",
    }
    # ─────────────────────────────────────────────────────────────────────────
    # ABOUT THOSE UNDERSCORE FIELDS.
    #
    # `_persona` and `_is_bot` are the answer key. In production you do NOT get
    # these — nobody tags their own bots for you, that's the whole problem. But
    # because WE generated this data, we know the truth, and that means we can
    # score our own bot filter later and get an actual number for how good it is.
    #
    # This is the single most underrated trick in synthetic data: generate the
    # label alongside the data. It converts "our bot filter seems fine" into
    # "our bot filter has 87% recall," and those are different universes.
    #
    # Rule: any column starting with `_` is truth you're not allowed to use in
    # your pipeline logic. Only in tests. Module 02 enforces this.
    # ─────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
#  One session's worth of behavior
# ══════════════════════════════════════════════════════════════════════════════
def generate_session(rng: random.Random, visitor: Visitor, start: datetime) -> Session:
    """Walk one visitor through the site and emit what they did.

    The shape below is a crude funnel: land → (search|category) → product → cart
    → checkout → confirmation. Real sites are messier, but the funnel is the
    thing that makes conversion rate MEAN something, so we keep it.
    """
    persona_name = _pick(rng, {k: {"share": v["weight"]} for k, v in PERSONAS.items()})
    p = PERSONAS[persona_name]
    session = Session(str(uuid.uuid4()), visitor, persona_name, start)

    ts = start
    depth = rng.randint(*p["depth"])

    # Everybody lands somewhere.
    landing = rng.choices(["home", "search", "category", "product"],
                          weights=[0.30, 0.24, 0.18, 0.28], k=1)[0]

    def step():
        """Advance the clock by this persona's dwell time.

        Bots dwell 0.05–0.9s. Humans dwell 4–120s. That gap is your single best
        bot signal and it costs you nothing — no ML, no vendor, just a median.
        Remember this in Module 02 when you're tempted to buy something.
        """
        nonlocal ts
        ts = ts + timedelta(seconds=rng.uniform(*p["dwell"]))

    # ── the landing event ──
    if landing == "search":
        term = rng.choice(SEARCH_TERMS)
        session.events.append(_event(session, ts, "search", "search", search_term=term))
    elif landing == "category":
        cat = rng.choice(CATEGORIES)
        session.events.append(_event(session, ts, "page_view", "category", category=cat))
    elif landing == "product":
        sku, _, cat, _, _ = rng.choice(CATALOG)
        session.events.append(_event(session, ts, "page_view", "product",
                                     product_id=sku, category=cat))
    else:
        session.events.append(_event(session, ts, "page_view", "home"))

    # ── the middle ──
    viewed_products: list[tuple] = []
    for _ in range(max(0, depth - 1)):
        step()
        roll = rng.random()
        if roll < 0.22:
            term = rng.choice(SEARCH_TERMS)
            session.events.append(_event(session, ts, "search", "search", search_term=term))
        elif roll < 0.42:
            cat = rng.choice(CATEGORIES)
            session.events.append(_event(session, ts, "page_view", "category", category=cat))
        else:
            row = rng.choice(CATALOG)
            viewed_products.append(row)
            session.events.append(_event(session, ts, "page_view", "product",
                                         product_id=row[0], category=row[2]))

    # ── intent: does this session try to buy? ──
    tier_mult = MEMBERSHIP_TIERS[visitor.membership_tier]["conv_multiplier"]
    dev_mult = DEVICES[visitor.device]["conv_multiplier"]
    intent = min(0.97, p["intent"] * tier_mult * dev_mult)

    if viewed_products and rng.random() < intent:
        cart = rng.sample(viewed_products, k=min(len(viewed_products), rng.randint(1, 3)))
        for row in cart:
            step()
            session.events.append(_event(session, ts, "add_to_cart", "product",
                                         product_id=row[0], category=row[2]))
        step()
        session.events.append(_event(session, ts, "page_view", "cart"))
        step()
        session.events.append(_event(session, ts, "begin_checkout", "checkout"))

        if rng.random() < p["close"]:
            step()
            aov_mult = MEMBERSHIP_TIERS[visitor.membership_tier]["aov_multiplier"]
            total = round(sum(r[3] for r in cart) * aov_mult, 2)
            oid = f"MO-{rng.randrange(10**9, 10**10)}"
            session.events.append(_event(session, ts, "purchase", "confirmation",
                                         order_id=oid, order_total=total))
            # ── AND HERE IS THE FIRST REAL LESSON, HIDING IN A COMMENT ──
            # The `purchase` event is the LAST event of the session and it is
            # the ONLY event worth money. It is also, structurally, the event
            # most likely to be lost: the user closes the tab on the thank-you
            # page, the beacon never flushes, the ad blocker eats it.
            #
            # So the single most valuable event in your entire warehouse is also
            # the most fragile one. Sit with that. It's why rule 04 on your
            # wallpaper exists, and it's Pathology #6 in the next file.

    return session


# ══════════════════════════════════════════════════════════════════════════════
#  A whole day / a whole run
# ══════════════════════════════════════════════════════════════════════════════
def make_visitor(rng: random.Random, returning_pool: list[Visitor]) -> Visitor:
    """New visitor, or one we've seen before?

    ~35% of sessions are returning visitors. This matters more than it looks:
    it's the only reason `sessions` and `unique visitors` differ, and the ratio
    between those two numbers is a metric executives care about deeply while
    defining it inconsistently. You're building that ambiguity on purpose.
    """
    if returning_pool and rng.random() < 0.35:
        return rng.choice(returning_pool)

    tier = _pick(rng, MEMBERSHIP_TIERS)
    v = Visitor(
        visitor_id=str(uuid.uuid4()),
        device=_pick(rng, DEVICES),
        membership_tier=tier,
        # Guests are never logged in. Members USUALLY are — but not always, and
        # that "not always" is where your member metrics go to die.
        member_id=None if tier == "guest" else (
            f"M{rng.randrange(10**7, 10**8)}" if rng.random() < 0.82 else None
        ),
    )
    returning_pool.append(v)
    return v


def generate_clean_events(
    n_sessions: int = 5_000,
    days: int = 7,
    end: datetime | None = None,
    seed: int = 11,
) -> list[dict]:
    """The public entry point. Returns a flat list of event dicts.

    SEEDED ON PURPOSE. Same seed → byte-identical data → your tests can assert
    exact numbers. Unseeded synthetic data is a nightmare to test against, and
    "the test fails sometimes" is how a learning project dies on a Tuesday.
    """
    rng = random.Random(seed)
    end = end or datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    returning_pool: list[Visitor] = []
    events: list[dict] = []

    # Spread sessions across days using the weekday shape, so Sunday is genuinely
    # busier than Tuesday and your daily chart has a heartbeat.
    day_list = [end - timedelta(days=d) for d in range(days - 1, -1, -1)]
    day_weights = [WEEKDAY_SHAPE[d.weekday()] for d in day_list]
    total_w = sum(day_weights)

    for day, w in zip(day_list, day_weights):
        for _ in range(int(round(n_sessions * w / total_w))):
            visitor = make_visitor(rng, returning_pool)
            start = _sample_timestamp(rng, day)
            events.extend(generate_session(rng, visitor, start).events)

    events.sort(key=lambda e: e["event_ts"])
    return events


# ══════════════════════════════════════════════════════════════════════════════
#  ...so that's it? That's clickstream?
# ══════════════════════════════════════════════════════════════════════════════
# Yeah. Run it. Count the rows. Group by day. Compute a conversion rate. It'll
# work perfectly on the first try and you'll feel like a genius.
#
# ...
#
# BRO. BUT THAT'S NOT IT.
#
# Every number you just computed is a lie, and not a small one — I'm talking
# "your conversion rate is off by 40% and pointing the wrong direction" lie.
# Because this data has never touched a network. Never been retried by Kafka.
# Never sat in a phone's pocket in a parking garage for three days. Never been
# scraped by a bot pretending to be an iPhone.
#
# What you have in your hands right now is the data your architecture diagram
# THINKS it produces. Nobody has ever had this data. Not once. Not ever.
#
# Open `pathologies.py`. We're going to fix that.
if __name__ == "__main__":
    evs = generate_clean_events(n_sessions=2000, days=7)
    print(f"{len(evs):,} events across {len({e['session_id'] for e in evs}):,} sessions")

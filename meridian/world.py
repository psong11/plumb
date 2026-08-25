"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MERIDIAN GOODS — the world                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Meridian Goods sells bulk household stuff online. Paper towels in packs of 24.
Olive oil in 3-liter tins. It has a paid membership ("Meridian+"), a store-pickup
flow, and a search box that people type genuinely unhinged things into.

WHY A FAKE COMPANY INSTEAD OF `df = pd.read_csv("clicks.csv")`?

Because the hard part of clickstream data is never the parsing. It's that
"a visit" means four different things to four different teams, and you cannot
feel that with anonymous columns named col_1..col_9. You need a business with
opinions. So we made one.

Everything here is deliberately small enough to hold in your head. That's a
feature. You should be able to predict what your own generator will emit before
you run it — and then be *wrong*, which is where the learning lives.
"""

# ── The catalog ────────────────────────────────────────────────────────────────
# Real retail catalogs have millions of SKUs. Ours has 18. You do not need a
# million SKUs to learn that joining events to products fans out your row count.
CATALOG = [
    # (sku,          name,                        category,      price,  is_bulk)
    ("MG-1001", "Paper Towels, 24 Rolls",       "household",    28.98, True),
    ("MG-1002", "Bath Tissue, 45 Rolls",        "household",    32.44, True),
    ("MG-1003", "Laundry Detergent, 200 oz",    "household",    24.12, True),
    ("MG-2001", "Olive Oil, 3 L",               "pantry",       36.80, True),
    ("MG-2002", "Jasmine Rice, 25 lb",          "pantry",       21.50, True),
    ("MG-2003", "Coffee Beans, 5 lb",           "pantry",       44.99, True),
    ("MG-2004", "Almond Butter, 48 oz",         "pantry",       17.25, False),
    ("MG-3001", "Rotisserie Chicken",           "fresh",         6.99, False),
    ("MG-3002", "Strawberries, 4 lb",           "fresh",        11.40, False),
    ("MG-3003", "Ribeye, USDA Prime, 6 lb",     "fresh",        89.00, True),
    ("MG-4001", "65\" 4K TV",                   "electronics", 549.00, False),
    ("MG-4002", "Robot Vacuum",                 "electronics", 289.99, False),
    ("MG-4003", "Wireless Earbuds",             "electronics",  99.00, False),
    ("MG-5001", "Patio Umbrella, 11 ft",        "outdoor",     179.00, False),
    ("MG-5002", "Propane Grill, 4-Burner",      "outdoor",     399.00, False),
    ("MG-6001", "Multivitamin, 400 ct",         "pharmacy",     22.75, True),
    ("MG-6002", "Allergy Relief, 365 ct",       "pharmacy",     19.99, True),
    ("MG-6003", "Reading Glasses, 3-Pack",      "pharmacy",     14.50, False),
]

CATEGORIES = sorted({row[2] for row in CATALOG})

# ── Membership ─────────────────────────────────────────────────────────────────
# THIS is where metric ambiguity is born. "Member conversion rate" — does that
# mean (a) conversion among people we KNOW are members, (b) among people who were
# LOGGED IN, or (c) among sessions that later got attributed to a member account?
# Those are three different numbers and every one of them is defensible.
# Remember this when you get to Module 03. It's the whole ballgame.
MEMBERSHIP_TIERS = {
    "guest":  {"share": 0.42, "conv_multiplier": 0.35, "aov_multiplier": 0.7},
    "basic":  {"share": 0.38, "conv_multiplier": 1.00, "aov_multiplier": 1.0},
    "plus":   {"share": 0.20, "conv_multiplier": 1.85, "aov_multiplier": 1.6},
}

# ── Devices ────────────────────────────────────────────────────────────────────
# `app` matters enormously and people forget it. A native app can be BACKGROUNDED
# mid-session, buffer its events on disk, and flush them days later. Web can't do
# that — web just loses them. Two totally different failure modes, one column.
DEVICES = {
    "mobile_web": {"share": 0.44, "conv_multiplier": 0.62, "can_buffer_offline": False},
    "desktop":    {"share": 0.27, "conv_multiplier": 1.55, "can_buffer_offline": False},
    "app":        {"share": 0.24, "conv_multiplier": 1.30, "can_buffer_offline": True},
    "tablet":     {"share": 0.05, "conv_multiplier": 0.95, "can_buffer_offline": False},
}

# ── Page types ─────────────────────────────────────────────────────────────────
PAGE_TYPES = ["home", "search", "category", "product", "cart", "checkout", "confirmation"]

# ── Visitor personas ───────────────────────────────────────────────────────────
# A traffic generator that emits uniformly random pages produces data that is
# useless for learning, because every metric comes out flat and boring. Real
# traffic is a MIXTURE of a few archetypes with wildly different shapes, and
# almost every interesting analytics question is secretly "which archetype grew?"
#
# `weight`      how much of total traffic this persona is
# `depth`       (min, max) pages viewed in a session
# `dwell`       (min, max) seconds between events — bots give themselves away here
# `intent`      probability the session reaches checkout at all
# `close`       probability of completing checkout ONCE they get there
PERSONAS = {
    "bouncer": {
        "weight": 0.34, "depth": (1, 2), "dwell": (1.0, 9.0),
        "intent": 0.00, "close": 0.00,
        "note": "Landed, hated it, left. A third of the internet. Your denominator.",
    },
    "browser": {
        "weight": 0.29, "depth": (3, 9), "dwell": (3.0, 45.0),
        "intent": 0.06, "close": 0.30,
        "note": "Window shopping on the couch. Lots of pages, almost no money.",
    },
    "researcher": {
        "weight": 0.13, "depth": (8, 26), "dwell": (10.0, 120.0),
        "intent": 0.22, "close": 0.35,
        "note": "Comparing four TVs across six visits. Will buy — just not today. "
                "Single-session metrics slander this person constantly.",
    },
    "buyer": {
        "weight": 0.08, "depth": (3, 11), "dwell": (2.0, 30.0),
        "intent": 0.78, "close": 0.72,
        "note": "Came to buy paper towels. Bought paper towels. Left.",
    },
    "restocker": {
        "weight": 0.03, "depth": (2, 5), "dwell": (0.5, 7.0),
        "intent": 0.88, "close": 0.90,
        "note": "Reorders the same 6 items monthly. Highest-value, lowest-drama.",
    },
    "checker": {
        "weight": 0.07, "depth": (6, 22), "dwell": (0.7, 4.2),
        "intent": 0.03, "close": 0.40,
        "note": "Checks order status, store hours, and prices. Fast, deep, "
                "almost never carts. THIS is your false positive. Every bot "
                "filter you ever tune will eat some of these, and they are "
                "real people with real money. Meet the tradeoff.",
    },
    "bot": {
        "weight": 0.06, "depth": (12, 80), "dwell": (0.05, 2.6),
        "intent": 0.00, "close": 0.00,
        "note": "Price scraper. Fast, deep, no cart. Some are lazy and obvious; "
                "the commercial ones add jitter to look human. It is in your "
                "data RIGHT NOW and it is inflating your pageviews.",
    },
}

# ── Traffic shape over a day ───────────────────────────────────────────────────
# Relative traffic by hour (local). Retail has a lunch bump and a big couch-time
# evening peak. This exists so that "hourly sessions" charts look like something
# a human would recognize — and so that time-zone bugs are VISIBLE when you make
# them, instead of hiding inside a flat line.
HOURLY_SHAPE = [
    0.28, 0.18, 0.13, 0.11, 0.13, 0.22,   # 00–05  the dead of night
    0.44, 0.71, 0.88, 0.96, 1.00, 1.05,   # 06–11  morning ramp
    1.12, 1.02, 0.94, 0.92, 0.97, 1.15,   # 12–17  lunch bump, afternoon sag
    1.38, 1.52, 1.47, 1.21, 0.83, 0.48,   # 18–23  couch time. the real peak.
]

# Weekday multipliers, Monday=0. Sunday is the big one in bulk retail.
WEEKDAY_SHAPE = [0.94, 0.91, 0.93, 0.98, 1.06, 1.14, 1.22]

SITE = "meridian-goods.example"
EVENT_SCHEMA_VERSION = "2.3.0"   # remember this number. Module 01 breaks it on purpose.

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 02 · BRONZE → SILVER                                                 ║
║  Getting your numbers back. Most of them. And knowing which ones you didn't. ║
╚══════════════════════════════════════════════════════════════════════════════╝

So. You broke your own data. 23 orders vanished, a third of your pageviews are a
scraper wearing a MacBook costume, and somewhere in there are events dated 1970.

Now you fix it.

Except — and this is the reframe I need you to carry for the rest of your career —
**you don't fix it. You can't. You characterize it.**

Bronze is immutable and bronze is honest: it's exactly what arrived, warts and
all, and you never edit it. Silver is bronze plus *judgment*: deduplicated,
sessionized, bot-scored, schema-reconciled. Every one of those words is a
DECISION someone made, and the difference between a real data platform and a pile
of notebooks is whether those decisions are written down, versioned, tested, and
attached to the data as metadata.

That last clause is the whole module. Every transform here emits not just rows
but a COUNT OF WHAT IT DID. How many duplicates it killed. How many events it
quarantined. What share of traffic it thinks is bots. Those counts become the
data quality manifest, the manifest rides along to Module 03, and in Module 04
your agent reads it and says "42,100 sessions, ±3%, 6% suspected bot" instead of
"42,100 sessions."

Wallpaper rules 04 and 05. You're building them right now, by hand.

┌────────────────────────────────────────────────────────────────────────────┐
│  THE PIPELINE                                                              │
│                                                                            │
│   1. quarantine_impossible_timestamps  ← YOU   1970 is not a Tuesday       │
│   2. deduplicate                       ← YOU   at-least-once, undone       │
│   3. resolve_schema_drift              ← YOU   product_id ∪ item_id        │
│   4. classify_bots                     ← YOU   and then SCORE yourself     │
│   5. sessionize                        ← YOU   the 30 minutes nobody       │
│                                                 can justify                │
│   6. apply_watermark                    (worked) when is a day *done*?     │
└────────────────────────────────────────────────────────────────────────────┘

  ⌘K ⌘0  fold every answer key.        pytest module_02_bronze_to_silver -q

THE ONE RULE:
    Columns starting with `_` are GROUND TRUTH. `_is_bot`, `_true_ts`,
    `_is_duplicate`, `_drifted`. In production these do not exist — nobody
    labels their own scraper for you.

    Your pipeline code may NEVER read them. Tests may. There's a guard at the
    bottom of this file that will catch you, and it is not being cute: the
    single most common way a data project fools itself is by leaking the label
    into the feature. Your bot filter will look incredible and then do nothing
    on real traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

# Bounds for "a timestamp a real person could have generated on this site."
# Meridian Goods launched in 2019 and we are not accepting events from the future.
PLAUSIBLE_START = pd.Timestamp("2019-01-01", tz="UTC")
FUTURE_TOLERANCE = timedelta(hours=6)   # some clock skew is legit. six hours isn't.

SESSION_TIMEOUT_MINUTES = 30


@dataclass
class Manifest:
    """What the pipeline did to your data, in numbers.

    This little object is the most important thing in Module 02 and it looks
    like nothing. It's the difference between an agent that says "42,100" and
    an agent that says "42,100, and here's how much we're unsure."

    In production this becomes a table — one row per pipeline run, queryable,
    alertable, trended. When your dedup rate jumps from 1.5% to 9% overnight,
    that is a PRODUCER incident and this table is how you find out on Tuesday
    instead of at the quarterly review.
    """
    rows_in: int = 0
    rows_out: int = 0
    quarantined_timestamps: int = 0
    duplicates_removed: int = 0
    drifted_rows_recovered: int = 0
    bot_events_flagged: int = 0
    bot_sessions_flagged: int = 0
    sessions_derived: int = 0
    events_after_watermark: int = 0
    notes: list[str] = field(default_factory=list)

    def rate(self, n: int) -> float:
        return n / self.rows_in if self.rows_in else 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  1 · QUARANTINE IMPOSSIBLE TIMESTAMPS
# ══════════════════════════════════════════════════════════════════════════════
#
#  Start here because it's the cheapest and because if you skip it, everything
#  downstream gets weird in ways that are genuinely hard to trace.
#
#  You have events dated 1970 and 2038. If you partition a Delta table by
#  event_date and one row says 1970-08-12, you now own a partition containing
#  one row, forever. Do that a few thousand times and your query planner has ten
#  thousand tiny partitions to consider before it reads anything. This is the
#  "small files problem" and it is how a query that should take 4 seconds takes
#  90 and costs you actual money.
#
#  QUARANTINE, DON'T DELETE. Write the bad rows to a side table.
#
#  I cannot stress this enough and it's the tacit part nobody documents: the
#  quarantine table is where you find out that a bad app release started sending
#  garbage timestamps three days ago. If you `WHERE event_ts > '2019-01-01'` in
#  your silver job, those rows evaporate and you never learn anything. A filter
#  hides the incident. A quarantine table *reports* it.
#
# ╭─ HOW IT WORKS ───────────────────────────────────────────────────────────────────────
# │ SIGNATUREdf, manifest
# │
# │ IN      df         bronze DataFrame with `event_ts` and `ingested_at`
# │         manifest   a Manifest — mutate it, don't return it
# │
# │ DOES    A row is IMPOSSIBLE if either:
# │           · event_ts < PLAUSIBLE_START, or
# │           · event_ts > ingested_at + FUTURE_TOLERANCE
# │         (that second one is lovely — you cannot receive a thing before it
# │          happens, so ingestion time is a free upper bound on event time)
# │
# │         Add a column `quarantine_reason` to the bad rows: "before_launch"
# │         or "future_dated". Set manifest.quarantined_timestamps.
# │
# │ OUT     (clean_df, quarantined_df) — both real DataFrames, index reset.
# │
# │ TRAP 1  Do not use `_true_ts`. That's the label. You only have event_ts and
# │         ingested_at in production, and the whole trick is that ingested_at
# │         is enough.
# │ TRAP 2  Both columns must be tz-aware to compare. If pandas yells about
# │         comparing tz-naive and tz-aware, that's your bug, not pandas'.
# ╰──────────────────────────────────────────────────────────────────────────────
def quarantine_impossible_timestamps(df: pd.DataFrame, manifest: Manifest):
    df = df.copy()
    too_old = df["event_ts"] < PLAUSIBLE_START
    too_new = df["event_ts"] > df["ingested_at"] + FUTURE_TOLERANCE
    bad = too_old | too_new

    q = df[bad].copy()
    q["quarantine_reason"] = np.where(too_old[bad], "before_launch", "future_dated")

    manifest.quarantined_timestamps = int(bad.sum())
    if manifest.quarantined_timestamps:
        manifest.notes.append(
            f"{manifest.quarantined_timestamps} events had impossible timestamps "
            f"({int(too_old.sum())} pre-launch, {int(too_new.sum())} future-dated)")
    return df[~bad].reset_index(drop=True), q.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  2 · DEDUPLICATE         
# ══════════════════════════════════════════════════════════════════════════════
#
#  You already know the mechanic: group by event_id, keep one. Ten minutes.
#
#  ...
#
#  BRO. BUT THAT'S NOT IT.
#
#  Which one do you keep?
#
#  Sounds like a trivia question. It is not. Two rows, same event_id, same
#  event_ts, DIFFERENT ingested_at. If you keep the LAST arrival, then a
#  duplicate that shows up next Tuesday drags that event's ingested_at into next
#  Tuesday, and now your watermark logic thinks you're still receiving Tuesday's
#  data and the day never closes. If you keep the FIRST arrival, your pipeline is
#  stable and reproducible: rerun it tomorrow, get the same answer.
#
#  **Keep first-seen.** Reproducibility beats freshness for a row that is, by
#  definition, identical. Write that decision in a comment. Someone will ask.
#
#  And the tacit one, free, from someone who has eaten it: **log the dedup
#  RATE as a metric.** The count you throw away is a leading indicator of
#  producer bugs. A retry storm shows up in the dedup rate hours before it shows
#  up anywhere a human would look.
#
# ╭─ HOW IT WORKS ───────────────────────────────────────────────────────────────────────
# │ SIGNATUREdf, manifest
# │ DOES    one row per event_id; keep the row with the EARLIEST ingested_at.
# │         set manifest.duplicates_removed.
# │ OUT     DataFrame, sorted by ingested_at, index reset.
# │ TRAP 1  Not `.drop_duplicates("event_id")` alone — that keeps whatever row
# │         happens to be first in the current sort order, which is not the same
# │         thing as first-seen and will be subtly wrong on a re-run.
# │ TRAP 2  Triple deliveries exist. Do not assume pairs.
# ╰──────────────────────────────────────────────────────────────────────────────
def deduplicate(df: pd.DataFrame, manifest: Manifest) -> pd.DataFrame:
    before = len(df)
    # DECISION: keep first-seen. A duplicate is by definition identical in
    # payload, so the only thing the later copy adds is a later ingested_at —
    # which would poison the watermark and make re-runs non-reproducible.
    out = (df.sort_values("ingested_at", kind="mergesort")
             .drop_duplicates(subset="event_id", keep="first")
             .reset_index(drop=True))
    manifest.duplicates_removed = before - len(out)
    manifest.notes.append(
        f"dedup removed {manifest.duplicates_removed} rows "
        f"({(before - len(out)) / max(before,1):.2%} of input) — watch this rate")
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  3 · RESOLVE SCHEMA DRIFT
# ══════════════════════════════════════════════════════════════════════════════
#
#  Someone shipped app 2.4.0 and renamed product_id → item_id.
#
#  The fix is a coalesce and it takes one line. That is NOT the exercise.
#
#  The exercise is: **notice, and shout.** Because a silent coalesce is arguably
#  worse than the bug. It papers over an unmanaged producer change, the app team
#  never finds out, and next quarter they rename three more fields because
#  nothing bad happened last time.
#
#  So your function does two things: it heals the column, AND it writes a loud
#  note into the manifest with the app_version and the date it started. That note
#  is the thing you paste into the mobile team's channel. That paste is how the
#  schema registry eventually gets funded. Wallpaper rule 07 — you cannot fix
#  this downstream, you can only make it impossible to ignore.
#
# ╭─ HOW IT WORKS ───────────────────────────────────────────────────────────────────────
# │ SIGNATUREdf, manifest
# │ DOES    1. new column `sku` = product_id, falling back to item_id.
# │         2. count how many rows were rescued FROM item_id → manifest
# │            .drifted_rows_recovered
# │         3. if any drift: append a manifest note naming the app_version(s)
# │            involved and the first date it was seen. Make it loud enough to
# │            paste into Slack.
# │ OUT     DataFrame with `sku`. Keep product_id and item_id — bronze lineage
# │         should survive into silver so you can always prove what happened.
# │ TRAP    pandas `.combine_first()` or `.fillna()` both work. `np.where` on
# │         object columns with None gets weird — check your nulls are actually
# │         null and not the string "None" after a parquet round-trip.
# ╰──────────────────────────────────────────────────────────────────────────────
def resolve_schema_drift(df: pd.DataFrame, manifest: Manifest) -> pd.DataFrame:
    df = df.copy()
    if "item_id" not in df.columns:
        df["item_id"] = None

    prod = df["product_id"].where(df["product_id"].notna(), None)
    item = df["item_id"].where(df["item_id"].notna(), None)
    df["sku"] = prod.combine_first(item)

    rescued = df["product_id"].isna() & df["item_id"].notna()
    manifest.drifted_rows_recovered = int(rescued.sum())

    if manifest.drifted_rows_recovered:
        versions = sorted(df.loc[rescued, "app_version"].dropna().unique())
        first_seen = df.loc[rescued, "event_ts"].min()
        manifest.notes.append(
            f"⚠️  UNMANAGED SCHEMA CHANGE: {manifest.drifted_rows_recovered} events "
            f"sent `item_id` instead of `product_id`. app_version={versions}, "
            f"first seen {first_seen:%Y-%m-%d %H:%M}. Silver healed it via coalesce, "
            f"but the producer contract is broken and every consumer reading "
            f"product_id directly is silently dropping these rows.")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  4 · CLASSIFY BOTS       
# ══════════════════════════════════════════════════════════════════════════════
#
#  My favorite exercise in the repo, because you get a SCORE at the end and the
#  score will be worse than you expect, and that's the lesson.
#
#  You have no user agents, no IPs, no vendor list. You have behavior. Which is
#  fine — behavior is the better signal anyway. Bots differ from humans in ways
#  that are almost embarrassingly visible:
#
#    · dwell time. Humans take 4–120s between pages. A scraper takes 0.05–0.9s.
#      A median inter-event gap under a second is not a person.
#    · depth. 40 product views in one session, no cart, no search.
#    · regularity. Human gaps are ragged. Bot gaps are metronomic — LOW VARIANCE
#      is the sneaky one, and it's the one that catches bots that add random
#      delays to look human, because they usually randomize uniformly and humans
#      are heavy-tailed.
#
#  YOU WILL NOT GET 100%. Set that down now. The "restocker" persona — reorders
#  the same six items, moves fast, knows exactly where everything is — looks a
#  LOT like a bot. Every point of recall you buy costs you precision on your most
#  valuable customers.
#
#  So the deliverable isn't a perfect filter. It's a filter WITH A KNOWN
#  PRECISION AND RECALL, published next to the number. That's wallpaper rules
#  04 and 05 and it's why we generated `_is_bot` alongside the data: so you can
#  actually measure yourself instead of vibing.
#
#  DO NOT READ `_is_bot` IN THIS FUNCTION. The guard will catch you. More
#  importantly, you'll catch yourself, and it'll feel bad, and it should.
#
# ╭─ HOW IT WORKS ───────────────────────────────────────────────────────────────────────
# │ SIGNATUREdf, manifest
# │ DOES    Add a boolean column `is_suspected_bot`, constant within a session.
# │         Build session-level features from `event_ts` and event counts, e.g.:
# │           median_gap   median seconds between consecutive events
# │           gap_stdev    std-dev of those gaps  (low = metronomic = robot)
# │           depth        events in session
# │           carted       did the session ever add_to_cart / purchase?
# │         Then a rule. Start dumb — `median_gap < 1.0 and depth >= 10` — run
# │         the scorer, then tune. Tuning against a printed confusion matrix is
# │         the single most useful hour in this module.
# │ ALSO    set manifest.bot_events_flagged and .bot_sessions_flagged
# │ TRAP 1  Sessions of length 1 have no gaps. Don't emit NaN into your rule.
# │ TRAP 2  Compute gaps WITHIN session, sorted by event_ts. A global .diff()
# │         gives you the gap to whatever unrelated event happened to be next.
# │ TRAP 3  Never flag a session that purchased. A bot that gives you money is
# │         a customer. (Yes, really. Write the comment.)
# ╰──────────────────────────────────────────────────────────────────────────────
def classify_bots(df: pd.DataFrame, manifest: Manifest) -> pd.DataFrame:
    df = df.sort_values(["session_id", "event_ts"], kind="mergesort").copy()
    gaps = df.groupby("session_id")["event_ts"].diff().dt.total_seconds()
    df["_gap"] = gaps

    feats = df.groupby("session_id").agg(
        median_gap=("_gap", "median"),
        gap_stdev=("_gap", "std"),
        depth=("event_id", "size"),
    )
    converted = (df.assign(_c=df["event_name"].isin(["add_to_cart", "purchase"]))
                   .groupby("session_id")["_c"].any())
    feats["carted"] = converted
    feats["median_gap"] = feats["median_gap"].fillna(999.0)
    feats["gap_stdev"] = feats["gap_stdev"].fillna(999.0)

    # Tuned by staring at the confusion matrix, not by theory. Notice it is
    # two OR'd rules, both crude. That is normal and it is fine. Resist the urge
    # to reach for a model here — you have no labels in production, so you'd be
    # training on a heuristic anyway, and then you'd have a heuristic you can no
    # longer read.
    suspect = (
        ((feats["median_gap"] < 1.6) & (feats["depth"] >= 10))
        | ((feats["gap_stdev"] < 0.9) & (feats["depth"] >= 14))
    )
    # A session that carted or bought is a customer, full stop. Whatever it is,
    # it is giving us money and we are not deleting it from our denominator.
    suspect = suspect & (~feats["carted"])

    df["is_suspected_bot"] = df["session_id"].map(suspect).fillna(False)
    df = df.drop(columns=["_gap"])
    manifest.bot_events_flagged = int(df["is_suspected_bot"].sum())
    manifest.bot_sessions_flagged = int(suspect.sum())
    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  5 · SESSIONIZE          
# ══════════════════════════════════════════════════════════════════════════════
#
#  Bronze already has a session_id. The app generated it. Why are you rebuilding it?
#
#  Because **the app's session_id is a client-side opinion** and you are about to
#  learn to distrust it. It resets when the app restarts. It survives across a
#  lunch break it shouldn't. It's absent entirely on the web when cookies get
#  cleared. If your top-line "sessions" metric is a `COUNT(DISTINCT session_id)`
#  over a field the mobile team controls, then the mobile team controls your
#  top-line metric and neither of you knows it.
#
#  So silver derives its own, server-side, from a rule you own:
#
#      A new session starts when the same visitor has been idle > 30 minutes.
#
#  And now the thing I actually want you to walk away with:
#
#      **Thirty minutes is completely arbitrary.**
#
#  It's from Urchin, 2005, which became Google Analytics, and the entire industry
#  inherited it without ever re-deriving it. There is no physics here. Someone
#  reading product reviews for 35 minutes and buying is TWO sessions, and the
#  first one is a "bounce," and your bounce rate is a little worse for it.
#
#  This is your first real taste of Module 03: a metric is a *choice*, and the
#  reason the org can't agree on "sessions" is not that nobody wrote it down —
#  it's that the choice is genuinely arbitrary and three teams made it
#  differently. Your job is not to be right. Your job is to make the choice
#  explicit, versioned, and singular.
#
# ╭─ HOW IT WORKS ───────────────────────────────────────────────────────────────────────
# │ SIGNATUREdf, manifest, timeout_minutes=SESSION_TIMEOUT_MINUTES
# │ DOES    Add `derived_session_id`. Within each visitor_id, ordered by
# │         event_ts, start a new session whenever the gap from the previous
# │         event exceeds timeout_minutes. Make the id stable and readable:
# │           f"{visitor_id}:{session_start_epoch}"
# │         set manifest.sessions_derived
# │ OUT     DataFrame with the new column.
# │ TRAP 1  Partition by VISITOR, not session. You're deliberately ignoring the
# │         client's session boundaries — that's the whole exercise.
# │ TRAP 2  The first event of a visitor has a NaT gap. That's a session start.
# │ TRY     Compare your count to df.session_id.nunique(). They will NOT match.
# │         Go find one visitor where they disagree and read their event log
# │         line by line until you understand why. That five minutes is worth
# │         more than the function.
# ╰──────────────────────────────────────────────────────────────────────────────
def sessionize(df: pd.DataFrame, manifest: Manifest,
                       timeout_minutes: int = SESSION_TIMEOUT_MINUTES) -> pd.DataFrame:
    df = df.sort_values(["visitor_id", "event_ts"], kind="mergesort").copy()
    gap = df.groupby("visitor_id")["event_ts"].diff()
    new_session = gap.isna() | (gap > pd.Timedelta(minutes=timeout_minutes))
    ordinal = new_session.groupby(df["visitor_id"]).cumsum()

    starts = (df.assign(_o=ordinal)
                .groupby(["visitor_id", "_o"])["event_ts"].transform("min"))
    df["derived_session_id"] = (
        df["visitor_id"].astype(str) + ":" + (starts.astype("int64") // 10**9).astype(str))

    manifest.sessions_derived = int(df["derived_session_id"].nunique())
    client_sessions = int(df["session_id"].nunique())
    manifest.notes.append(
        f"sessionization: client said {client_sessions:,} sessions, "
        f"server-derived {manifest.sessions_derived:,} "
        f"({manifest.sessions_derived / max(client_sessions,1) - 1:+.1%}). "
        f"Neither is wrong. They answer different questions.")
    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  6 · APPLY WATERMARK
# ══════════════════════════════════════════════════════════════════════════════
def apply_watermark(df: pd.DataFrame, manifest: Manifest,
                    lateness_hours: float = 72.0) -> pd.DataFrame:
    """When is a day *done*?

    This is the function that answers the tunnel story, and I wrote it because
    the concept is subtle enough that seeing it beats guessing at it.

    Here's the situation. It's Wednesday 6am. Your job runs. It sees Tuesday and
    says "Tuesday had 41,200 sessions." Somebody screenshots it.

    On Friday, a phone comes out of a parking garage and flushes 700 events
    stamped Tuesday. Tuesday is now 41,900 sessions. **The past changed.** No
    error. No alert. The screenshot is just wrong now.

    A watermark is the industry's answer, and it is disappointingly honest:

        Pick a lateness budget. Wait that long. Then declare the day CLOSED and
        refuse to accept anything later.

    That's it. That's the whole idea. Flink, Beam, Spark Structured Streaming —
    all of them, this idea, wrapped in more machinery.

    Notice what a watermark actually is: **it's not a technical mechanism, it's
    a business SLA wearing a technical costume.** 72 hours means "we accept that
    we will permanently discard some real events in exchange for numbers that
    stop changing." Shorter watermark → fresher, more wrong, more churn.
    Longer → truer, but Tuesday isn't final until Friday and finance hates you.

    There is no correct answer. There is only a decision, and the decision has
    to be WRITTEN DOWN, because the day someone asks "why did Tuesday change?"
    the only acceptable reply is "it didn't, here's our lateness policy and here
    are the 43 events we rejected under it."

    Which is why this function counts what it rejects, instead of filtering
    quietly. Are you noticing a pattern in this module? Good. That's the pattern.
    """
    df = df.copy()
    df["event_date"] = df["event_ts"].dt.floor("D")
    df["lateness"] = df["ingested_at"] - df["event_ts"]
    budget = pd.Timedelta(hours=lateness_hours)

    too_late = df["lateness"] > budget
    n_late = int(too_late.sum())

    df["arrived_after_watermark"] = too_late
    manifest.events_after_watermark = n_late
    if n_late:
        affected = df.loc[too_late, "event_date"].dt.date.value_counts().to_dict()
        manifest.notes.append(
            f"{n_late} events arrived beyond the {lateness_hours:g}h lateness budget "
            f"and are excluded from closed days. Affected dates: {affected}. "
            f"These are REAL user actions we are choosing to discard. That is a "
            f"business decision, not a bug — but somebody should be told it exists.")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  THE GUARD — no peeking
# ══════════════════════════════════════════════════════════════════════════════
TRUTH_COLUMNS = {"_true_ts", "_is_bot", "_persona", "_is_duplicate",
                 "_was_buffered", "_drifted", "_bot_spoofed"}


def assert_no_truth_leakage(source: str) -> None:
    """Fail loudly if pipeline code reads a ground-truth column.

    This exists because label leakage is the most seductive bug in data work.
    Your bot filter hits 100% and you feel like a genius and then it does
    literally nothing in production because `_is_bot` isn't a real column.

    Every ML team learns this the hard way exactly once. You get to skip it.
    """
    hits = [c for c in TRUTH_COLUMNS if c in source]
    if hits:
        raise AssertionError(
            f"pipeline code references ground-truth column(s) {hits}. "
            "Those don't exist in production. That's not a filter, that's a spoiler.")

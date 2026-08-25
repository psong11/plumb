"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MODULE 02 · THE SCORER                                                      ║
║  You built a bot filter. Is it any good? Now you find out.                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

I wrote this one. It's the part of synthetic data that people skip and it's the
part that makes the whole exercise worth doing.

Because we generated the data, we know which sessions were REALLY bots. So we can
grade your heuristic with an actual confusion matrix instead of a feeling. In
production you don't get this — which is exactly why practicing here matters. You
develop calibration for what a "pretty good" behavioral filter actually scores,
and then when a vendor tells you they're at 99% you'll know to ask 99% of what.
"""
from __future__ import annotations

import pandas as pd


def score_bot_filter(df: pd.DataFrame) -> dict:
    """Confusion matrix for `is_suspected_bot` vs the `_is_bot` ground truth.

    PRECISION  of the sessions you flagged, how many really were bots?
               Low precision = you are deleting real customers from your
               denominator. Expensive and invisible.

    RECALL     of the real bots, how many did you catch?
               Low recall = your pageviews stay inflated and every
               per-visit metric reads low.

    You will not max both. That is not a skill issue, it is the shape of the
    problem. Pick which error you'd rather make and be able to say why — that
    sentence is the actual PM deliverable, not the F1 score.
    """
    s = (df.groupby("session_id")
           .agg(pred=("is_suspected_bot", "any"), truth=("_is_bot", "any")))

    tp = int((s.pred & s.truth).sum())
    fp = int((s.pred & ~s.truth).sum())
    fn = int((~s.pred & s.truth).sum())
    tn = int((~s.pred & ~s.truth).sum())

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1}


def print_scorecard(score: dict) -> None:
    p, r, f1 = score["precision"], score["recall"], score["f1"]
    verdict = (
        "That's a solid behavioral filter. Now go read your false positives —\n"
        "     I promise at least one of them is a `restocker`, i.e. your best customer."
        if f1 > 0.75 else
        "Tune it. Print the false negatives, look at their median_gap and depth,\n"
        "     and move ONE threshold at a time. This hour is the module."
    )
    print(f"""
  ┌─ BOT FILTER SCORECARD ─────────────────────────────────────────────┐
  │  caught (TP)        {score['tp']:>7,}    missed (FN)      {score['fn']:>7,}      │
  │  false alarms (FP)  {score['fp']:>7,}    clean (TN)       {score['tn']:>7,}      │
  ├────────────────────────────────────────────────────────────────────┤
  │  precision  {p:>6.1%}   ← of what you flagged, this much was real   │
  │  recall     {r:>6.1%}   ← of the real bots, you caught this much    │
  │  F1         {f1:>6.1%}                                              │
  └────────────────────────────────────────────────────────────────────┘
     {verdict}
""")


def restatement_demo(df: pd.DataFrame, report_hour: int = 6) -> pd.DataFrame:
    """Prove the tunnel story with your own data.

    Two versions of the same day:

      `_early`  what the batch job saw at 6am the next morning
      `_final`  what's true now that the stragglers have landed

    Same day, same definition, same code. Different numbers, because one waited
    longer. Nothing broke.

    NOW — READ THE OUTPUT CAREFULLY, because there's a second lesson hiding in
    it that took me an embarrassingly long time to notice the first time:

        **Sessions barely move. Purchases move a lot.**

    Why? A session's FIRST event almost always arrives on time — that's when the
    phone still had signal. It's the TAIL that gets buffered in the tunnel. So
    the session already existed in the early count; it just showed up shorter.

    And what lives in the tail of a session? add_to_cart. begin_checkout.
    purchase. The money.

    So late data leaves your top-line traffic number looking rock solid while
    quietly deflating your conversion rate, and then correcting it days later.
    Your traffic dashboard says "stable," your conversion dashboard says
    "recovering," and neither of them is describing anything that happened.

    This is why "sessions are fine so the pipeline is fine" is a sentence that
    should make you nervous for the rest of your career. Freshness bias is not
    uniform across a funnel. It concentrates exactly where the value is.
    """
    d = df.copy()
    d["event_date"] = d["event_ts"].dt.floor("D")
    # A real batch job runs at a WALL CLOCK time, not "24h after each event."
    # An 11pm event gets 7 hours of grace; a 1am event gets 29. Modelling it as
    # a flat window hides the exact effect we're trying to show.
    report_at = d["event_date"] + pd.Timedelta(days=1) + pd.Timedelta(hours=report_hour)
    early = d[d["ingested_at"] <= report_at]

    def roll(x: pd.DataFrame, suffix: str) -> pd.DataFrame:
        g = x.groupby("event_date")
        return pd.DataFrame({
            f"events{suffix}":    g["event_id"].size(),
            f"sessions{suffix}":  g["derived_session_id"].nunique(),
            f"purchases{suffix}": g.apply(
                lambda s: int((s["event_name"] == "purchase").sum()),
                include_groups=False),
        })

    out = roll(early, "_early").join(roll(d, "_final"), how="outer").fillna(0).astype(int)
    out = out[out["sessions_final"] > 50]

    out["conv_early"] = (out["purchases_early"] / out["sessions_early"].replace(0, 1))
    out["conv_final"] = (out["purchases_final"] / out["sessions_final"].replace(0, 1))
    out["conv_moved"] = ((out["conv_final"] - out["conv_early"])
                         / out["conv_early"].replace(0, 1)).map("{:+.2%}".format)
    out["conv_early"] = out["conv_early"].map("{:.3%}".format)
    out["conv_final"] = out["conv_final"].map("{:.3%}".format)
    out.index = out.index.strftime("%a %m-%d")

    return out[["sessions_early", "sessions_final",
                "purchases_early", "purchases_final",
                "conv_early", "conv_final", "conv_moved"]].tail(8)

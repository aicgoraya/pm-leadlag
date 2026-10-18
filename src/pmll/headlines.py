"""Headline-timestamp conditioning.

The main alternative explanation for "PM leads asset" is that both react to
the same public headline and PM books just update a few seconds faster, or
that the asset reacted first and PM caught up (so PM is lagging).

For each jump we record the earliest public timestamp we can find for the
underlying news (`first_public_ts`). Sources, in order of preference:
  1. Wire timestamps (Reuters/AP/Bloomberg first alert) - manual lookup
  2. Official statements (White House, IDF, CENTCOM, Kremlin) - manual
  3. First tweet from a verified major outlet - manual
  4. GDELT 15-minute event feed - automated lower bound (coarse)

This file does not scrape; it defines the schema and the classification.
Fill `data/headlines.csv` by hand for every jump in the event sample. That
is a few hours of work and it is the single most important data-quality
step in the project, because without it every lead-lag result has an
obvious "same headline" rebuttal.

Classification of each jump relative to first_public_ts:
  PRE     jump minute < first_public_ts - tolerance   (PM moved before public news)
  SAME    |jump - first_public| <= tolerance            (simultaneous reaction)
  POST    jump > first_public_ts + tolerance            (PM lagged the news)
  UNKNOWN no timestamp found

The paper reports every result split by this class. The interesting
category is PRE. If PRE jumps show asset follow-through, the PM contained
information not yet public. If only SAME/POST do, the PM is a fast reader,
not a leader. Note that PRE jumps on military events are exactly the
insider-trading cases documented by ACDC/Bloomberg; the paper should say so
and refrain from attributing any specific wallet.
"""
from __future__ import annotations

import pandas as pd

SCHEMA = ["jump_ts", "condition_id", "first_public_ts", "source", "source_url", "notes"]


def load_headlines(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ("jump_ts", "first_public_ts"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def classify(jumps: pd.DataFrame, headlines: pd.DataFrame, condition_id: str,
             tolerance_min: int = 2) -> pd.Series:
    h = headlines[headlines["condition_id"] == condition_id].set_index("jump_ts")["first_public_ts"]
    out = {}
    for t in jumps.index:
        fp = h.get(t, pd.NaT)
        if pd.isna(fp):
            out[t] = "UNKNOWN"
            continue
        delta = (t - fp).total_seconds() / 60
        if delta < -tolerance_min:
            out[t] = "PRE"
        elif delta > tolerance_min:
            out[t] = "POST"
        else:
            out[t] = "SAME"
    return pd.Series(out, name="headline_class")


def template(jumps: pd.DataFrame, condition_id: str) -> pd.DataFrame:
    """Blank rows to fill by hand for each detected jump."""
    return pd.DataFrame({
        "jump_ts": jumps.index,
        "condition_id": condition_id,
        "first_public_ts": pd.NaT,
        "source": "",
        "source_url": "",
        "notes": "",
    })

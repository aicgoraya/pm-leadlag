#!/usr/bin/env python3
"""Clean data/events_raw.csv -> data/events.csv.

- Parses dates; where endDate is missing or earlier than startDate, infers it
  from "by <Month> <day>[, <year>]" in the question (Gamma's endDate is
  unreliable for short-dated ladder markets).
- Adds a `window_end` = endDate + 2 days so price history covers resolution.
- Drops rows still lacking a usable endDate and reports them.

Usage: python scripts/build_events.py data/events_raw.csv data/events.csv
"""
import re
import sys

import pandas as pd

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def infer_end(question: str, start: pd.Timestamp) -> pd.Timestamp | None:
    m = re.search(r"by\s+([A-Za-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?", question)
    if not m:
        m2 = re.search(r"(?:in|by end of|before)\s+(\d{4})", question)
        if m2:
            return pd.Timestamp(int(m2.group(1)), 12, 31, tz="UTC")
        return None
    mon = MONTHS.get(m.group(1).lower())
    if mon is None:
        return None
    day = int(m.group(2))
    year = int(m.group(3)) if m.group(3) else start.year
    try:
        end = pd.Timestamp(year, mon, day, tz="UTC")
    except ValueError:
        return None
    if end < start:  # "by January 31" asked in December -> next year
        end = pd.Timestamp(year + 1, mon, day, tz="UTC")
    return end


def main(src, dst):
    ev = pd.read_csv(src)
    ev["startDate"] = pd.to_datetime(ev["startDate"], utc=True, errors="coerce")
    ev["endDate"] = pd.to_datetime(ev["endDate"], utc=True, errors="coerce")
    fixed, dropped = [], []
    for i, r in ev.iterrows():
        if pd.isna(r["endDate"]) or r["endDate"] < r["startDate"]:
            e = infer_end(str(r["question"]), r["startDate"])
            if e is None:
                dropped.append(r["question"]); continue
            ev.at[i, "endDate"] = e
            fixed.append((r["question"], e.date()))
    ev = ev[ev["endDate"].notna() & (ev["endDate"] >= ev["startDate"])].copy()
    ev["window_end"] = ev["endDate"] + pd.Timedelta(days=2)
    ev["is_control"] = ev["is_control"].astype(str).str.lower().isin(["true", "1", "yes"])
    ev.to_csv(dst, index=False)
    print(f"wrote {len(ev)} rows -> {dst}")
    for q, e in fixed:
        print("  fixed endDate:", q, "->", e)
    for q in dropped:
        print("  DROPPED (no endDate):", q)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

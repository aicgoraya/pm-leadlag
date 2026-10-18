"""Exchange session calendars.

Polymarket trades 24/7. CME futures (CL, ES, ZN, GC, VX) trade nearly 24/5
with a daily maintenance break; NYSE equities (ITA, LMT, RTX) trade
09:30-16:00 ET. The lead-lag tests need to know, for every UTC minute,
whether each conventional asset was open, and where the next open is.

All times are handled in UTC internally. ET conversion uses zoneinfo so DST
is correct.

CME Globex (approximate, sufficient for this study):
    Open  Sunday 18:00 ET  ->  Friday 17:00 ET
    Daily break 17:00-18:00 ET Mon-Thu
    (Equity index, energy, metals, treasuries all share this schedule
     closely enough; VX differs slightly but we treat it the same.)

Holidays: we do NOT hard-code the CME holiday calendar. Instead, the
loaders mark minutes with no bars as closed (see `assets.infer_sessions`),
which handles holidays and early closes empirically. The functions here
give the *scheduled* calendar for the weekend design.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


@dataclass(frozen=True)
class Session:
    """A contiguous trading session [open, close) in UTC."""

    open: pd.Timestamp
    close: pd.Timestamp

    def contains(self, ts: pd.Timestamp) -> bool:
        return self.open <= ts < self.close


def _et(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert(ET).to_pydatetime()


def cme_is_open(ts: pd.Timestamp) -> bool:
    """Scheduled CME Globex open/closed status at a UTC timestamp."""
    t = _et(ts)
    wd = t.weekday()  # Mon=0 ... Sun=6
    hm = t.time()
    if wd == 5:  # Saturday
        return False
    if wd == 6:  # Sunday: opens 18:00 ET
        return hm >= time(18, 0)
    if wd == 4:  # Friday: closes 17:00 ET
        return hm < time(17, 0)
    # Mon-Thu: closed 17:00-18:00 ET
    return not (time(17, 0) <= hm < time(18, 0))


def nyse_is_open(ts: pd.Timestamp) -> bool:
    """Scheduled NYSE regular-hours status (09:30-16:00 ET, Mon-Fri)."""
    t = _et(ts)
    if t.weekday() >= 5:
        return False
    return time(9, 30) <= t.time() < time(16, 0)


def is_open(ts: pd.Timestamp, venue: str) -> bool:
    venue = venue.lower()
    if venue == "cme":
        return cme_is_open(ts)
    if venue == "nyse":
        return nyse_is_open(ts)
    if venue == "polymarket":
        return True
    raise ValueError(f"unknown venue {venue!r}")


def open_mask(index: pd.DatetimeIndex, venue: str) -> np.ndarray:
    """Vectorised scheduled-open mask for a UTC DatetimeIndex."""
    if index.tz is None:
        raise ValueError("index must be tz-aware UTC")
    local = index.tz_convert(ET)
    wd = local.weekday
    minutes = local.hour * 60 + local.minute
    venue = venue.lower()
    if venue == "polymarket":
        return np.ones(len(index), dtype=bool)
    if venue == "nyse":
        return (wd < 5) & (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)
    if venue == "cme":
        sat = wd == 5
        sun = (wd == 6) & (minutes < 18 * 60)
        fri = (wd == 4) & (minutes >= 17 * 60)
        brk = (wd <= 3) & (minutes >= 17 * 60) & (minutes < 18 * 60)
        return ~(sat | sun | fri | brk)
    raise ValueError(f"unknown venue {venue!r}")


def next_open(ts: pd.Timestamp, venue: str) -> pd.Timestamp:
    """First scheduled open minute at or after `ts` (UTC)."""
    ts = ts.floor("min")
    if is_open(ts, venue):
        return ts
    # step forward minute by minute; at most ~3 days of minutes
    probe = ts
    for _ in range(4 * 24 * 60):
        probe = probe + pd.Timedelta(minutes=1)
        if is_open(probe, venue):
            return probe
    raise RuntimeError("no open found within 4 days; calendar bug?")


def prev_close(ts: pd.Timestamp, venue: str) -> pd.Timestamp:
    """Last scheduled open minute strictly before `ts` (UTC)."""
    ts = ts.floor("min")
    probe = ts
    for _ in range(4 * 24 * 60):
        probe = probe - pd.Timedelta(minutes=1)
        if is_open(probe, venue):
            return probe
    raise RuntimeError("no prior open within 4 days; calendar bug?")


def closed_windows(start: pd.Timestamp, end: pd.Timestamp, venue: str,
                   min_minutes: int = 120) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Scheduled closed windows of at least `min_minutes` in [start, end).

    Returns (last_open_minute, first_reopen_minute) pairs. Used by the
    weekend design to find every closure (weekends, and the daily break
    if min_minutes <= 60).
    """
    idx = pd.date_range(start.floor("min"), end.floor("min"), freq="min", tz="UTC")
    mask = open_mask(idx, venue)
    out = []
    i = 0
    n = len(idx)
    while i < n:
        if mask[i]:
            i += 1
            continue
        j = i
        while j < n and not mask[j]:
            j += 1
        if j - i >= min_minutes and i > 0 and j < n:
            out.append((idx[i - 1], idx[j]))
        i = j
    return out

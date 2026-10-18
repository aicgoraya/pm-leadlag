# Do prediction markets lead conventional markets on geopolitical events?

Lead-lag study between Polymarket geopolitical/military contracts and oil
futures, defense equities, Treasuries, VIX and gold, at minute frequency.

**Status (2026-10-18):** pipeline validated (13/13 synthetic tests). Real data
pulled: 76-91 Polymarket markets at minute resolution (coverage median 99.7% of
minutes quoted) and 9 ETFs at minute bars incl. extended hours (Massive, Oct 2024
to Oct 2026). **First real result from the closed-hours design is in** (see
"Preliminary results"). Full battery (event study, Granger, TE) still running.

## Preliminary results (closed-hours design, 2026-10-18)

When Polymarket odds on Iran / Strait-of-Hormuz events move while US equity
markets are closed, oil ETFs gap in the predicted direction at the open.

Pooled over all geopolitical markets, one row per event cluster per closure,
per-market signs (scripts/assign_signs.py), cluster-robust SE by closure,
artifact closures removed (see "Data artifacts"):

| asset | n | clusters | beta (log-ret per log-odds) | t | p |
|---|---|---|---|---|---|
| USO, 30 min | 1757 | 466 | 0.0121 | 4.17 | <1e-4 |
| XLE, 30 min | 1836 | 485 | 0.0049 | 4.06 | <1e-4 |
| USO, 1 min (open gap) | 1757 | 466 | 0.0117 | 4.24 | <1e-4 |
| USO, weekends only | 378 | 100 | 0.0070 | 2.43 | 0.015 |
| XLE, weekends only | 379 | 100 | 0.0026 | 1.96 | 0.050 |
| TLT, 30 min | 2226 | 450 | -0.0009 | -2.43 | 0.015 |
| SPY, GLD, ITA, LMT, RTX | | | ~0 | <1.5 | n.s. |

Source: Iran markets (XLE t=3.7, USO t=3.6, 224 clusters) and Hormuz markets
(USO t=3.9, XLE t=3.7, 105 clusters; beta 0.028 on USO, i.e. a 50%->73% move
predicts ~2.8% on USO at the open). Nothing from Ukraine, Israel, Taiwan,
tariffs, other military. Controls (sports/entertainment) null on every asset.

Checks passed:
- Shuffle placebo (permute each market's closure moves across its own closures): all |t|<1.8.
- Reverse direction (asset return in last 60 open minutes -> PM closure move): all |t|<0.8.
- Pre-closure PM move as control: insignificant for oil (t_pre ~ -0.2).
- Effect present at first minute of trading, not accumulated over the morning.
- Robust to dropping artifact closures (see below).

What it does NOT show: whether PM aggregated public overnight news that oil
couldn't trade on, or absorbed non-public information. The headline-timestamp
step (data/headlines_template.csv, 353 jumps >=10pt on treated markets, 196
during closed hours) separates those. Not done yet.

Earlier pass with category-level signs produced a spurious defense-stock
result (RTX t=3.0) because ceasefire and strike markets were coded the same
direction; it vanished once signs were per-market. Keep signs per market.

## Data artifacts found

- **2025-12-27 01:01 UTC:** 13 unrelated markets snapped to exactly p=0.50 in
  the same minute (empty-book default). Feed outage or book reset, not news.
  `pmll.jumps.flag_artifacts` flags simultaneous multi-market jumps and
  p_after==0.50 exactly. 104 closure rows had an exact-0.50 endpoint and 124
  spanned the 12-27 minute; result unchanged after dropping both.
- 4 more minutes with 3+ simultaneous jumps (2025-04-19 22:20, 2026-05-08
  19:06, 2026-05-23 20:33, 2026-06-11 17:30). Check each: some may be real
  (one news event moving several Iran rungs), some not.
- Massive ETF bars include 04:00-20:00 ET extended hours; 38% of USO bars are
  outside regular session. `to_minute_grid(regular_hours_only=True)` for the
  regular-session robustness run.
- 27/91 Polymarket pulls initially failed on network timeouts when the Mac
  slept; `_fetch_chunk` now retries with backoff. All were recoverable.

## Research question

When a Polymarket contract on a geopolitical event (US strikes Iran, Hormuz
closure, Ukraine ceasefire, ...) reprices, do conventional assets follow,
and by how long? Three designs, in increasing cleanliness:

1. **Overlap-hours lead-lag.** Granger causality (HAC), transfer entropy
   and cross-correlation between 1-min Polymarket log-odds changes and asset
   returns, while the asset venue is open. Run both directions; the claim
   is asymmetry.
2. **Event study around Polymarket jumps.** Signed CARs at -15, -5, +1, +5,
   +15, +30, +60 minutes with a placebo distribution from random minutes.
   The *pre-window* (negative horizons) is the key diagnostic: if the asset
   already moved before the jump, the prediction market was lagging a
   headline, not leading.
3. **Closed-hours (weekend) design.** For each venue closure, regress the
   asset's reopen gap on the Polymarket move accumulated during the closure.
   During closure the asset *cannot* react, so this cannot be simultaneity.
   Generalises the single election-night observation in Aktug & Torul (2026).

Plus a tradability check (jump-following rule net of costs) as the
economic-significance test.

## Prior work to cite (and differentiate from)

- Aktug & Torul (2026), *Price Discovery across Political Prediction Markets*,
  SSRN 7051166 — §5.7 shows Polymarket hit milestones 15-225 min before ES
  on 2024 election night; descriptive, one night, ES + DJT only. The precedent.
- Ng, Peng, Tao, Zhou (2026), *Price Discovery and Trading in Modern
  Prediction Markets*, SSRN 5331995 — PM-vs-PM (Polymarket vs Kalshi).
- Azqueta-Gavaldón & Ureta (2026), *CausalAlpha*, arXiv 2606.07049 —
  OSINT-text geopolitical index → energy equities, daily SVAR, weak
  transmission. Same assets/question, different signal; motivates sub-hour.
- Leigh, Wolfers & Zitzewitz (2003), NBER 9587 — TradeSports "Saddam
  Security" vs oil/equities, daily, contemporaneous. The ancestor.
- Qin & Yang (2026), arXiv 2606.04217 — Polymarket-v1 on-chain trade
  database (1.2B trades, aggressor flags). Data source for trade-level work.
- ACDC (2026) reports and Mitts & Ofir (2026), SSRN — insider-trading
  evidence on military markets. Relevant because PRE-headline jumps on
  military markets are exactly those cases; this paper does not attribute
  trades to anyone.

The novelty check (16-20 searches per idea, Oct 2026) found no systematic
multi-event intraday lead-lag study from prediction markets to conventional
assets on geopolitical events. Re-check before submission; the area moves
monthly.

## Repository layout

```
src/pmll/
  calendar.py     CME/NYSE scheduled sessions, closure windows
  polymarket.py   Gamma metadata + CLOB minute price history; minute grid; trades->minute
  assets.py       DataBento/CSV minute bars -> grid with empirical open mask; returns; gap returns
  align.py        common UTC minute grid; overlap filter; k-minute resampling
  jumps.py        Lee-Mykland (floored) + threshold jump detection, merged
  eventstudy.py   signed CARs, placebo, summary with t and placebo p
  leadlag.py      Granger (HAC Wald), transfer entropy (surrogate p), xcorr, Hasbrouck IS
  weekend.py      closure table + gap regressions (HC3), winsorised
  backtest.py     jump-following rule net of costs
  headlines.py    first-public-timestamp schema and PRE/SAME/POST classification
  synthetic.py    generator with known lead-lag for validation
scripts/
  build_events.py     clean events_raw.csv -> events.csv (fixes bad endDates)
  assign_signs.py     per-market escalation sign + per-asset hypothesis signs (sign_* cols)
  quick_weekend.py    fast closed-hours regressions + placebo + reverse check (~15 min)
  pull_polymarket.py  minute price history for every event (no auth)
  pull_databento.py   futures + equities minute bars (needs API key; --estimate first)
  pull_polygon.py     free ETF fallback (USO/ITA/LMT/RTX/GLD/TLT/SPY/XLE/VIXY)
  run_analysis.py     full battery per (market, asset); writes results/*.csv
tests/test_pipeline.py  13 tests on synthetic data
data/events_raw.csv     94 markets as fetched (Gamma API, Oct 17 2026)
data/events.csv         91 cleaned
```

## Setup

```
pip install -e .            # core
pip install -e ".[dev]"     # + pytest
pytest -q                   # should print 13 passed (~50 s)
```

## Getting the data (run on your own machine)

1. **Polymarket** (free, ~1-2 h):
   `python scripts/pull_polymarket.py data/events.csv data/raw/polymarket`
2. **Conventional assets**, one of:
   - DataBento (futures + equities): sign up, `pip install databento`,
     `python scripts/pull_databento.py 2024-01-01 2026-10-01 data/raw/databento --estimate`
     then rerun without `--estimate` if the printed cost fits the signup credit.
   - Massive (formerly Polygon.io) free tier (ETFs only, 2-year lookback, 5 req/min, ~25 min):
     `python scripts/pull_polygon.py 2024-10-01 2026-10-01 data/raw/polygon`
     Use ETF proxies (USO≈CL, GLD≈GC, TLT≈ZB, SPY≈ES, VIXY≈VX) and say so.
3. **Run:**
   `python scripts/run_analysis.py data/events.csv data/raw/polymarket data/raw/databento results/`
4. **Headline timestamps** (manual, ~3-4 h, the most important data step):
   for every jump in `results/jumps.csv` with |dp| ≥ 0.05, find the earliest
   public timestamp of the underlying news and fill `data/headlines.csv`
   (schema in `pmll/headlines.py`). Then split every table by
   PRE/SAME/POST. Without this, every result has a "same headline" rebuttal.

## Known biases and caveats (put these in the paper)

- **Quote staleness biases against PM leadership.** Polymarket quotes
  update only on trades; on thin books the detected jump minute lags the
  information minute by a few minutes, so some asset movement that is
  really post-information lands in the pre-window. Report `pm_stale` and
  repeat with `max_stale ∈ {5, 15, 30}`.
- **Timestamp noise.** Le (2026, arXiv 2602.19520) reports ~3 h timestamp
  noise in some Polymarket exports; the CLOB price-history endpoint used
  here is wall-clock, but verify on a few known events (e.g. Feb 28 2026
  Iran strikes at 06:15 UTC).
- **Wash trading.** ~25% of Polymarket volume may be wash (Columbia 2025).
  Price-history series are less affected than volume; don't use volume
  weights without filtering.
- **Hasbrouck information shares** need cointegrated levels; PM log-odds
  and asset log prices generally aren't. Report only on event segments
  where Johansen passes, or omit.
- **Mechanism.** A lead during closed hours on military markets may reflect
  insider flow rather than information aggregation (ACDC/Bloomberg cases).
  State this; do not attribute to wallets.
- **Multiple testing.** 79 markets × ~10 assets × several tests. Pool by
  category and report pooled statistics as primary; per-market tables are
  descriptive.
- **Ladder markets.** Many Iran markets are siblings ("by Jan N" rungs);
  treat each event cluster as one unit for inference, not 20.

## Event list notes

Built from the Gamma API via tag filters (geopolitics, tariffs, ukraine,
venezuela, oil). Volume-ranked paging without tags surfaces only
elections/sports. Gamma `endDate` is unreliable for short-dated ladders;
`build_events.py` re-parses it from the question. Likely-missing markets to
fetch by slug: 2024 Houthi/Red Sea, OPEC+ cuts, "Russia uses nuclear
weapon", North Korea, Liberation Day tariff markets, Trump-Putin summit,
Israel x Hamas ceasefire by Oct 10 2025 (the Gaza deal).

## Suggested venue

arXiv q-fin.TR preprint + public repo first (what internship recruiters
read), then ACM ICAIF 2027. Journal options: Finance Research Letters,
Economics Letters. Not an ML venue unless the jump-detection/nowcasting
component becomes the contribution.

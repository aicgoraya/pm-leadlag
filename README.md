# Do prediction markets lead conventional markets on geopolitical events?

Lead-lag study between Polymarket geopolitical/military contracts and oil
futures, defense equities, Treasuries, VIX and gold, at minute frequency.

**Status (2026-10-18):** full battery run on 91 Polymarket markets (81
geopolitical in 50 event clusters, 10 controls; minute resolution, coverage
median 99.7% of minutes quoted) and 9 ETFs at minute bars incl. extended hours
(Massive, Oct 2024 to Oct 2026). Pipeline validated on synthetic data (13/13
tests). Paper draft v0.2 in `paper/`.

## Results (full battery, 2026-10-18, 91 markets x 9 ETFs, per-market signs, artifact-filtered)

The four designs together tell one story: **Polymarket is not faster than oil
futures, it is open when they are closed.** Its informational edge over oil is
about trading hours, not speed, and it is not tradable at the open.

### 1. Closed-hours design (PM moves while ETF closed -> reopen gap)
Pooled over geopolitical markets, one row per event cluster per closure,
cluster-robust SE by closure, artifact closures removed (scripts/quick_weekend.py):

| asset | n | clusters | beta (log-ret per log-odds) | t | p |
|---|---|---|---|---|---|
| USO, 30 min | 2305 | 466 | 0.0111 | 4.06 | <1e-4 |
| XLE, 30 min | 2426 | 485 | 0.0047 | 3.75 | 0.0002 |
| VIXY, 30 min | 3345 | 478 | 0.0064 | 3.06 | 0.002 |
| USO, 1-min open gap | 2305 | 466 | 0.0107 | 4.09 | <1e-4 |
| USO, weekends only | 496 | 100 | 0.0075 | 2.63 | 0.009 |
| SPY, 30 min | 3152 | 450 | 0.0010 | 2.01 | 0.044 |
| TLT, GLD, ITA, LMT, RTX | | | ~0 | <1.4 | n.s. |

Oil driven by Iran (XLE t=3.7, USO t=3.6, 223 clusters) and Hormuz (USO t=3.9,
beta 0.028, 105 clusters) markets. VIXY driven by Venezuela markets (t=2.6).
Controls null on all assets (largest |t| 1.3). Shuffle placebo: oil and VIXY
null (|t|<1.8); largest placebo |t| across nine assets is 2.1 on ITA. Reverse
direction (asset pre-close -> PM closure move) null (|t|<1.6). Effect present
in the first minute of trading. Full tables: results/quick91/closure_tables.csv.

### 1b. Regular-hours robustness (ETF session 09:30-16:00 ET only)
Extended-hours bars dropped, so every overnight (~17.5 h) is a closure.
Dedup, clustered, artifact-filtered (results/quick91_rh/closure_tables.csv):

| asset | sample | n | clusters | beta | t | p |
|---|---|---|---|---|---|---|
| USO | all closures | 2204 | 445 | 0.0167 | 4.47 | <1e-4 |
| XLE | all closures | 2204 | 445 | 0.0055 | 3.97 | <1e-4 |
| VIXY | all closures | 3088 | 445 | 0.0073 | 2.66 | 0.008 |
| USO | overnight only | 1708 | 345 | 0.0186 | 3.47 | 0.0005 |
| XLE | overnight only | 1708 | 345 | 0.0069 | 3.41 | 0.0006 |
| USO | weekends only | 496 | 100 | 0.0090 | 2.61 | 0.009 |
| USO | controls | 1262 | 424 | 0.0001 | 0.02 | 0.98 |

Overnight and weekend closures replicate independently. Beta is larger than
under extended hours (0.017 vs 0.011) because pre-market trading absorbs part
of the gap before 09:30. TLT t = -2.4 under regular hours, -1.4 extended.

### 2. Event study (asset OPEN at the PM jump): who moves first?
Signed CAR in bp around PM jumps during ETF hours, Iran+oil markets (35 markets),
t across markets:

| | -15 min | -5 | +1 | +5 | +15 | +30 |
|---|---|---|---|---|---|---|
| USO bp | **41.7** | 19.6 | 2.5 | 5.5 | 8.6 | 12.0 |
| USO t | **6.3** | 5.3 | 1.6 | 2.0 | 2.3 | 3.2 |
| XLE bp | 9.6 | 4.9 | 0.9 | 3.7 | 5.2 | 8.5 |
| XLE t | 5.1 | 4.2 | 1.1 | 3.8 | 3.6 | 4.4 |

Oil has already moved 42 bp in the 15 minutes BEFORE the PM jump, vs 12 bp in
the 30 minutes after. During trading hours, **oil moves first and Polymarket
catches up**. Controls: pre-window ~0.

### 3. Granger / transfer entropy on overlap minutes (asset open, PM quote fresh)
Fraction of (market, asset) pairs significant at 5%, Iran+oil:

| asset | Granger PM->asset | Granger asset->PM | TE PM->asset | TE asset->PM | median xcorr peak lag |
|---|---|---|---|---|---|
| USO | 0.08 | **0.24** | 0.35 | **0.46** | **-3 min** (oil leads) |
| XLE | 0.14 | 0.22 | 0.35 | 0.19 | -2 |
| SPY | 0.05 | 0.19 | 0.35 | 0.27 | -4 |

Fisher-combined over 68 treated USO pairs: asset->PM p=1e-13 vs PM->asset p=0.06.
Consistent with the event study: in overlapping hours the causal arrow runs
oil -> Polymarket, at a 2-4 minute lag. (TE fractions are inflated by sparse
PM updates; Granger and xcorr are the cleaner read.)

### 4. Tradability
Rule: follow each closed-hours PM jump into USO at the next open, hold 30 min,
1 bp/side. Iran+oil, n=283: **mean -15 bp/trade, t=-2.4, hit rate 47%.**
Open-hours jumps, enter 1 min later: USO +7 bp, t=1.3, n.s. Larger jumps
(|dp|>=0.10) do not help (-20 bp, n=90). **Not tradable.** The reopen gap in
design 1 happens at the opening print; by the first tradable minute it is
priced and the next 30 min mean-revert.

### Interpretation (for the paper)
- When both venues trade, oil futures/ETFs impound geopolitical news 2-4 min
  before Polymarket. Polymarket is a follower in continuous time.
- When ETFs are closed (nights, weekends), Polymarket keeps pricing. The
  accumulated move predicts the reopen gap with t>4, but the gap is realized
  at the open and cannot be captured afterwards.
- Net: prediction-market prices are a *real-time nowcast of what oil will do
  at the open*, usable for risk/positioning before the open, not a signal to
  trade after it. This is the Aktug-Torul election-night observation
  generalized across 50 geopolitical event clusters and reversed in overlapping hours.
- Still open: whether closed-hours PM moves reflect public overnight news that
  oil couldn't trade on, or non-public information (the ACDC/Bloomberg
  insider cases). headlines_template.csv is the path; not done.

### What changed from the first pass
Category-level signs produced a spurious defense-stock result (RTX t=3.0)
because ceasefire and strike markets were coded the same direction. Per-market
signs (assign_signs.py) removed it and moved everything to oil. Keep signs per
market; review that file by hand.

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
  closure_tables.py   artifact filter, dedup, closed-hours tables used in the paper
  assign_signs.py     per-market escalation and asset signs into events.csv
  make_figures.py     paper figures from results/
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
3. **Run** (about 40 min each on two cores):
   ```
   python scripts/assign_signs.py data/events.csv
   python scripts/run_analysis.py data/events.csv data/raw/polymarket data/raw/polygon results/full
   python scripts/run_analysis.py data/events.csv data/raw/polymarket data/raw/polygon results/full_rh --regular-hours
   python scripts/quick_weekend.py data/events.csv data/raw/polymarket data/raw/polygon results/quick
   python scripts/closure_tables.py results/quick
   python scripts/quick_weekend.py data/events.csv data/raw/polymarket data/raw/polygon results/quick_rh --regular-hours
   python scripts/closure_tables.py results/quick_rh
   python scripts/make_figures.py results paper
   ```
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

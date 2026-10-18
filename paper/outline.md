# Open When Oil Is Closed: Prediction Markets and Geopolitical Price Discovery

Working outline. Target: arXiv q-fin.TR, then ACM ICAIF 2027.

## Abstract (draft)

Do prediction markets lead conventional financial markets on geopolitical
events? Using minute-level prices for 79 Polymarket contracts on US-Iran
conflict, the Strait of Hormuz, Russia-Ukraine, Israel, Taiwan and tariffs
(2024-2026) and minute bars for oil, energy, defense, Treasury, gold and
equity ETFs, we find the answer depends on whether both venues are open.
When US ETFs are closed, Polymarket's accumulated move on Iran and Hormuz
contracts predicts the oil ETF reopen gap (USO t=4.2, 466 closures; controls
null; shuffle placebo null). When both trade, the direction reverses: oil
moves 2-4 minutes before Polymarket (event-study pre-window t=6.3; Granger
oil->PM in 24% of pairs vs 8% reverse). The reopen gap is realized at the
opening print and a jump-following rule loses 15 bp per trade. Prediction
markets are not faster than oil futures; they are open when oil futures are
not. We reconcile the election-night lead reported by Aktug and Torul (2026)
with the weak daily transmission in Azqueta-Gavaldón and Ureta (2026): the
lead is a trading-hours effect, and the transmission is concentrated in the
first minute after the open.

## 1. Introduction

- Motivation: $54B settled on Polymarket; Iran war 2026 made geopolitical
  contracts the most liquid non-election markets; Bloomberg/ACDC insider
  cases on military markets. Question: is this information reaching
  conventional markets first?
- Prior claim: Aktug & Torul (2026) "prediction markets incorporate political
  information ahead of deep, professionally arbitraged financial markets."
  Evidence: one election night, milestone timing vs ES (15-225 min lead),
  two weekend shocks (ES gaps 0.07%, 0.12%), DJT overnight beta 0.36 on 45
  sessions. Descriptive; no inferential lead-lag; single event.
- Prior null: Azqueta-Gavaldón & Ureta (2026) OSINT geopolitical index ->
  energy equities, daily SVAR, "statistically weak". Suggests any effect is
  sub-daily.
- Our contribution: (i) 79 contracts, ~40 distinct geopolitical events, 466
  venue closures; (ii) four designs that separate closed-hours from
  open-hours; (iii) the direction reverses between them; (iv) economic
  significance via backtest.
- One-paragraph result.

## 2. Data

- 2.1 Polymarket: Gamma metadata, CLOB minute price history (fidelity=1),
  91 contracts (79 geopolitical, 12 controls), coverage median 99.7% of
  minutes quoted. Per-market escalation sign (Table A1). Ladder siblings and
  event clusters. Artifacts: 2025-12-27 01:01 UTC book reset (13 contracts
  at 0.50), filter rule.
- 2.2 ETFs: Massive minute bars incl. extended hours 04:00-20:00 ET, Oct 2024
  to Oct 2026: USO, XLE, ITA, LMT, RTX, GLD, TLT, SPY, VIXY. Empirical open
  mask. Regular-hours robustness.
- 2.3 Hypothesised asset response per contract (escalation x template).
- 2.4 Summary stats: jumps per category, fraction during closed hours
  (Table 1).

## 3. Designs

- 3.1 Closed-hours gap: y_c = signed reopen return, x_c = PM log-odds change
  over closure; OLS with closure-clustered SE; pre-closure PM move control;
  dedup to one row per event cluster per closure; winsorised x.
- 3.2 Event study around PM jumps during open hours: Lee-Mykland (floored
  sigma) + threshold; signed CAR at -15..+60; placebo from random open
  minutes; pre-window as the "who moved first" diagnostic.
- 3.3 Granger (HAC Wald) and transfer entropy (surrogate p) on overlap
  minutes; cross-correlation peak lag.
- 3.4 Tradability: jump-following rule, 30-min hold, 1 bp/side.
- 3.5 Validation on synthetic data with known lead-lag (Appendix B; 13 tests).

## 4. Results

- 4.1 Closed hours: Table 2 (pooled per asset), Table 3 (by category), Fig 1
  (binned scatter USO reopen gap vs PM closure move, Iran+Hormuz).
- 4.2 Placebo and reverse checks: Table 4.
- 4.3 Open hours: Table 5 (CAR profile), Fig 2 (CAR path -15..+60 USO/XLE
  with placebo band). Pre-window dominates.
- 4.4 Granger/TE: Table 6. Asymmetry oil->PM.
- 4.5 Tradability: Table 7. Negative.
- 4.6 Robustness: regular hours only; weekends only; |dp| thresholds;
  max_stale in {5,15,30}; drop 2026 Iran war months; drop artifact minutes.
- 4.7 Heterogeneity: which categories. Only oil-relevant contracts move oil;
  nothing moves defense once signs are per-market (contrast with naive
  category-sign result, Appendix C: a cautionary tale).

## 5. Interpretation

- Trading-hours asymmetry, not speed. PM as overnight nowcast.
- Why no tradable edge: gap at the open print; ETF market makers read
  Polymarket too (anecdotal; cite press).
- Mechanism caveat: closed-hours PM moves could be public overnight news or
  non-public information. Headline-timestamp classification (PRE/SAME/POST)
  on the N largest closed-hours jumps [TODO]. We do not attribute to wallets.
- Quote-staleness bias: jump minute lags information minute on thin books;
  biases against PM leadership in open hours; strengthens closed-hours result.

## 6. Related work

Aktug & Torul 2026; Ng, Peng, Tao, Zhou 2026 (PM vs PM); Gómez-Cram et al.
2026 (EPS contracts lead analyst revisions); Leigh, Wolfers, Zitzewitz 2003
and Snowberg et al. 2007 (ancestors, daily); Azqueta-Gavaldón & Ureta 2026
(OSINT, weak daily); Mitts & Ofir 2026 and ACDC 2026 (insider evidence on
military markets); Qin & Yang 2026 (on-chain database); Le 2026
(calibration, timestamp noise); Hasbrouck 1995, Putnins 2013 (methods).

## 7. Conclusion

## Appendix

- A. Contract list with escalation signs and asset signs.
- B. Synthetic validation.
- C. The category-sign artifact.
- D. Data artifacts and filters.
- E. Full per-category tables.

## Figures to make
1. Binned scatter: USO 30-min reopen return vs PM closure log-odds move,
   Iran+Hormuz, with fitted line and CI.
2. CAR path -15..+60 min for USO and XLE, treated vs control, placebo band.
3. Histogram of xcorr peak lag for USO pairs (mass at -3).
4. One case study: a weekend with a large Hormuz move and the Monday USO open.
5. Timeline of jumps per week with the Iran war shaded.

## Numbers still needed
- Regular-hours-only run (in progress).
- Count of distinct event clusters (currently 49 incl. controls).
- Headline classification counts.

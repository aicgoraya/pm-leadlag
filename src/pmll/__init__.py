"""pmll: prediction-market lead-lag toolkit.

Modules
-------
calendar     CME / NYSE session calendar and 24/7 -> exchange-hours mapping
polymarket   Polymarket CLOB price-history loader (minute resolution)
assets       Conventional-asset minute-bar loader (DataBento / CSV) and returns
align        Align Polymarket series to asset bars on a common UTC minute grid
jumps        Jump detection on Polymarket probability series
eventstudy   Event-study CARs around Polymarket jumps
leadlag      Granger causality, transfer entropy, Hasbrouck information share
weekend      Closed-hours design: Monday open gap vs accumulated PM move
backtest     Tradability check net of costs
"""

__version__ = "0.1.0"

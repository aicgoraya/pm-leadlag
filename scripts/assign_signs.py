#!/usr/bin/env python3
"""Assign a per-market escalation sign and per-asset hypothesis signs.

Each market gets `escalation` in {+1, -1, 0}:
  +1  YES = more conflict / supply disruption / risk (strikes, invasion, Hormuz closed,
      tariffs imposed, sanctions, nuclear, military engagement, regime fall)
  -1  YES = de-escalation / resolution (ceasefire, peace deal, traffic returns to
      normal, tariffs lowered, trade deal, LNG resumes)
   0  unclear / control -> all assets get +1 (expect null)

Asset response to +1 escalation (risk-on/off template):
  risk assets  SPY -1
  oil          USO +1, XLE +1   (but see oil-specific below)
  defense      ITA +1, LMT +1, RTX +1
  safe havens  GLD +1, TLT +1
  vol          VIXY +1
Asset sign = escalation * template, written as columns sign_<ASSET> in events.csv.

Category tweaks:
  russia_ukraine escalation: oil +1 (Russia supply risk), defense +1, SPY -1.
  tariffs: "escalation" = tariffs imposed/upheld -> SPY -1, TLT +1, GLD +1; oil/defense 0.
  oil price-threshold markets ("CL hit $100"): YES = oil up -> USO/XLE +1, SPY -1, others 0.
  china_taiwan: defense +1, SPY -1, GLD/TLT +1, oil 0.

Manual overrides at the bottom for wording the regex gets wrong. Review the
printed table before trusting it; this is the single most assumption-laden
file in the project.

Usage: python scripts/assign_signs.py data/events.csv
(rewrites events.csv in place with escalation + sign_* columns)
"""
import re
import sys

import pandas as pd

ASSETS = ["SPY", "USO", "XLE", "ITA", "LMT", "RTX", "GLD", "TLT", "VIXY"]
TEMPLATE = {"SPY": -1, "USO": +1, "XLE": +1, "ITA": +1, "LMT": +1, "RTX": +1,
            "GLD": +1, "TLT": +1, "VIXY": +1}

DEESC = r"ceasefire|peace deal|ends? (the )?(ukraine )?war|returns? to normal|reopen|resumes?|lower(s)? tariffs|trade deal|nuclear deal|meeting|announces end of military|agrees to end enrichment|ceasefire extended|ceasefire continue|lebanon ceasefire extension"
ESC = r"strike|strikes|invade|invasion|military action|military engagement|forces enter|attack|detonate|nuclear weapon|sanctions|tariff|custody|out in|out by|regime|khamenei|fordow|kharg|closes|close|blockade|100% tariff|40% tariff|large tariffs|ground operation|anti-cartel|houthi"


def escalation(q: str) -> int:
    ql = q.lower()
    if re.search(DEESC, ql):
        return -1
    if re.search(ESC, ql):
        return +1
    return 0


def signs_for(row) -> dict:
    cat, q = row["category"], row["question"].lower()
    e = int(row["escalation"])
    if cat == "control" or e == 0:
        return {a: +1 for a in ASSETS}
    s = {a: e * TEMPLATE[a] for a in ASSETS}
    if cat == "tariffs":
        s["USO"] = s["XLE"] = s["ITA"] = s["LMT"] = s["RTX"] = 0
    if cat == "china_taiwan":
        s["USO"] = s["XLE"] = 0
    if cat == "oil" and re.search(r"crude oil|\(cl\)", q):
        # price threshold market: YES = oil up
        s = {a: 0 for a in ASSETS}
        s.update({"USO": +1, "XLE": +1, "SPY": -1})
    return s


OVERRIDES = {
    # question substring (lowercase) -> escalation
    "will trump lower tariffs on china": -1,
    "supreme court rules in favor of trump's tariffs": +1,
    "us-china trade deal": -1,
    "xi jinping out": 0,          # ambiguous for markets
    "will a nuclear weapon detonate": +1,
    "maduro out": +1,             # regime change via US pressure -> risk/oil up
    "maduro in u.s. custody": +1,
    "qatarenergy announces/resumes lng": -1,
    "will trump impose more sanctions on russia": +1,
    "military action against iran ends": -1,
    "conflict ends by": -1,
    "officially declare war on iran": +1,
    "israel military response against iran": +1,
    "us obtains iranian enriched uranium": -1,
    "major cyberattack on iran": +1,
}


def main(path):
    ev = pd.read_csv(path)
    ev["escalation"] = ev["question"].map(escalation)
    for k, v in OVERRIDES.items():
        m = ev["question"].str.lower().str.contains(re.escape(k))
        ev.loc[m, "escalation"] = v
    sg = ev.apply(signs_for, axis=1, result_type="expand")
    for a in ASSETS:
        ev[f"sign_{a}"] = sg[a].astype(int)
    ev.to_csv(path, index=False)
    pd.set_option("display.width", 200)
    print(ev[["category", "escalation", "question"]].sort_values(["category", "escalation"]).to_string(index=False))
    print("\nescalation counts:", ev.groupby("category")["escalation"].value_counts().to_dict())


if __name__ == "__main__":
    main(sys.argv[1])

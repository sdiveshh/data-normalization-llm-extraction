"""Final safety checks on the output table. Returns a list of problem strings."""
import re
from typing import Dict, List

from schema import COLUMNS, NEW_LINE, UPGRADE

MONEY_RE = re.compile(r"^\$\d+(\.\d{2})?$")
MONEY_COLS = ["BASE", "MSRP", "RESELLER LIST PRICE", "SWITCHER", "UNIQUE DISCOUNT",
              "Max TI (Maximum Trade-In Value)", "PWP/GWP OFFER $ VALUE", "SERVICE LINE OFFER $ VALUE",
              "FINANCE OFFER $ VALUE", "SUBSCRIPTION BUNDLE OFFER $ VALUE", "ADDITIONAL OFFER $ VALUE"]
BAD = {"n/a", "na", "null", "none", "0", "-", "$0"}
LT = "LINE TYPE (e.g., New Line vs. Upgrade)"
NEW_ONLY = ["SWITCHER", "SWITCHER_OFFER_TEXT", "SERVICE LINE OFFERS", "SERVICE LINE OFFER $ VALUE", "RESELLER LIST PRICE"]


def validate(rows: List[Dict], n_products: int) -> List[str]:
    errs = []
    if len(rows) != 2 * n_products:
        errs.append(f"row count {len(rows)} != 2 x {n_products}")
    for i, r in enumerate(rows):
        if list(r.keys()) != COLUMNS:
            errs.append(f"row {i}: columns differ from spec")
        for c in MONEY_COLS:
            v = r.get(c)
            if v not in (None, "") and not MONEY_RE.match(v):
                errs.append(f"row {i}: bad money format in {c}: {v!r}")
        for c, v in r.items():
            if isinstance(v, str) and v.strip().lower() in BAD:
                errs.append(f"row {i}: placeholder value in {c}: {v!r}")
        if r[LT] == UPGRADE:
            for c in NEW_ONLY:
                if r.get(c):
                    errs.append(f"row {i}: Upgrade row has new-line-only field {c}")
    for i in range(0, len(rows) - 1, 2):
        if (rows[i][LT], rows[i + 1][LT]) != (NEW_LINE, UPGRADE):
            errs.append(f"rows {i},{i+1}: expected New Line then Upgrade")
    return errs

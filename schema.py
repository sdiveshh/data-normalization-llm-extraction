"""Shared constants and the intermediate `Facts` record.

Pipeline:  raw JSON --(extractor)--> Facts --(rows.build_rows)--> 2 CSV rows
The extractor (rules or LLM) only *finds* values in the text. Line-type gating,
money formatting and validation always happen afterwards in plain Python.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional

NEW_LINE = "New Line"
UPGRADE = "Upgrade"
LINE_TYPES = (NEW_LINE, UPGRADE)

# Exact headers from the assignment, in order. Do not rename.
COLUMNS = [
    "PLAN TYPE", "PRODUCT NAME", "BRAND", "VARIANT", "BASE", "MSRP",
    "RESELLER LIST PRICE", "SWITCHER", "SWITCHER_OFFER_TEXT", "UNIQUE DISCOUNT",
    "FREE MEMORY UPGRADE", "BOGO OFFER", "Max TI (Maximum Trade-In Value)",
    "Trade-In Value Type (Enhanced/ Base)", "LINE TYPE (e.g., New Line vs. Upgrade)",
    "RATEPLAN DURATION (MONTHS)", "SHIPMENT", "STOCK", "PWP/GWP OFFERS",
    "Cleaned PWP/GWP OFFERS", "PWP/GWP OFFER $ VALUE", "SUBSCRIPTION BUNDLE OFFERS",
    "SUBSCRIPTION BUNDLE OFFER $ VALUE", "SERVICE LINE OFFERS",
    "SERVICE LINE OFFER $ VALUE", "ADDITIONAL OFFERS", "ADDITIONAL OFFER $ VALUE",
    "FINANCE OFFER DESCRIPTION 1", "FINANCE OFFER $ VALUE",
]


@dataclass
class Facts:
    """Everything found in the source text for ONE product. Amounts are plain
    numeric strings exactly as written in the source ("660.36", "800")."""
    base_monthly: Optional[str] = None
    base_new_line_only: bool = False
    device_credit: Optional[str] = None          # -> UNIQUE DISCOUNT
    device_credit_new_line_only: bool = True
    service_line_amount: Optional[str] = None
    service_line_text: Optional[str] = None
    switcher_amount: Optional[str] = None
    switcher_text: Optional[str] = None
    trade_in_max: Optional[str] = None
    trade_in_type: Optional[str] = None          # "Enhanced" | "Base"
    reseller_price: Optional[str] = None
    finance_welcome: Optional[str] = None        # one-time -> New Line only
    finance_recurring: Optional[str] = None
    finance_bill_discount: Optional[str] = None
    rateplan_months: Optional[str] = None
    pwp: List[dict] = field(default_factory=list)  # {"name","now","was"}

    def to_dict(self):
        return asdict(self)

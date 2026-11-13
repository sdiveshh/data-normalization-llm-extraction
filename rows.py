"""Turns Facts into exactly two CSV rows (New Line / Upgrade) for one product.
All line-type eligibility rules live here, in one place."""
from decimal import Decimal
from typing import Dict, List, Optional

from schema import COLUMNS, LINE_TYPES, NEW_LINE, UPGRADE, Facts


def money(*amounts: Optional[str]) -> Optional[str]:
    """'$' + exact digits. Decimals are kept (two places) if ANY source amount had a
    decimal point; whole-dollar sources ('800') stay '$800'. Never rounds."""
    vals = [a for a in amounts if a not in (None, "")]
    if not vals:
        return None
    total = sum((Decimal(v) for v in vals), Decimal(0))
    if any("." in v for v in vals):
        return f"${total.quantize(Decimal('0.01'))}"
    return f"${int(total)}"


def finance_row(f: Facts, line: str):
    """New Line: welcome bonus + recurring + bill discount. Upgrade: recurring + bill
    discount only (one-time acquisition bonus excluded). Spend requirements ignored."""
    welcome = f.finance_welcome if line == NEW_LINE else None
    if not any([welcome, f.finance_recurring, f.finance_bill_discount]):
        return None, None
    parts = []
    if welcome:
        parts.append(f"Earn a {money(welcome)} statement credit after qualifying purchases welcome bonus")
    if f.finance_recurring:
        lead = "plus up to" if welcome else "Get up to"
        parts.append(f"{lead} {money(f.finance_recurring)} back every year with the AT&T Points Plus\u00ae Card from Citi")
    if f.finance_bill_discount:
        parts.append(f"{'and ' if parts else ''}{money(f.finance_bill_discount)} discounts on your AT&T bills")
    return " ".join(parts), money(welcome, f.finance_recurring, f.finance_bill_discount)


def build_rows(product: dict, f: Facts) -> List[Dict[str, Optional[str]]]:
    rows = []
    for line in LINE_TYPES:
        new = line == NEW_LINE
        r = {c: None for c in COLUMNS}
        r["PLAN TYPE"] = product.get("plan_type")
        r["PRODUCT NAME"] = product.get("product_name")
        r["BRAND"] = product.get("brand")
        r["VARIANT"] = product.get("variant")
        r["MSRP"] = money((product.get("pricing") or {}).get("retail"))
        r["LINE TYPE (e.g., New Line vs. Upgrade)"] = line
        r["SHIPMENT"] = product.get("shipment")
        r["STOCK"] = product.get("stock")
        r["RATEPLAN DURATION (MONTHS)"] = f.rateplan_months

        if f.base_monthly and (new or not f.base_new_line_only):
            r["BASE"] = money(f.base_monthly)
        if new and f.reseller_price:
            r["RESELLER LIST PRICE"] = money(f.reseller_price)
        if new and f.switcher_amount:                       # port-in = new lines only
            r["SWITCHER"] = money(f.switcher_amount)
            r["SWITCHER_OFFER_TEXT"] = f.switcher_text
        if f.device_credit and (new or not f.device_credit_new_line_only):
            r["UNIQUE DISCOUNT"] = money(f.device_credit)
        if new and f.service_line_amount:
            r["SERVICE LINE OFFERS"] = f.service_line_text
            r["SERVICE LINE OFFER $ VALUE"] = money(f.service_line_amount)
        if f.trade_in_max:
            r["Max TI (Maximum Trade-In Value)"] = money(f.trade_in_max)
            r["Trade-In Value Type (Enhanced/ Base)"] = f.trade_in_type
        if f.pwp:
            r["PWP/GWP OFFERS"] = " | ".join(f"{p['name']}: Was {money(p['was'])}. Now {money(p['now'])}." for p in f.pwp)
            r["Cleaned PWP/GWP OFFERS"] = " | ".join(f"{p['name']} for {money(p['now'])} (was {money(p['was'])})" for p in f.pwp)
            r["PWP/GWP OFFER $ VALUE"] = money(*[str(Decimal(p["was"]) - Decimal(p["now"])) for p in f.pwp])
        r["FINANCE OFFER DESCRIPTION 1"], r["FINANCE OFFER $ VALUE"] = finance_row(f, line)
        rows.append(r)
    return rows

"""Deterministic (regex) extractor. This is the baseline and the safety net
for the LLM extractor: it never guesses, it only returns what the text says."""
import re
from typing import Iterable, List, Optional

from schema import Facts

AMT = r"\$\s?([\d,]+(?:\.\d+)?)"


def norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def clean_amount(s: str) -> str:
    return s.replace(",", "").strip()


def variant_token(variant: str) -> str:
    return re.sub(r"\s+", "", variant or "")          # "1 TB" -> "1TB"


def short_name(product: dict) -> str:
    name, brand = product.get("product_name", ""), product.get("brand", "")
    return norm(name[len(brand):] if brand and name.startswith(brand) else name)


def short_fields(offer: dict) -> List[str]:
    """Headline-level text only (no long legal 'full_details' blobs, which list
    tiers for OTHER models)."""
    fd = offer.get("full_details") or {}
    out = [offer.get("title"), offer.get("description"), offer.get("raw"), fd.get("modal_raw_text")]
    for c in fd.get("cards") or []:
        out += [c.get("title"), c.get("description"), c.get("legal")]
    return [norm(x) for x in out if x]


def detail_blocks(offer: dict) -> List[str]:
    """Long 'Offer Details' texts (where per-variant discount lists live)."""
    fd = offer.get("full_details") or {}
    out = [fd.get("modal_raw_text")]
    for c in fd.get("cards") or []:
        out.append((c.get("full_details") or {}).get("raw_text"))
    out.append((fd.get("modal_full_details") or {}).get("raw_text"))
    seen, res = set(), []
    for x in out:
        x = norm(x)
        if x and x not in seen:
            seen.add(x); res.append(x)
    return res


def all_text(product: dict) -> List[str]:
    res = []
    for o in product.get("offers") or []:
        res += short_fields(o) + detail_blocks(o)
    res += [norm(x) for x in (product.get("pricing") or {}).get("options", [])]
    return res


# ---------------------------------------------------------------- individual finders
def find_device_credit(product, offers):
    """'iPhone 17 Pro Max 1TB for $21.43/mo ... after up to $628.36 in bill credits'.
    Anchored on exact model + exact variant so a 256GB figure can never leak into a 1TB row."""
    name, vt = re.escape(short_name(product)), re.escape(variant_token(product["variant"]))
    pat = re.compile(
        rf"(?<![\w]){name}\s+{vt}\s+for\s+\$[\d.,]+(?:/mo\.)?"
        rf"(?:(?!\d+\s?(?:GB|TB)\s+for).){{0,200}}?after up to {AMT} in bill credits", re.I)
    for o in offers:
        for blk in detail_blocks(o):
            m = pat.search(blk)
            if m:
                elig = re.search(r"Eligibility:\s*(.*?)\.\s", blk)
                e = (elig.group(1).lower() if elig else "")
                new_only = not ("existing" in e or "upgrad" in e) or not e
                return clean_amount(m.group(1)), new_only
    return None, True


def find_switcher(offers):
    for o in offers:
        title = norm(o.get("title"))
        m = re.search(rf"up to {AMT}\s*/\s*line", title, re.I)
        blob = " ".join(short_fields(o)).lower()
        if m and "switch" in blob:
            desc = norm(o.get("description"))
            tail = re.sub(r"^Learn how to\s+", "", desc, flags=re.I).rstrip(".")
            text = f"Get up to ${clean_amount(m.group(1))}/line when you {tail}." if tail else title
            return clean_amount(m.group(1)), text
    return None, None


def find_service_line(offers):
    """$200 'additional credit / off a new line'. The $5.56/mo figure is the SAME $200
    spread over 36 months, so only the $200 is reported (never summed)."""
    for o in offers:
        for f in short_fields(o):
            m = re.search(rf"Price after additional {AMT} in credits", f, re.I)
            if m:
                a = clean_amount(m.group(1))
                return a, f"Price after additional ${a} in credits."
    for o in offers:
        title = norm(o.get("title"))
        m = re.search(rf"Get {AMT} off a new line", title, re.I)
        if m:
            return clean_amount(m.group(1)), title
    return None, None


def find_trade_in(offers):
    """Needs an explicit 'Up to $X off' that sits next to the word trade-in."""
    for o in offers:
        for f in short_fields(o):
            for m in re.finditer(rf"up to {AMT} off", f, re.I):
                window = f[max(0, m.start() - 250): m.end() + 250].lower()
                if "trade-in" in window or "trade in" in window:
                    # Enhanced = carrier-funded promo credit (bill credits / any-condition);
                    # judged on the whole offer headline, not one field.
                    blob = " ".join(short_fields(o)).lower()
                    enhanced = any(k in blob for k in ("any condition", "bill credit", "monthly credit"))
                    return clean_amount(m.group(1)), "Enhanced" if enhanced else "Base"
    return None, None


def find_reseller_price(product, offers):
    """'Get iPhone 17e 256GB for $0 ... Price is $0.99/mo. for retailer partner...'
    Only valid when the headline variant equals THIS row's variant."""
    name, vt = short_name(product), variant_token(product["variant"])
    for o in offers:
        title = norm(o.get("title"))
        t = re.match(r"Get (?P<n>.+?)\s+(?P<v>\d+\s?(?:GB|TB))\s+for\b", title, re.I)
        if not t or norm(t.group("n")).lower() != name.lower() or variant_token(t.group("v")).lower() != vt.lower():
            continue
        m = re.search(rf"Price is {AMT}\s*/mo\.? for retailer partner", norm(o.get("description")), re.I)
        if m:
            return clean_amount(m.group(1))
    return None


def find_finance(product):
    blocks = all_text(product)
    cit = [b for b in blocks if "Points Plus" in b]
    w = r_ = b_ = None
    for b in cit:
        w = w or re.search(rf"{AMT} statement credit after spending", b)
        r_ = r_ or re.search(rf"up to {AMT} in statement credits every year", b, re.I)
        b_ = b_ or re.search(rf"Earn {AMT} discounts on your AT&T bills", b, re.I)
    g = lambda m: clean_amount(m.group(1)) if m else None
    return g(w), g(r_), g(b_)


def find_rateplan(product):
    txt = " ".join(all_text(product))
    m = re.search(r"0% APR (\d+)[- ]mo", txt, re.I) or re.search(r"over (\d+) mos", txt, re.I)
    return m.group(1) if m else None


def find_pwp(product) -> List[dict]:
    out = []
    for a in product.get("accessories_offers") or []:
        p = a.get("pricing") or {}
        now, was = p.get("current_price"), p.get("original_price")
        if now and was:
            mn, mw = re.search(AMT, now), re.search(AMT, was)
            if mn and mw:
                out.append({"name": norm(a.get("title")), "now": clean_amount(mn.group(1)),
                            "was": clean_amount(mw.group(1))})
    return out


# ---------------------------------------------------------------- entry point
def extract_facts(product: dict) -> Facts:
    offers = product.get("offers") or []
    f = Facts()
    opts = (product.get("pricing") or {}).get("options") or []
    if (product.get("pricing") or {}).get("monthly") not in (None, ""):
        f.base_monthly = str(product["pricing"]["monthly"])
        f.base_new_line_only = any("requires new line" in o.lower() for o in opts)
    f.device_credit, f.device_credit_new_line_only = find_device_credit(product, offers)
    f.switcher_amount, f.switcher_text = find_switcher(offers)
    f.service_line_amount, f.service_line_text = find_service_line(offers)
    f.trade_in_max, f.trade_in_type = find_trade_in(offers)
    f.reseller_price = find_reseller_price(product, offers)
    f.finance_welcome, f.finance_recurring, f.finance_bill_discount = find_finance(product)
    f.rateplan_months = find_rateplan(product)
    f.pwp = find_pwp(product)
    return f

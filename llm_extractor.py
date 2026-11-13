"""OPTIONAL LLM extractor (python main.py --mode llm). Needs ANTHROPIC_API_KEY.

The LLM only *reads* the offer text and returns JSON. Every value it returns must
(1) quote an evidence snippet that really exists in the source text and
(2) contain the amount inside that snippet. Anything else is dropped and the
deterministic rules value is used instead (hallucination guard). Gating by line
type and money formatting are NOT done by the LLM - see rows.py."""
import json
import os
import re
import time
from typing import Callable, Optional

from rules_extractor import all_text, extract_facts, norm, short_name, variant_token
from schema import Facts

SYSTEM = """You extract promotional facts from scraped retailer text. Rules:
- Use ONLY the text provided. Never use outside knowledge, never guess, never round.
- Only use figures that belong to the exact product and exact storage variant given.
- Return ONLY one JSON object, no markdown, no commentary.
Schema (use null when absent):
{"device_credit":{"amount":"660.36","evidence":"<exact substring>"},
 "service_line":{"amount":"200","evidence":"<exact substring>"},
 "switcher":{"amount":"800","evidence":"<exact substring>"},
 "trade_in_max":{"amount":"930","evidence":"<exact substring>"},
 "reseller_price":{"amount":"14.99","evidence":"<exact substring>"}}
"amount" = digits only (no $ or commas). "evidence" must be copied verbatim."""


def build_prompt(product: dict, text: str) -> str:
    return (f"Product: {product['product_name']}\nVariant: {product['variant']}\n"
            f"Extract the five fields for THIS product and THIS variant only.\n\nTEXT:\n{text}")


def default_client(system: str, user: str, timeout: float = 60.0) -> str:
    import anthropic                                   # pip install anthropic
    c = anthropic.Anthropic(timeout=timeout)
    msg = c.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                            max_tokens=1000, system=system,
                            messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def parse_json(raw: str) -> Optional[dict]:
    """Tolerates ```json fences and chatter around the object."""
    raw = re.sub(r"```(?:json)?", "", raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def grounded(field: Optional[dict], source: str) -> Optional[str]:
    """Return the amount only if evidence is in the source AND contains the amount."""
    if not isinstance(field, dict):
        return None
    amt, ev = str(field.get("amount") or "").replace(",", "").strip(), norm(field.get("evidence"))
    if not amt or not ev or not re.fullmatch(r"\d+(\.\d+)?", amt):
        return None
    if ev in source and amt in ev.replace(",", ""):
        return amt
    return None


def extract_facts_llm(product: dict, client: Callable = default_client, retries: int = 2, log=print) -> Facts:
    base = extract_facts(product)                       # rules = structure + fallback
    source = norm(" ".join(all_text(product)))
    data = None
    for attempt in range(retries + 1):
        try:
            data = parse_json(client(SYSTEM, build_prompt(product, source[:60000])))
            if data is not None:
                break
        except Exception as e:                          # timeout / API error
            log(f"LLM error ({attempt+1}/{retries+1}): {e}")
            time.sleep(2 ** attempt)
    if data is None:
        log("LLM unusable -> using rules result")
        return base
    for key, attr in [("device_credit", "device_credit"), ("service_line", "service_line_amount"),
                      ("switcher", "switcher_amount"), ("trade_in_max", "trade_in_max"),
                      ("reseller_price", "reseller_price")]:
        val = grounded(data.get(key), source)
        rules_val = getattr(base, attr)
        if val is None and data.get(key):
            log(f"{product['variant']}: dropped ungrounded LLM {key}")
        if val and rules_val and val != rules_val:
            log(f"{product['product_name']} {product['variant']}: LLM {key}={val} != rules {rules_val} (keeping rules)")
            continue
        if val and not rules_val:
            setattr(base, attr, val)
    return base

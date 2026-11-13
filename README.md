# Data Normalization & LLM Extraction

Turns the scraped retailer JSON (`Input.json`, 12 products) into one CSV with **exactly two rows per product** (New Line, Upgrade) and the 29 required columns.

## Run it (3 commands)
```bash
python main.py --input Input.json --output output/output.csv    # no installs needed
python -m unittest discover -s tests -v                          # 7 tests
# optional LLM extractor (needs a key):
pip install anthropic && export ANTHROPIC_API_KEY=... && python main.py --mode llm
```
Result: `output/output.csv` (24 rows). Exit code is 1 if any validation check fails.

## How it works
`Input.json -> extractor (rules | llm) -> Facts -> rows.py (line-type rules + money format) -> validate.py -> CSV`

| File | Job |
|---|---|
| `schema.py` | exact column list, `Facts` record |
| `rules_extractor.py` | regex extraction, anchored to exact model + variant |
| `llm_extractor.py` | optional LLM reader with evidence-grounding guard + fallback to rules |
| `rows.py` | New Line vs Upgrade eligibility, money formatting, 2-row multiplication |
| `validate.py` | row count, headers, `$x.xx` format, no placeholders, new-line-only leaks |
| `main.py` | CLI, per-record error isolation |

## Rules applied
- **Variant anchoring**: a discount is used only if the text names this exact model + storage (the 1 TB row never receives the 256 GB figure).
- **New Line only**: switcher, service-line credit, reseller price, device bill credits (text says "New customers activating new line"). **Both**: trade-in, Citi recurring benefits, accessories.
- **Finance**: New = welcome + yearly + bill discount; Upgrade = yearly + bill discount. Spend thresholds ignored.
- **Money**: `$` + source digits, no rounding, no thousands separator (`$1200`, `$660.36`). Missing = blank cell.
- **Non-duplication**: the `$5.56/mo` credit is the same `$200`; only `$200` is reported, never summed.

## Assumptions (please sanity-check against your answer key)
1. `BASE` = scraped monthly installment price; blank on Upgrade rows when the page says it requires a new line.
2. `Trade-In Value Type` = `Enhanced` when the offer is a carrier promo credit (bill credits / any condition), else `Base`.
3. `PWP/GWP OFFER $ VALUE` = was-price minus now-price of discounted accessories (AirPods 4 ANC: $30.00).
4. `RESELLER LIST PRICE` only when the offer headline names the row's own variant; the iPhone 17e text gives two different reseller prices ($0.99/mo vs $6.99), the description value is used.
5. No BOGO, memory-upgrade or subscription text exists in this input, and add-on items carry no `offer_text`, so those columns are blank.

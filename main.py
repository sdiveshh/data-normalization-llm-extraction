"""Usage: python main.py --input Input.json --output output/output.csv [--mode rules|llm]"""
import argparse
import csv
import json
import logging
import os
import sys

from rows import build_rows
from rules_extractor import extract_facts
from schema import COLUMNS, Facts
from validate import validate

log = logging.getLogger("normalizer")


def load_products(path: str):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):                       # tolerate {"products":[...]}
        data = next((v for v in data.values() if isinstance(v, list)), [data])
    if not isinstance(data, list):
        raise ValueError("Input JSON must be an array of product objects")
    return data


def run(input_path: str, output_path: str, mode: str = "rules"):
    extractor = extract_facts
    if mode == "llm":
        from llm_extractor import extract_facts_llm as extractor
    products, rows = load_products(input_path), []
    for i, p in enumerate(products):
        try:
            facts = extractor(p)
        except Exception as e:                       # one bad record must not kill the run
            log.error("product %d (%s) failed: %s - emitting base-only rows", i, p.get("product_name"), e)
            facts = Facts()
        rows += build_rows(p if isinstance(p, dict) else {}, facts)
    problems = validate(rows, len(products))
    for pr in problems:
        log.warning("VALIDATION: %s", pr)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="raise")
        w.writeheader()
        w.writerows({k: ("" if v is None else v) for k, v in r.items()} for r in rows)
    log.info("%d products -> %d rows -> %s", len(products), len(rows), output_path)
    return rows, problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="Input.json")
    ap.add_argument("--output", default="output/output.csv")
    ap.add_argument("--mode", choices=["rules", "llm"], default="rules")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _, probs = run(a.input, a.output, a.mode)
    sys.exit(1 if probs else 0)

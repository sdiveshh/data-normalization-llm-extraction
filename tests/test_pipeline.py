import copy, json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from llm_extractor import extract_facts_llm, parse_json
from rows import build_rows, money
from rules_extractor import extract_facts
from schema import COLUMNS
from validate import validate

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "..", "Input.json"), encoding="utf-8"))


def rows_for(p):
    return build_rows(p, extract_facts(p))

def find(name, variant):
    return next(p for p in DATA if p["product_name"] == name and p["variant"] == variant)

LT = "LINE TYPE (e.g., New Line vs. Upgrade)"


class T(unittest.TestCase):
    def test_two_rows_per_product_and_valid(self):
        rows = [r for p in DATA for r in rows_for(p)]
        self.assertEqual(len(rows), 2 * len(DATA))
        self.assertEqual(validate(rows, len(DATA)), [])
        self.assertEqual(list(rows[0].keys()), COLUMNS)

    def test_pdf_example_256gb(self):
        """The assignment's worked example, rebuilt from a real record (256GB variant)."""
        p = copy.deepcopy(find("Apple iPhone 17 Pro Max", "1 TB"))
        p["variant"], p["pricing"]["retail"] = "256 GB", "1199.99"
        new, up = rows_for(p)
        self.assertEqual(new["MSRP"], "$1199.99")
        self.assertEqual((new["UNIQUE DISCOUNT"], new["SERVICE LINE OFFER $ VALUE"], new["SWITCHER"]), ("$660.36", "$200", "$800"))
        self.assertEqual(new["FINANCE OFFER $ VALUE"], "$450")
        self.assertIsNone(new["Max TI (Maximum Trade-In Value)"])
        for c in ("UNIQUE DISCOUNT", "SERVICE LINE OFFERS", "SERVICE LINE OFFER $ VALUE", "SWITCHER"):
            self.assertIsNone(up[c])
        self.assertEqual(up["FINANCE OFFER $ VALUE"], "$250")
        self.assertTrue(up["FINANCE OFFER DESCRIPTION 1"].startswith("Get up to $240 back every year"))

    def test_strict_variant_matching(self):
        # banner on the 1TB page talks about 256GB; 1TB must get the 1TB figure
        self.assertEqual(rows_for(find("Apple iPhone 17 Pro Max", "1 TB"))[0]["UNIQUE DISCOUNT"], "$628.36")
        self.assertEqual(rows_for(find("Apple iPhone 17 Pro Max", "2 TB"))[0]["UNIQUE DISCOUNT"], "$812.36")
        self.assertEqual(rows_for(find("Apple iPhone 17 Pro", "512 GB"))[0]["UNIQUE DISCOUNT"], "$724.36")
        # reseller price only where the headline variant == row variant
        self.assertEqual(rows_for(find("Apple iPhone 17 Pro", "256 GB"))[0]["RESELLER LIST PRICE"], "$9.99")
        self.assertIsNone(rows_for(find("Apple iPhone 17 Pro", "512 GB"))[0]["RESELLER LIST PRICE"])
        # 17 Pro 256GB must not pick up the 17 Pro MAX 256GB line
        self.assertNotEqual(rows_for(find("Apple iPhone 17 Pro", "256 GB"))[0]["UNIQUE DISCOUNT"], "$660.36")

    def test_trade_in_is_model_specific(self):
        self.assertEqual(rows_for(find("Apple iPhone 17", "256 GB"))[1]["Max TI (Maximum Trade-In Value)"], "$930")
        self.assertEqual(rows_for(find("Apple iPhone 18 Pro Max", "1 TB"))[1]["Max TI (Maximum Trade-In Value)"], "$1200")
        self.assertIsNone(rows_for(find("Apple iPhone 17 Pro", "256 GB"))[0]["Max TI (Maximum Trade-In Value)"])

    def test_money_never_rounds(self):
        self.assertEqual(money("660.36"), "$660.36")
        self.assertEqual(money("800"), "$800")
        self.assertEqual(money("200", "240", "10"), "$450")
        self.assertEqual(money("1599.99"), "$1599.99")
        self.assertIsNone(money(None))

    def test_malformed_record_still_gives_two_rows(self):
        rows = build_rows({"product_name": "X"}, extract_facts({"product_name": "X", "variant": "1 TB"}))
        self.assertEqual(len(rows), 2)

    def test_llm_guard_and_parsing(self):
        p = find("Apple iPhone 17 Pro Max", "1 TB")
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertIsNone(parse_json("not json"))
        logs = []
        # hallucinated amount with fake evidence -> dropped; rules value kept
        bad = lambda s, u: json.dumps({"device_credit": {"amount": "999.99", "evidence": "up to $999.99 in bill credits"}})
        f = extract_facts_llm(p, client=bad, log=logs.append)
        self.assertEqual(f.device_credit, "628.36")
        self.assertTrue(any("ungrounded" in l for l in logs))
        # timeouts / garbage -> falls back to rules, never crashes
        boom = lambda s, u: (_ for _ in ()).throw(TimeoutError("t"))
        self.assertEqual(extract_facts_llm(p, client=boom, retries=0, log=lambda *_: None).device_credit, "628.36")


if __name__ == "__main__":
    unittest.main()

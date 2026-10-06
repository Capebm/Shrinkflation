import json
import tempfile
import unittest
from pathlib import Path

from radar.composition import extract_quid
from radar.detect import detect, similarity
from radar.model import Observation
from radar.quantity import Quantity, parse_quantity
from radar.sources import csvfile, lojas, off
from radar.store import Store

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent


def obs(date, ean="5600000000017", qty="100 g", price=1.49, **kw):
    kw.setdefault("name", "Tablete de chocolate")
    kw.setdefault("brand", "Marca")
    return Observation(observed_at=date, source="csv", retailer="Loja", ean=ean,
                       quantity_text=qty, price=price, **kw)


class QuantityTests(unittest.TestCase):
    def test_units(self):
        cases = {
            "450 g": Quantity(450, "g"), "450g": Quantity(450, "g"), "0,45 kg": Quantity(450, "g"),
            "1,5 L": Quantity(1500, "ml"), "75 cl": Quantity(750, "ml"), "330ml ℮": Quantity(330, "ml"),
            "4 x 125 g": Quantity(500, "g", 4), "6x1,5L": Quantity(9000, "ml", 6),
            "12 rolos": Quantity(12, "un", 12), "Detergente 40 lavagens": Quantity(40, "un", 40),
            "Chocolate 70% cacau 100 g": Quantity(100, "g"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_quantity(text), expected)

    def test_nothing_to_parse(self):
        for text in ("", None, "Chocolate negro", "70%", "0 g"):
            self.assertIsNone(parse_quantity(text))


class CompositionTests(unittest.TestCase):
    def test_quid(self):
        q = extract_quid("Ingredientes: carne de novilho (80%), água, sal, cebola 5%, leite em pó [12,5 %]")
        self.assertEqual(q, {"carne de novilho": 80.0, "leite em pó": 12.5, "cebola": 5.0})

    def test_quid_empty(self):
        self.assertEqual(extract_quid("açúcar, farinha, sal"), {})


class DetectTests(unittest.TestCase):
    def run_detect(self, observations):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add(observations)
            return detect(store.history(), store.seen())

    def test_shrink_same_price(self):
        [e] = self.run_detect([obs("2026-01-01"), obs("2026-02-01", qty="90 g")])
        self.assertEqual(e.kind, "encolhimento")
        self.assertAlmostEqual(e.change_pct, 11.1, places=1)
        self.assertTrue(e.price_known)

    def test_proportional_price_cut_is_not_an_alert(self):
        self.assertEqual(self.run_detect([obs("2026-01-01", qty="400 g", price=2.00),
                                          obs("2026-02-01", qty="350 g", price=1.75)]), [])

    def test_plain_price_rise_is_not_shrinkflation(self):
        self.assertEqual(self.run_detect([obs("2026-01-01"), obs("2026-02-01", price=1.79)]), [])

    def test_shrink_without_price_reports_implied_rise(self):
        [e] = self.run_detect([obs("2026-01-01", price=None), obs("2026-02-01", qty="90 g", price=None)])
        self.assertFalse(e.price_known)
        self.assertAlmostEqual(e.change_pct, 11.1, places=1)

    def test_quid_drop(self):
        events = self.run_detect([
            obs("2026-01-01", quid=extract_quid("carne de novilho (95%), sal")),
            obs("2026-02-01", quid=extract_quid("Carne de Novilho (80%), água, sal")),
        ])
        self.assertEqual([e.kind for e in events], ["receita_quid"])

    def test_code_swap(self):
        events = self.run_detect([
            obs("2026-01-01", ean="1111111111116", qty="375 g", price=2.99, name="Cereais de chocolate"),
            obs("2026-01-01", ean="3333333333332", qty="1 kg", price=5.0, name="Arroz agulha", brand="Outra"),
            obs("2026-03-01", ean="3333333333332", qty="1 kg", price=5.0, name="Arroz agulha", brand="Outra"),
            obs("2026-03-01", ean="2222222222220", qty="330 g", price=2.99, name="Cereais de chocolate novo formato"),
        ])
        [e] = events
        self.assertEqual((e.kind, e.ean_before, e.ean_after), ("troca_codigo", "1111111111116", "2222222222220"))

    def test_similarity_ignores_quantities(self):
        self.assertEqual(similarity("Cereais Choco 375 g", "Cereais Choco 330g"), 1.0)


class StoreTests(unittest.TestCase):
    def test_unchanged_observations_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            self.assertEqual(store.add([obs("2026-01-01")]), 1)
            self.assertEqual(store.add([obs("2026-01-08")]), 0)
            self.assertEqual(store.add([obs("2026-01-15", qty="90 g")]), 1)
            self.assertEqual(store.seen()["csv|Loja|5600000000017"], {"first": "2026-01-01", "last": "2026-01-15"})


class SourceTests(unittest.TestCase):
    def test_open_food_facts_mapping(self):
        payload = json.loads((FIX / "off_search.json").read_text(encoding="utf-8"))
        result = off.collect(["en:chocolates"], "2026-10-06", get_json=lambda url: payload)
        by_ean = {o.ean: o for o in result}
        self.assertEqual(set(by_ean), {"5601234567890", "5609999999999"})
        choc = by_ean["5601234567890"]
        self.assertEqual((choc.name, choc.brand, choc.amount, choc.unit), ("Chocolate de leite com avelãs", "Marca Teste", 90, "g"))
        self.assertEqual(choc.quid, {"avelãs": 12.0, "leite em pó": 18.0})
        self.assertEqual(choc.nutrition["proteína"], 7.1)
        self.assertEqual((by_ean["5609999999999"].amount, by_ean["5609999999999"].unit), (400, "g"))

    def test_search_url_filters_portugal(self):
        urls = []
        list(off.search("en:coffees", get_json=lambda u: urls.append(u) or {"products": [], "count": 0}))
        self.assertIn("countries_tags=en%3Aportugal", urls[0])
        self.assertIn("categories_tags=en%3Acoffees", urls[0])

    def test_shop_json_ld(self):
        html = (FIX / "loja_produto.html").read_text(encoding="utf-8")
        o = lojas.parse_product_page(html, "https://loja.example/p/1", "Loja Teste", "2026-10-06")
        self.assertEqual((o.ean, o.brand, o.amount, o.unit, o.price), ("5600000000123", "Marca Teste", 220, "g", 3.49))
        self.assertEqual(o.quid, {"café torrado moído": 100.0})

    def test_shop_collect_respects_robots(self):
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "lojas.csv"
            lst.write_text("retalhista,url\nLoja,https://loja.example/p/1\n", encoding="utf-8")
            got, skipped = lojas.collect(lst, "2026-10-06", pause=0, get=lambda u: "", allowed=lambda u: False)
            self.assertEqual(got, [])
            self.assertIn("robots.txt", skipped[0])

    def test_example_csv_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add(csvfile.read(ROOT / "data/exemplo/observacoes.csv"))
            kinds = sorted(e.kind for e in detect(store.history(), store.seen()))
        self.assertEqual(kinds, ["encolhimento"] * 3 + ["receita_nutricao"] + ["receita_quid"] * 2 + ["troca_codigo"])


if __name__ == "__main__":
    unittest.main()

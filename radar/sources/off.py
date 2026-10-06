"""Open Food Facts (ODbL): quantity, ingredients and nutrition for products sold in Portugal.

No prices here; shrinks found from this source report the implied rise at an
unchanged shelf price. API etiquette: custom User-Agent and at most ~10 search
requests per minute.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from urllib.parse import urlencode

from ..composition import extract_quid, nutrition_from_off, quid_from_off
from ..model import Observation
from ..quantity import parse_quantity
from . import http

SEARCH_URL = "https://world.openfoodfacts.org/api/v2/search"
FIELDS = ",".join([
    "code", "product_name", "product_name_pt", "brands", "quantity", "product_quantity",
    "product_quantity_unit", "ingredients_text_pt", "ingredients_text", "ingredients", "nutriments",
])

# Categories with the most documented cases. Unknown tags simply return nothing.
DEFAULT_CATEGORIES = [
    "en:chocolates", "en:coffees", "en:breakfast-cereals", "en:biscuits", "en:crisps",
    "en:yogurts", "en:frozen-foods", "en:margarines", "en:ice-creams", "en:sausages",
]


def search(category: str, *, max_pages: int = 10, page_size: int = 100, pause: float = 6.5,
           get_json: Callable[[str], dict] = http.get_json) -> Iterator[dict]:
    for page in range(1, max_pages + 1):
        params = {"countries_tags": "en:portugal", "categories_tags": category, "fields": FIELDS,
                  "page_size": page_size, "page": page}
        data = get_json(f"{SEARCH_URL}?{urlencode(params)}")
        products = data.get("products") or []
        yield from products
        if len(products) < page_size or page * page_size >= int(data.get("count") or 0):
            return
        time.sleep(pause)


def to_observation(p: dict, observed_at: str) -> Observation | None:
    code = str(p.get("code") or "")
    if not code:
        return None
    ingredients = p.get("ingredients_text_pt") or p.get("ingredients_text") or ""
    quid = {**extract_quid(ingredients), **quid_from_off(p.get("ingredients"))}
    obs = Observation(
        observed_at=observed_at, source="off", ean=code,
        name=p.get("product_name_pt") or p.get("product_name") or "",
        brand=(p.get("brands") or "").split(",")[0].strip(),
        quantity_text=p.get("quantity") or "",
        url=f"https://world.openfoodfacts.org/product/{code}",
        ingredients=ingredients or None, quid=quid, nutrition=nutrition_from_off(p.get("nutriments")),
    )
    if obs.amount is None and p.get("product_quantity"):
        q = parse_quantity(f"{p['product_quantity']} {p.get('product_quantity_unit') or 'g'}")
        if q:
            obs.amount, obs.unit, obs.pack_count = q.amount, q.unit, q.pack_count
    return obs


def collect(categories: list[str], observed_at: str, max_pages: int = 10,
            get_json: Callable[[str], dict] = http.get_json) -> list[Observation]:
    seen: dict[str, Observation] = {}
    for category in categories:
        for product in search(category, max_pages=max_pages, get_json=get_json):
            obs = to_observation(product, observed_at)
            if obs and obs.ean not in seen:
                seen[obs.ean] = obs
    return list(seen.values())

"""Open Food Facts (ODbL): quantity, ingredients and nutrition for products sold in Portugal.

No prices here; shrinks found from this source report the implied rise at an
unchanged shelf price. API etiquette: custom User-Agent and at most ~10 search
requests per minute.

Search goes first to Search-a-licious (search.openfoodfacts.org), the newer
Elasticsearch service, and falls back to the classic /api/v2/search, which
answered 503 on the first GitHub Actions run. Parameters checked against the
search-a-licious source (app/_types.py, data/config/openfoodfacts.yml): Lucene
query in ``q``, ``page``/``page_size`` (page * page_size <= 10 000), response
``{"hits": [...], "page_count": N}``; text fields come per language
(``{"main": ..., "pt": ...}``).

Search-a-licious hits carry no ingredient text (checked on a live response), so
ingredients come from the product endpoint, one request per product, cached in
data/off_ingredientes.json and only refetched when the product's
``last_modified_t`` changes.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlencode

from ..composition import extract_quid, nutrition_from_off, quid_from_off
from ..model import Observation
from ..quantity import parse_quantity
from . import http

SEARCH_URL = "https://world.openfoodfacts.org/api/v2/search"
SAL_URL = "https://search.openfoodfacts.org/search"
SAL_FIELDS = ",".join([
    "code", "product_name", "brands", "quantity", "product_quantity", "product_quantity_unit",
    "ingredients_text", "nutriments", "last_modified_t",
])
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}"
PRODUCT_FIELDS = "ingredients_text_pt,ingredients_text,ingredients"
FIELDS = ",".join([
    "code", "product_name", "product_name_pt", "brands", "quantity", "product_quantity",
    "product_quantity_unit", "ingredients_text_pt", "ingredients_text", "ingredients", "nutriments",
])

# Categories with the most documented cases. Unknown tags simply return nothing.
DEFAULT_CATEGORIES = [
    "en:chocolates", "en:coffees", "en:breakfast-cereals", "en:biscuits", "en:crisps",
    "en:yogurts", "en:frozen-foods", "en:margarines", "en:ice-creams", "en:sausages",
]


def search_sal(category: str, *, max_pages: int = 10, page_size: int = 100, pause: float = 6.5,
               get_json: Callable[[str], dict] = http.get_json) -> Iterator[dict]:
    for page in range(1, max_pages + 1):
        params = {"q": f'countries_tags:"en:portugal" AND categories_tags:"{category}"', "langs": "pt,en",
                  "fields": SAL_FIELDS, "page_size": page_size, "page": page}
        data = get_json(f"{SAL_URL}?{urlencode(params)}")
        if "hits" not in data:
            raise RuntimeError(f"Search-a-licious sem resultados: {str(data.get('errors'))[:200]}")
        yield from map(_from_sal_hit, data["hits"])
        if page >= int(data.get("page_count") or 1):
            return
        time.sleep(pause)


def _lang(value) -> str:
    if isinstance(value, dict):
        return value.get("pt") or value.get("main") or value.get("en") or next(iter(value.values()), "") or ""
    return value or ""


def _from_sal_hit(hit: dict) -> dict:
    """Reshape a Search-a-licious hit into the classic API product shape used below."""
    brands = hit.get("brands") or ""
    if isinstance(brands, list):
        brands = brands[0] if brands else ""
    brands = brands.split(":", 1)[-1] if ":" in brands[:4] else brands
    if brands and brands == brands.lower() and " " not in brands:  # taxonomy slug, e.g. "marca-teste"
        brands = brands.replace("-", " ").title()
    return {"code": hit.get("code"), "product_name": _lang(hit.get("product_name")), "brands": brands,
            "quantity": hit.get("quantity"), "product_quantity": hit.get("product_quantity"),
            "product_quantity_unit": hit.get("product_quantity_unit"),
            "ingredients_text": _lang(hit.get("ingredients_text")), "nutriments": hit.get("nutriments"),
            "last_modified_t": hit.get("last_modified_t")}


def search(category: str, *, max_pages: int = 10, page_size: int = 100, pause: float = 6.5,
           get_json: Callable[[str], dict] = http.get_json) -> Iterator[dict]:
    for page in range(1, max_pages + 1):
        params = {"countries_tags": "en:portugal", "categories_tags": category, "fields": FIELDS + ",last_modified_t",
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


def _get_product(url: str) -> dict:
    # one quick retry only: a product that fails is simply tried again next week
    return json.loads(http.get(url, retries=2))


def add_ingredients(pairs: list[tuple[Observation, object]], cache_path: Path, *, pause: float = 0.7,
                    get_json: Callable[[str], dict] = _get_product, budget_s: float = 15 * 60,
                    max_failures: int = 25) -> tuple[int, int]:
    """Fill in ingredients and declared percentages. Returns (requests made, failures).

    Stops fetching after ``budget_s`` seconds or ``max_failures`` failures; the cache
    keeps what was fetched, so the next weekly run carries on where this one stopped.
    Products not fetched keep the ingredients cached earlier, if any.
    """
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    fetched = failed = 0
    deadline = time.monotonic() + budget_s
    for obs, modified in pairs:
        if obs.ingredients:
            continue
        entry = cache.get(obs.ean)
        stale = not entry or entry.get("t") != modified
        if stale and time.monotonic() < deadline and failed < max_failures:
            try:
                product = get_json(PRODUCT_URL.format(code=obs.ean) + "?fields=" + PRODUCT_FIELDS).get("product") or {}
            except Exception as exc:
                failed += 1
                print(f"ingredientes {obs.ean}: {exc}", file=sys.stderr)
                product = None
            if product is None:
                if not entry:
                    continue
            else:
                fetched += 1
                text = product.get("ingredients_text_pt") or product.get("ingredients_text") or ""
                entry = cache[obs.ean] = {"t": modified, "text": text,
                                          "quid": {**extract_quid(text), **quid_from_off(product.get("ingredients"))}}
                if fetched % 100 == 0:
                    print(f"ingredientes: {fetched} produtos lidos", file=sys.stderr, flush=True)
                if pause:
                    time.sleep(pause)
        elif not entry:
            continue
        obs.ingredients = entry["text"] or None
        obs.quid = entry["quid"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return fetched, failed


def collect(categories: list[str], observed_at: str, max_pages: int = 10,
            get_json: Callable[[str], dict] = http.get_json, pause: float = 6.5,
            ingredient_cache: Path | None = None) -> tuple[list[Observation], list[str]]:
    """Return the observations and the categories that could not be read from either service."""
    seen: dict[str, Observation] = {}
    modified: dict[str, object] = {}
    failed: list[str] = []
    for category in categories:
        products = None
        for name, fn in (("search-a-licious", search_sal), ("api/v2/search", search)):
            try:
                products = list(fn(category, max_pages=max_pages, get_json=get_json, pause=pause))
                break
            except Exception as exc:  # one service down should not stop the weekly run
                print(f"{category}: {name} falhou ({exc})", file=sys.stderr)
        if products is None:
            failed.append(category)
            continue
        print(f"{category}: {len(products)} produtos", file=sys.stderr)
        for product in products:
            obs = to_observation(product, observed_at)
            if obs and obs.ean not in seen:
                seen[obs.ean] = obs
                modified[obs.ean] = product.get("last_modified_t")
    if ingredient_cache is not None:
        kwargs = {} if get_json is http.get_json else {"get_json": get_json}
        fetched, errors = add_ingredients([(o, modified[o.ean]) for o in seen.values()], ingredient_cache,
                                          pause=min(pause, 0.7), **kwargs)
        print(f"ingredientes: {fetched} pedidos ao Open Food Facts, {errors} falhas", file=sys.stderr)
    return list(seen.values()), failed

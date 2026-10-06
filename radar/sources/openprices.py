"""Open Prices (prices.openfoodfacts.org, ODbL): crowdsourced shelf prices with receipts or photos as proof.

Open Prices records the barcode, price, date and shop of each price, but not the
pack size at that date. So these prices are not a series of their own: they fill
in the price before and after a size change that Open Food Facts detected.

API checked against the open-prices source (open_prices/api/prices/filters.py):
GET /api/v1/prices?product_code__in=A,B&date__gte=YYYY-MM-DD&ordering=date&size=100&page=N
Response: {"items": [...], "page", "pages", "size", "total"}; each item nests
"location" with "osm_address_country_code".
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

from . import http

PRICES_URL = "https://prices.openfoodfacts.org/api/v1/prices"
BATCH = 50


@dataclass(frozen=True)
class PricePoint:
    id: int
    ean: str
    date: str
    price: float
    currency: str
    store: str
    country: str

    @classmethod
    def from_item(cls, item: dict) -> "PricePoint | None":
        """Keep full-price product prices in euros from shops in Portugal."""
        loc = item.get("location") or {}
        if (item.get("type") != "PRODUCT" or item.get("price_is_discounted")
                or item.get("currency") != "EUR" or loc.get("osm_address_country_code") != "PT"
                or not item.get("product_code") or item.get("price") in (None, "")):
            return None
        store = ", ".join(p for p in (loc.get("osm_name"), loc.get("osm_address_city")) if p)
        return cls(int(item["id"]), str(item["product_code"]), str(item["date"]), float(item["price"]),
                   "EUR", store, "PT")


def fetch(eans: Iterable[str], since: str, *, pause: float = 1.0,
          get_json: Callable[[str], dict] = http.get_json) -> list[PricePoint]:
    codes = sorted({e for e in eans if e})
    points: list[PricePoint] = []
    for start in range(0, len(codes), BATCH):
        batch = codes[start:start + BATCH]
        page = 1
        while True:
            params = {"product_code__in": ",".join(batch), "date__gte": since,
                      "ordering": "date", "size": 100, "page": page}
            data = get_json(f"{PRICES_URL}?{urlencode(params)}")
            points += [p for p in map(PricePoint.from_item, data.get("items") or []) if p]
            if page >= int(data.get("pages") or 1):
                break
            page += 1
            time.sleep(pause)
        time.sleep(pause)
    return points


class PriceStore:
    """data/precos_openprices.jsonl, one price per line, unique by Open Prices id."""

    def __init__(self, root: Path) -> None:
        self.path = Path(root) / "precos_openprices.jsonl"

    def load(self) -> list[PricePoint]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [PricePoint(**json.loads(line)) for line in fh if line.strip()]

    def add(self, points: list[PricePoint]) -> int:
        known = {p.id for p in self.load()}
        new = [p for p in points if p.id not in known]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for p in sorted(new, key=lambda p: (p.date, p.id)):
                fh.write(json.dumps(asdict(p), ensure_ascii=False, sort_keys=True) + "\n")
        return len(new)

"""Product pages from online shops, read through their schema.org JSON-LD.

Reads a CSV with columns ``retalhista,url``. Each page is fetched only if robots.txt
allows it, with a pause between requests. Many shops publish a JSON-LD ``Product``
with the barcode (gtin13), name, brand and offer price; the net quantity usually
sits in the name ("Chocolate de Leite 100 g") and is parsed from there.

Not yet tested against Portuguese shops: pages rendered only in the browser, or
behind bot protection, return nothing and are reported as skipped.
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from ..composition import extract_quid
from ..model import Observation
from . import http

_LD = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


def _walk(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk(node[key])


def _is_product(node: dict) -> bool:
    t = node.get("@type")
    return t == "Product" or (isinstance(t, list) and "Product" in t)


def _price(offers) -> tuple[float | None, str | None]:
    for offer in _walk(offers):
        raw = offer.get("price", offer.get("lowPrice"))
        if raw not in (None, ""):
            try:
                return float(str(raw).replace(",", ".")), offer.get("priceCurrency")
            except ValueError:
                continue
    return None, None


def parse_product_page(html: str, url: str, retailer: str, observed_at: str) -> Observation | None:
    for block in _LD.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if not _is_product(node):
                continue
            ean = next((str(node[k]) for k in ("gtin13", "gtin", "gtin14", "gtin8", "sku") if node.get(k)), "")
            brand = node.get("brand")
            brand = brand.get("name", "") if isinstance(brand, dict) else (brand or "")
            weight = node.get("weight")
            qty_text = ""
            if isinstance(weight, dict) and weight.get("value"):
                qty_text = f"{weight['value']} {weight.get('unitText') or weight.get('unitCode') or ''}"
            price, currency = _price(node.get("offers"))
            description = node.get("description") or ""
            return Observation(observed_at=observed_at, source="loja", retailer=retailer, ean=ean,
                               name=node.get("name") or "", brand=str(brand), quantity_text=qty_text,
                               price=price, currency=currency or "EUR", url=url,
                               quid=extract_quid(description))
    return None


def collect(list_path: Path, observed_at: str, pause: float = 3.0,
            get: Callable[[str], str] = http.get, allowed: Callable[[str], bool] = http.allowed
            ) -> tuple[list[Observation], list[str]]:
    observations, skipped = [], []
    with Path(list_path).open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("url") or "").strip()]
    for i, row in enumerate(rows):
        url = row["url"].strip()
        if not allowed(url):
            skipped.append(f"{url} (robots.txt)")
            continue
        try:
            obs = parse_product_page(get(url), url, row.get("retalhista", "").strip(), observed_at)
        except Exception as exc:  # network errors should not stop the weekly run
            skipped.append(f"{url} ({exc.__class__.__name__})")
        else:
            if obs and obs.ean:
                observations.append(obs)
            else:
                skipped.append(f"{url} (sem JSON-LD Product com código de barras)")
        if i < len(rows) - 1:
            time.sleep(pause)
    return observations, skipped

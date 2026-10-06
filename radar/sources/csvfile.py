"""Manual or partner data: receipts, shelf photos, DECO cases, retailer feeds.

Columns: data, retalhista, ean, marca, nome, quantidade, preco, url, ingredientes,
proteina. Decimal commas are accepted.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..composition import extract_quid
from ..model import Observation


def _float(value: str | None) -> float | None:
    value = (value or "").strip().replace("€", "").replace(",", ".")
    return float(value) if value else None


def read(path: Path) -> list[Observation]:
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("ean") and row.get("data")):
                continue
            protein = _float(row.get("proteina"))
            out.append(Observation(
                observed_at=row["data"].strip(), source="csv", ean=row["ean"],
                retailer=(row.get("retalhista") or "").strip(), brand=(row.get("marca") or "").strip(),
                name=(row.get("nome") or "").strip(), quantity_text=(row.get("quantidade") or "").strip(),
                price=_float(row.get("preco")), currency="EUR", url=(row.get("url") or "").strip() or None,
                ingredients=(row.get("ingredientes") or "").strip() or None,
                quid=extract_quid(row.get("ingredientes")),
                nutrition={"proteína": protein} if protein is not None else {},
            ))
    return out

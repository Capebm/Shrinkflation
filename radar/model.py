from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields

from .quantity import parse_quantity


@dataclass
class Observation:
    """One product as seen by one source on one date."""

    observed_at: str                 # ISO date, YYYY-MM-DD
    source: str                      # "off", "loja", "csv"
    ean: str
    name: str = ""
    brand: str = ""
    retailer: str = ""               # empty for sources without prices (Open Food Facts)
    quantity_text: str = ""
    amount: float | None = None      # total in base unit
    unit: str | None = None          # "g", "ml" or "un"
    pack_count: int | None = None
    price: float | None = None
    currency: str | None = None
    url: str | None = None
    ingredients: str | None = None
    quid: dict[str, float] = field(default_factory=dict)
    nutrition: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ean = "".join(ch for ch in str(self.ean) if ch.isdigit())
        if self.amount is None:
            q = parse_quantity(self.quantity_text) or parse_quantity(self.name)
            if q:
                self.amount, self.unit, self.pack_count = q.amount, q.unit, q.pack_count

    @property
    def key(self) -> str:
        return f"{self.source}|{self.retailer}|{self.ean}"

    @property
    def unit_price(self) -> float | None:
        if self.price is None or not self.amount:
            return None
        return self.price / self.amount

    def signature(self) -> str:
        """Hash of the fields whose change matters; equal signatures are not stored twice."""
        relevant = {
            "amount": self.amount, "unit": self.unit, "pack_count": self.pack_count,
            "price": self.price, "quid": self.quid, "nutrition": self.nutrition,
            "name": self.name, "brand": self.brand,
        }
        return hashlib.sha1(json.dumps(relevant, sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, [])}

    @classmethod
    def from_dict(cls, data: dict) -> "Observation":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

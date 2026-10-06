"""Parse net quantities from labels such as "450 g", "0,45 kg", "4 x 125 g" or "12 rolos".

Everything is normalised to one of three base units: grams (g), millilitres (ml)
or units (un), so that two observations of the same product can be compared.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# label unit -> (base unit, factor to base unit)
UNITS: dict[str, tuple[str, float]] = {
    "mg": ("g", 0.001), "g": ("g", 1), "gr": ("g", 1), "grs": ("g", 1), "gramas": ("g", 1),
    "kg": ("g", 1000), "kgs": ("g", 1000),
    "ml": ("ml", 1), "cl": ("ml", 10), "dl": ("ml", 100),
    "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000), "litro": ("ml", 1000), "litros": ("ml", 1000),
    "un": ("un", 1), "und": ("un", 1), "unid": ("un", 1), "unidade": ("un", 1), "unidades": ("un", 1),
    "uds": ("un", 1), "pcs": ("un", 1), "rolo": ("un", 1), "rolos": ("un", 1),
    "cápsula": ("un", 1), "cápsulas": ("un", 1), "capsula": ("un", 1), "capsulas": ("un", 1),
    "saqueta": ("un", 1), "saquetas": ("un", 1), "doses": ("un", 1), "lavagens": ("un", 1),
    "folhas": ("un", 1), "toalhitas": ("un", 1), "pastilhas": ("un", 1),
}

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
_MULTI = re.compile(rf"(\d+)\s*[x×]\s*{_NUM}\s*({_UNIT})(?![\w])", re.IGNORECASE)
_SINGLE = re.compile(rf"{_NUM}\s*({_UNIT})(?![\w])", re.IGNORECASE)


@dataclass(frozen=True)
class Quantity:
    amount: float          # total amount in base unit
    unit: str              # "g", "ml" or "un"
    pack_count: int = 1    # number of items in a multipack


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def parse_quantity(text: str | None) -> Quantity | None:
    """Return the total quantity found in ``text``, or None when nothing parses."""
    if not text:
        return None
    text = text.replace("℮", " ")
    m = _MULTI.search(text)
    if m:
        count = int(m.group(1))
        base, factor = UNITS[m.group(3).lower()]
        if count > 0:
            return Quantity(round(count * _num(m.group(2)) * factor, 3), base, count)
    m = _SINGLE.search(text)
    if m:
        base, factor = UNITS[m.group(2).lower()]
        amount = round(_num(m.group(1)) * factor, 3)
        if amount > 0:
            return Quantity(amount, base, int(amount) if base == "un" else 1)
    return None

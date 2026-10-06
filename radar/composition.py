"""Composition signals used to spot skimpflation (cheaper recipe at the same price).

QUID: EU Regulation 1169/2011, art. 22, requires the percentage of an ingredient
that is named or emphasised on the label ("hambúrguer de novilho (80%)").
A falling QUID is the cleanest public signal of a downgraded recipe.
"""
from __future__ import annotations

import re
import unicodedata

_PCT = r"(\d{1,3}(?:[.,]\d+)?)\s*%"
_BRACKETED = re.compile(rf"([^,;:()\[\]]{{2,60}}?)\s*[(\[]\s*{_PCT}\s*[)\]]")
_INLINE = re.compile(rf"([^,;:()\[\]%\d]{{2,60}}?)\s+{_PCT}")

NUTRIENTS = {
    "proteins_100g": "proteína",
    "fat_100g": "gordura",
    "sugars_100g": "açúcares",
    "salt_100g": "sal",
    "energy-kcal_100g": "kcal",
}


def normalise(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"^\s*ingredientes?\s*", "", name.lower())
    name = re.sub(r"[^a-z ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _label(raw: str) -> str:
    raw = re.sub(r"^\s*ingredientes?\s*", "", raw.strip().lower())
    return re.sub(r"\s+", " ", raw).strip(" .-_*")


def extract_quid(ingredients: str | None) -> dict[str, float]:
    """Map each ingredient that carries a declared percentage to that percentage."""
    if not ingredients:
        return {}
    found: dict[str, float] = {}
    keys: set[str] = set()
    for pattern in (_BRACKETED, _INLINE):
        for m in pattern.finditer(ingredients):
            label, pct = _label(m.group(1)), float(m.group(2).replace(",", "."))
            if normalise(label) and 0 < pct <= 100 and normalise(label) not in keys:
                keys.add(normalise(label))
                found[label] = pct
    return found


def quid_from_off(ingredients: list[dict] | None) -> dict[str, float]:
    """Declared percentages from Open Food Facts' parsed ingredient list (ignores estimates)."""
    found: dict[str, float] = {}
    for item in ingredients or []:
        pct = item.get("percent")
        name = _label(str(item.get("text", "")))
        if name and isinstance(pct, (int, float)) and 0 < pct <= 100:
            found.setdefault(name, float(pct))
    return found


def nutrition_from_off(nutriments: dict | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, label in NUTRIENTS.items():
        value = (nutriments or {}).get(key)
        if isinstance(value, (int, float)):
            out[label] = round(float(value), 2)
    return out

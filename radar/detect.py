"""Turn the observation history into events: shrinkflation, skimpflation and code swaps."""
from __future__ import annotations

import hashlib
import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta

from .composition import normalise
from .model import Observation
from .sources.openprices import PricePoint

QTY_TOLERANCE = 0.005      # ignore rounding noise below 0.5%
MIN_UNIT_PRICE_RISE = 3.0  # % rise in unit price that makes a shrink an alert
MIN_QUID_DROP = 2.0        # percentage points
MIN_NUTRIENT_DROP = 0.10   # relative drop
SWAP_WINDOW_DAYS = 120
SWAP_MIN_SIMILARITY = 0.6
PRICE_WINDOW_DAYS = 365    # how far from a size change Open Prices points are still used
PRICE_POINTS = 5           # median of up to this many prices on each side

KIND_LABELS = {
    "encolhimento": "Embalagem encolheu",
    "troca_codigo": "Embalagem encolheu com novo código de barras",
    "receita_quid": "Menos ingrediente principal",
    "receita_nutricao": "Composição nutricional pior",
}


@dataclass
class Event:
    kind: str
    brand: str
    name: str
    source: str
    retailer: str
    ean_before: str
    ean_after: str
    date_before: str
    date_after: str
    summary: str
    change_pct: float | None = None      # effective rise in price per unit, when known or implied
    price_known: bool = False
    details: dict = field(default_factory=dict)
    url: str | None = None

    @property
    def id(self) -> str:
        raw = "|".join([self.kind, self.source, self.retailer, self.ean_before, self.ean_after,
                        self.date_before, self.date_after, self.summary])
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["label"] = KIND_LABELS[self.kind]
        return d


def _fmt(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _money(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _qty(o: Observation) -> str:
    amount = o.amount or 0
    if o.unit == "g" and amount >= 1000:
        return f"{_fmt(amount / 1000)} kg"
    if o.unit == "ml" and amount >= 1000:
        return f"{_fmt(amount / 1000)} l"
    return f"{amount:g} {o.unit}"


def _shrink(a: Observation, b: Observation, kind: str,
            prices: dict[str, list[PricePoint]] | None = None) -> Event | None:
    if not (a.amount and b.amount) or a.unit != b.unit:
        return None
    if b.amount >= a.amount * (1 - QTY_TOLERANCE):
        return None
    price_note = ""
    if (a.price is None or b.price is None) and prices:
        a, b, price_note = _with_crowd_prices(a, b, prices)
    qty_drop = (1 - b.amount / a.amount) * 100
    price_known = a.price is not None and b.price is not None
    if price_known:
        change = (b.unit_price / a.unit_price - 1) * 100
        if change < MIN_UNIT_PRICE_RISE:
            return None  # the price fell along with the size: not hidden inflation
        cur = {"EUR": "€", None: "€"}.get(b.currency, b.currency)
        summary = (f"{_qty(a)} → {_qty(b)} (−{_fmt(qty_drop)}%); preço {_money(a.price)} → {_money(b.price)} {cur}; "
                   f"preço por unidade +{_fmt(change)}%{price_note}")
    else:
        change = (a.amount / b.amount - 1) * 100  # implied rise if the shelf price stayed the same
        summary = f"{_qty(a)} → {_qty(b)} (−{_fmt(qty_drop)}%); preço desconhecido nesta fonte"
    return Event(kind, b.brand or a.brand, b.name or a.name, b.source, b.retailer, a.ean, b.ean,
                 a.observed_at, b.observed_at, summary, round(change, 1), price_known,
                 {"qty_before": a.amount, "qty_after": b.amount, "unit": b.unit,
                  "price_before": a.price, "price_after": b.price,
                  "price_source": "Open Prices" if price_note else None}, b.url or a.url)


def _with_crowd_prices(a: Observation, b: Observation, prices: dict[str, list[PricePoint]]
                       ) -> tuple[Observation, Observation, str]:
    """Median Open Prices price of the old pack before the change and of the new pack after it.

    Prices dated between the two observations are skipped: the pack size on those dates is unknown.
    """
    start = (date.fromisoformat(a.observed_at) - timedelta(days=PRICE_WINDOW_DAYS)).isoformat()
    end = (date.fromisoformat(b.observed_at) + timedelta(days=PRICE_WINDOW_DAYS)).isoformat()
    before = [p.price for p in prices.get(a.ean, []) if start <= p.date <= a.observed_at][-PRICE_POINTS:]
    after = [p.price for p in prices.get(b.ean, []) if b.observed_at <= p.date <= end][:PRICE_POINTS]
    if not (before and after):
        return a, b, ""
    note = f" (mediana de {len(before)} e {len(after)} preços no Open Prices)"
    return (replace(a, price=round(statistics.median(before), 2), currency="EUR"),
            replace(b, price=round(statistics.median(after), 2), currency="EUR"), note)


def _quid(a: Observation, b: Observation) -> list[Event]:
    events = []
    after_by_key = {normalise(k): v for k, v in b.quid.items()}
    for ingredient, before in a.quid.items():
        after = after_by_key.get(normalise(ingredient))
        if after is not None and before - after >= MIN_QUID_DROP:
            events.append(Event("receita_quid", b.brand, b.name, b.source, b.retailer, a.ean, b.ean,
                                a.observed_at, b.observed_at,
                                f"{ingredient}: {_fmt(before)}% → {_fmt(after)}%",
                                details={"ingredient": ingredient, "before": before, "after": after},
                                url=b.url or a.url))
    return events


def _nutrition(a: Observation, b: Observation) -> list[Event]:
    changes = []
    for nutrient, min_abs in (("proteína", 0.5),):
        before, after = a.nutrition.get(nutrient), b.nutrition.get(nutrient)
        if before and after is not None and before - after >= min_abs and (before - after) / before >= MIN_NUTRIENT_DROP:
            changes.append(f"{nutrient} {_fmt(before)} → {_fmt(after)} g/100 g")
    if not changes:
        return []
    return [Event("receita_nutricao", b.brand, b.name, b.source, b.retailer, a.ean, b.ean,
                  a.observed_at, b.observed_at, "; ".join(changes),
                  details={"before": a.nutrition, "after": b.nutrition}, url=b.url or a.url)]


def _tokens(name: str) -> set[str]:
    name = re.sub(r"\d+([.,]\d+)?\s*[a-zçãáéíóú]*", " ", normalise(name))
    return {t for t in name.split() if len(t) > 1}


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def detect(history: list[Observation], seen: dict[str, dict[str, str]],
           crowd_prices: list[PricePoint] | None = None) -> list[Event]:
    prices: dict[str, list[PricePoint]] = defaultdict(list)
    for point in sorted(crowd_prices or [], key=lambda p: (p.date, p.id)):
        prices[point.ean].append(point)
    by_key: dict[str, list[Observation]] = defaultdict(list)
    for obs in history:
        by_key[obs.key].append(obs)

    events: list[Event] = []
    for series in by_key.values():
        series.sort(key=lambda o: o.observed_at)
        for a, b in zip(series, series[1:]):
            ev = _shrink(a, b, "encolhimento", prices)
            if ev:
                events.append(ev)
            events += _quid(a, b)
            events += _nutrition(a, b)

    events += _code_swaps(by_key, seen, prices)
    uniq = {e.id: e for e in events}
    return sorted(uniq.values(), key=lambda e: (-(e.change_pct or 0), e.date_after))


def _code_swaps(by_key: dict[str, list[Observation]], seen: dict[str, dict[str, str]],
                prices: dict[str, list[PricePoint]]) -> list[Event]:
    """A product code disappears and a similar product from the same brand appears, smaller."""
    last_run: dict[str, str] = {}
    for key, span in seen.items():
        scope = key.rsplit("|", 1)[0]
        last_run[scope] = max(last_run.get(scope, ""), span["last"])

    events = []
    for old_key, old_span in seen.items():
        scope = old_key.rsplit("|", 1)[0]
        if old_span["last"] >= last_run[scope] or old_key not in by_key:
            continue  # still on sale
        old = by_key[old_key][-1]
        for new_key, new_span in seen.items():
            if new_key == old_key or not new_key.startswith(scope + "|") or new_key not in by_key:
                continue
            gap = _days(old_span["last"], new_span["first"])
            if not -14 <= gap <= SWAP_WINDOW_DAYS:
                continue
            new = by_key[new_key][0]
            if normalise(old.brand) != normalise(new.brand) or similarity(old.name, new.name) < SWAP_MIN_SIMILARITY:
                continue
            ev = _shrink(old, new, "troca_codigo", prices)
            if ev:
                events.append(ev)
    return events

"""Append-only history on disk, kept small enough to commit to git.

data/historico.jsonl  one Observation per line, written only when something changed
data/vistos.json      first and last date each product key was seen (for code swaps)
"""
from __future__ import annotations

import json
from pathlib import Path

from .model import Observation


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.history_path = self.root / "historico.jsonl"
        self.seen_path = self.root / "vistos.json"

    def history(self) -> list[Observation]:
        if not self.history_path.exists():
            return []
        with self.history_path.open(encoding="utf-8") as fh:
            return [Observation.from_dict(json.loads(line)) for line in fh if line.strip()]

    def seen(self) -> dict[str, dict[str, str]]:
        if not self.seen_path.exists():
            return {}
        return json.loads(self.seen_path.read_text(encoding="utf-8"))

    def add(self, observations: list[Observation]) -> int:
        """Store observations that differ from the latest known state. Returns how many were written."""
        self.root.mkdir(parents=True, exist_ok=True)
        latest: dict[str, str] = {}
        for obs in self.history():
            latest[obs.key] = obs.signature()
        seen = self.seen()
        written = 0
        with self.history_path.open("a", encoding="utf-8") as fh:
            for obs in sorted(observations, key=lambda o: o.observed_at):
                if not obs.ean:
                    continue
                span = seen.setdefault(obs.key, {"first": obs.observed_at, "last": obs.observed_at})
                span["first"] = min(span["first"], obs.observed_at)
                span["last"] = max(span["last"], obs.observed_at)
                sig = obs.signature()
                if latest.get(obs.key) != sig:
                    fh.write(json.dumps(obs.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                    latest[obs.key] = sig
                    written += 1
        self.seen_path.write_text(json.dumps(seen, indent=1, sort_keys=True), encoding="utf-8")
        return written

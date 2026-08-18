"""Remembers which candidate you actually pick for a given pinyin key.

Stored as a dict mapping JSON-encoded [key, text] pairs to [count, last_seq].
The bonus dominates the base weight so a learned pick wins, and recency breaks
ties between equal counts.
"""

from __future__ import annotations

import json
from pathlib import Path

COUNT_BONUS = 1e6
RECENCY_BONUS = 1.0


class Learn:
    def __init__(self, path: Path | None, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._entries: dict[str, list[float]] = {}
        self._seq = 0.0
        if enabled and path and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                raw = None
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if (
                        isinstance(key, str)
                        and isinstance(value, list)
                        and len(value) == 2
                        and all(
                            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
                        )
                    ):
                        self._entries[key] = [float(value[0]), float(value[1])]
                self._seq = max((v[1] for v in self._entries.values()), default=0.0)

    @staticmethod
    def _key(key: str, text: str) -> str:
        return json.dumps([key, text], ensure_ascii=False)

    def bonus(self, key: str, text: str) -> float:
        if not self.enabled:
            return 0.0
        entry = self._entries.get(self._key(key, text))
        if not entry:
            return 0.0
        count, seq = entry
        return count * COUNT_BONUS + seq * RECENCY_BONUS

    def record(self, key: str, text: str) -> None:
        if not self.enabled:
            return
        self._seq += 1.0
        entry = self._entries.setdefault(self._key(key, text), [0.0, 0.0])
        entry[0] += 1.0
        entry[1] = self._seq

    def reset(self) -> None:
        self._entries = {}
        self._seq = 0.0

    def save(self) -> None:
        if not self.enabled or not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._entries), encoding="utf-8")
        except OSError:
            pass  # losing the learn file must never break composing

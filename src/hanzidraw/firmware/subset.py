"""Choose which characters fit in the keyboard's flash, and cost them honestly."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..data.store import Store

S = 0.125
ROW_BYTES = 20  # three pointers + nstroke + padding + the py pointer, on a 32-bit target
ROUND_MODE = "half_away"


def _round(value: float) -> int:
    if ROUND_MODE == "half_even":
        return int(round(value))
    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


def firmware_xy(medians) -> tuple[list[int], list[int], list[int]]:
    xs: list[int] = []
    ys: list[int] = []
    lens: list[int] = []
    for stroke in medians:
        lens.append(len(stroke))
        for ex, ey in stroke:
            xs.append(_round(S * ex))
            ys.append(_round(S * ey))
    return xs, ys, lens


@dataclass(frozen=True)
class Entry:
    codepoint: int
    pinyin: str
    xs: list[int]
    ys: list[int]
    lens: list[int]

    @property
    def cost_bytes(self) -> int:
        return 4 * len(self.xs) + len(self.lens) + ROW_BYTES + len(self.pinyin) + 1


def _entry(store: Store, codepoint: int, pinyin: str) -> Entry:
    xs, ys, lens = firmware_xy(store.medians(codepoint))
    return Entry(codepoint=codepoint, pinyin=pinyin, xs=xs, ys=ys, lens=lens)


def select(
    store: Store,
    *,
    must: str = "",
    budget_bytes: int | None = None,
    per_initial: int | None = None,
    limit: int | None = None,
) -> list[Entry]:
    chosen: list[Entry] = []
    seen: set[int] = set()
    per_count: dict[str, int] = {}
    spent = 0

    for char in must:
        codepoint = ord(char)
        if codepoint in seen or not store.has_char(codepoint):
            continue
        pinyin = store.first_reading(codepoint)
        if not pinyin:
            continue
        entry = _entry(store, codepoint, pinyin)
        chosen.append(entry)
        seen.add(codepoint)
        spent += entry.cost_bytes
        per_count[pinyin[0]] = per_count.get(pinyin[0], 0) + 1

    for codepoint, pinyin, _rank in store.all_chars_by_rank():
        if limit is not None and len(chosen) >= limit:
            break
        if codepoint in seen or not pinyin:
            continue
        initial = pinyin[0]
        if per_initial is not None and per_count.get(initial, 0) >= per_initial:
            continue
        entry = _entry(store, codepoint, pinyin)
        if budget_bytes is not None and spent + entry.cost_bytes > budget_bytes:
            continue
        chosen.append(entry)
        seen.add(codepoint)
        spent += entry.cost_bytes
        per_count[initial] = per_count.get(initial, 0) + 1
    return chosen

"""The output contract every backend implements."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..data.store import Store
from ..render.glyph import Glyph, Point, glyph_from_em, place


@dataclass(frozen=True)
class Style:
    color: str
    width: float


class Backend(Protocol):
    def begin_glyph(self, ox: float, oy: float, size: float) -> None: ...
    def stroke(self, points: Sequence[Point]) -> None: ...
    def end_glyph(self) -> None: ...


def load_glyph(store: Store, codepoint: int) -> Glyph:
    return glyph_from_em(store.medians(codepoint))


def draw_glyph(backend: Backend, glyph: Glyph, ox: float, oy: float, size: float) -> None:
    backend.begin_glyph(ox, oy, size)
    for stroke in place(glyph, ox, oy, size).strokes:
        backend.stroke(stroke)
    backend.end_glyph()

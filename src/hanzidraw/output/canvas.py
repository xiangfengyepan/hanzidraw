"""Backend that draws into the application's own canvas widget."""

from __future__ import annotations

from collections.abc import Sequence

from ..render.glyph import Glyph, Point


class CanvasBackend:
    def __init__(self, view, text: str = "") -> None:
        self._view = view
        self._text = text
        self._strokes: list[tuple[Point, ...]] = []
        self._box = (0.0, 0.0, 0.0)
        self._outline: tuple[str, ...] | None = None

    def set_text(self, text: str) -> None:
        self._text = text

    def set_outline(self, outline: tuple[str, ...] | None) -> None:
        self._outline = outline

    def begin_glyph(self, ox: float, oy: float, size: float) -> None:
        self._strokes = []
        self._box = (ox, oy, size)

    def stroke(self, points: Sequence[Point]) -> None:
        self._strokes.append(tuple(points))

    def end_glyph(self) -> None:
        ox, oy, size = self._box
        self._view.commit(
            Glyph(tuple(self._strokes)), self._text, ox, oy, size, outline=self._outline
        )
        self._strokes = []
        self._outline = None

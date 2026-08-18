"""Where each confirmed glyph goes, and the practice grid behind it."""

from __future__ import annotations

from dataclasses import dataclass

from .glyph import Glyph


@dataclass(frozen=True)
class Placed:
    glyph: Glyph
    text: str
    ox: float
    oy: float
    size: float


@dataclass(frozen=True)
class GridLine:
    x1: float
    y1: float
    x2: float
    y2: float
    dashed: bool


class Sheet:
    def __init__(self, columns: int, advance: float, size: float, wrap: bool = True) -> None:
        if columns < 1:
            raise ValueError("columns must be at least 1")
        if advance <= 0:
            raise ValueError(f"advance must be positive, got {advance}")
        if size <= 0:
            raise ValueError(f"size must be positive, got {size}")
        self.columns = columns
        self.pitch = advance * size
        self.size = size
        self.wrap = wrap
        self._placed: list[Placed] = []

    @property
    def placed(self) -> tuple[Placed, ...]:
        return tuple(self._placed)

    @property
    def cursor(self) -> tuple[int, int]:
        n = len(self._placed)
        if not self.wrap:
            return (n, 0)
        return (n % self.columns, n // self.columns)

    def _origin(self, index: int) -> tuple[float, float]:
        col = index if not self.wrap else index % self.columns
        row = 0 if not self.wrap else index // self.columns
        pad = (self.pitch - self.size) / 2.0
        return (pad + col * self.pitch, pad + row * self.pitch)

    def add(self, glyph: Glyph, text: str) -> Placed:
        ox, oy = self._origin(len(self._placed))
        placed = Placed(glyph=glyph, text=text, ox=ox, oy=oy, size=self.size)
        self._placed.append(placed)
        return placed

    def undo(self) -> Placed | None:
        return self._placed.pop() if self._placed else None

    def clear(self) -> None:
        self._placed.clear()

    def size_px(self) -> tuple[float, float]:
        # An empty sheet shows one row of grid: practice paper displays the next
        # cell to be written in, so a blank canvas must not appear gridless.
        used = max(1, len(self._placed))
        if not self.wrap:
            return (used * self.pitch, self.pitch)
        rows = max(1, (used + self.columns - 1) // self.columns)
        return (self.columns * self.pitch, rows * self.pitch)

    def grid_lines(self, kind: str) -> tuple[GridLine, ...]:
        valid_kinds = {"none", "tian", "mi", "cross"}
        if kind not in valid_kinds:
            raise ValueError(
                f"unknown grid kind {kind!r}; must be one of {', '.join(sorted(valid_kinds))}"
            )
        if kind == "none":
            return ()
        width, height = self.size_px()
        cols = self.columns if self.wrap else max(1, len(self._placed))
        rows = max(1, int(round(height / self.pitch)))
        lines: list[GridLine] = []
        for row in range(rows):
            for col in range(cols):
                x, y = col * self.pitch, row * self.pitch
                p = self.pitch
                if kind in ("tian", "mi"):
                    lines += [
                        GridLine(x, y, x + p, y, False),
                        GridLine(x, y + p, x + p, y + p, False),
                        GridLine(x, y, x, y + p, False),
                        GridLine(x + p, y, x + p, y + p, False),
                    ]
                lines += [
                    GridLine(x, y + p / 2, x + p, y + p / 2, True),
                    GridLine(x + p / 2, y, x + p / 2, y + p, True),
                ]
                if kind == "mi":
                    lines += [
                        GridLine(x, y, x + p, y + p, True),
                        GridLine(x + p, y, x, y + p, True),
                    ]
        return tuple(lines)

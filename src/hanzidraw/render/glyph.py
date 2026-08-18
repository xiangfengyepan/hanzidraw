"""Stroke geometry: em units -> unit box -> pixels, plus arc-length walking.

The em -> unit-box mapping lives here and only here; the firmware exporter has
its own mapping from the same stored em units (see firmware/emit_c.py).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

EM = 1024.0

Point = tuple[float, float]


@dataclass(frozen=True)
class Glyph:
    strokes: tuple[tuple[Point, ...], ...]

    def bounds(self) -> tuple[float, float, float, float]:
        points = [p for stroke in self.strokes for p in stroke]
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))


def glyph_from_em(medians: Sequence[Sequence[Sequence[int]]]) -> Glyph:
    strokes = tuple(
        tuple((x / EM + 0.5, y / EM + 0.5) for x, y in stroke) for stroke in medians if len(stroke)
    )
    return Glyph(strokes)


def place(glyph: Glyph, ox: float, oy: float, size: float) -> Glyph:
    return Glyph(
        tuple(tuple((ox + x * size, oy + y * size) for x, y in stroke) for stroke in glyph.strokes)
    )


def polyline_length(points: Sequence[Point]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def walk(points: Sequence[Point], frac: float) -> tuple[Point, ...]:
    if not points:
        return ()
    frac = max(0.0, min(1.0, frac))
    if frac <= 0.0:
        return (tuple(points[0]),)
    total = polyline_length(points)
    if total == 0.0:
        return tuple(tuple(p) for p in points)
    if frac >= 1.0:
        return tuple(tuple(p) for p in points)

    target = total * frac
    out: list[Point] = [tuple(points[0])]
    walked = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        seg = math.hypot(x1 - x0, y1 - y0)
        if walked + seg >= target:
            t = (target - walked) / seg if seg else 0.0
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            return tuple(out)
        walked += seg
        out.append((x1, y1))
    return tuple(out)

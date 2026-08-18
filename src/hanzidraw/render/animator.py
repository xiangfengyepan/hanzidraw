"""Deterministic, frame-rate independent stroke reveal.

The caller supplies the time, so the same timeline can drive a 144 Hz widget, a
single PNG frame, or a test.
"""

from __future__ import annotations

from dataclasses import dataclass

from .glyph import Glyph, walk


def ease(name: str, t: float) -> float:
    t = max(0.0, min(1.0, t))
    if name == "ease_in":
        return t * t
    if name == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if name == "ease_in_out":
        return 2 * t * t if t < 0.5 else 1.0 - 2 * (1.0 - t) * (1.0 - t)
    return t


@dataclass(frozen=True)
class Timing:
    stroke_ms: float = 380.0
    gap_ms: float = 90.0
    easing: str = "ease_out"

    @classmethod
    def from_config(cls, cfg) -> Timing:
        return cls(
            stroke_ms=float(cfg.get("glyph.animation.stroke_ms")),
            gap_ms=float(cfg.get("glyph.animation.gap_ms")),
            easing=str(cfg.get("glyph.animation.easing")),
        )


class Timeline:
    def __init__(self, glyph: Glyph, timing: Timing) -> None:
        self.glyph = glyph
        self.timing = timing
        self._step = max(1e-6, timing.stroke_ms + timing.gap_ms)

    @property
    def total_ms(self) -> float:
        n = len(self.glyph.strokes)
        if not n:
            return 0.0
        return n * self.timing.stroke_ms + max(0, n - 1) * self.timing.gap_ms

    def stroke_progress(self, t_ms: float) -> tuple[int, float]:
        n = len(self.glyph.strokes)
        if n == 0 or t_ms >= self.total_ms:
            return (n, 1.0)
        if t_ms < 0.0:
            return (0, 0.0)
        index = int(t_ms // self._step)
        if index >= n:
            return (n, 1.0)
        within = t_ms - index * self._step
        return (index, max(0.0, min(1.0, within / self.timing.stroke_ms)))

    def at(self, t_ms: float) -> Glyph:
        if t_ms < 0.0:
            return Glyph(())
        index, frac = self.stroke_progress(t_ms)
        strokes = list(self.glyph.strokes[:index])
        if index < len(self.glyph.strokes):
            eased = ease(self.timing.easing, frac)
            if eased > 0.0:
                strokes.append(walk(self.glyph.strokes[index], eased))
        return Glyph(tuple(strokes))

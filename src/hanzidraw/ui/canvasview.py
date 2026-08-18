"""The drawing surface: grid, finished glyphs, and the one being animated."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..render.animator import Timeline, Timing
from ..render.glyph import Glyph
from ..render.sheet import Sheet

FRAME_MS = 16


class CanvasView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = None
        self._mode = "sheet"
        self._sheet = Sheet(columns=6, advance=1.15, size=240.0)
        self._done: list[tuple[Glyph, str]] = []
        self._current: Glyph | None = None
        self._current_text = ""
        self._current_box = (0.0, 0.0, 0.0)
        self._timeline: Timeline | None = None
        self._started = 0.0
        self._frozen_strokes: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ---- configuration ----

    def configure(self, cfg) -> None:
        self._cfg = cfg
        self._mode = str(cfg.get("canvas.mode"))
        self._sheet = Sheet(
            columns=int(cfg.get("canvas.columns")),
            advance=float(cfg.get("canvas.advance")),
            size=float(cfg.get("glyph.size_px")),
            wrap=bool(cfg.get("canvas.wrap")),
        )
        self._done.clear()
        self._current = None
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode == "single":
            self._done = self._done[-1:] if self._done else []
        self.update()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def sheet(self) -> Sheet:
        return self._sheet

    @property
    def glyph_count(self) -> int:
        return len(self._done) + (1 if self._current is not None else 0)

    @property
    def is_animating(self) -> bool:
        return self._timer.isActive()

    # ---- content ----

    def commit(self, glyph: Glyph, text: str, ox: float, oy: float, size: float) -> None:
        # Task 20's outline painter needs the cell box to place the typographic
        # contour, so it is kept rather than discarded even though the pixel
        # geometry pushed here is already baked into `glyph`.
        self._current_box = (ox, oy, size)
        if self._current is not None:
            self._done.append((self._current, self._current_text))
        if self._mode == "single":
            self._done.clear()
        self._current = glyph
        self._current_text = text
        self._frozen_strokes = None
        animated = self._cfg is None or bool(self._cfg.get("glyph.animation.enabled"))
        if animated:
            timing = Timing.from_config(self._cfg) if self._cfg else Timing()
            self._timeline = Timeline(glyph, timing)
            self._started = time.monotonic() * 1000.0
            self._timer.start()
        else:
            self._timeline = None
            self._timer.stop()
        self.update()

    def undo(self) -> None:
        self._timer.stop()
        if self._current is not None:
            self._current = None
        elif self._done:
            self._done.pop()
        self.update()

    def clear(self) -> None:
        self._timer.stop()
        self._done.clear()
        self._current = None
        self._sheet.clear()
        self.update()

    def replay(self) -> None:
        if self._current is None:
            return
        timing = Timing.from_config(self._cfg) if self._cfg else Timing()
        self._timeline = Timeline(self._current, timing)
        self._started = time.monotonic() * 1000.0
        self._frozen_strokes = None
        self._timer.start()
        self.update()

    def step(self, delta: int) -> None:
        """Freeze the animation and show a fixed number of strokes."""
        self._timer.stop()
        if self._current is None:
            return
        base = self._frozen_strokes if self._frozen_strokes is not None else 0
        count = base + delta if delta else 0
        self._frozen_strokes = max(0, min(len(self._current.strokes), count))
        self.update()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.grab().save(str(path), "PNG" if path.suffix.lower() != ".jpg" else "JPG")

    # ---- painting ----

    def _tick(self) -> None:
        if self._timeline is None:
            self._timer.stop()
            return
        if (time.monotonic() * 1000.0 - self._started) >= self._timeline.total_ms:
            self._timer.stop()
        self.update()

    def _visible_current(self) -> Glyph | None:
        if self._current is None:
            return None
        if self._frozen_strokes is not None:
            return Glyph(self._current.strokes[: self._frozen_strokes])
        if self._timeline is None:
            return self._current
        return self._timeline.at(time.monotonic() * 1000.0 - self._started)

    def _pen(self, color: str, width: float, dashed: bool = False) -> QPen:
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    @staticmethod
    def _path(strokes) -> QPainterPath:
        path = QPainterPath()
        for stroke in strokes:
            if not stroke:
                continue
            path.moveTo(QPointF(*stroke[0]))
            for point in stroke[1:]:
                path.lineTo(QPointF(*point))
        return path

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        del event
        cfg = self._cfg
        background = str(cfg.get("canvas.background")) if cfg else "#fdfdf7"
        color = str(cfg.get("glyph.color")) if cfg else "#111111"
        ghost = str(cfg.get("glyph.outline_color")) if cfg else "#cccccc"
        width = float(cfg.get("glyph.stroke_width_px")) if cfg else 14.0
        grid_kind = str(cfg.get("canvas.grid")) if cfg else "none"
        grid_color = str(cfg.get("canvas.grid_color")) if cfg else "#e5ded0"

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(background))

        if grid_kind != "none":
            painter.setPen(self._pen(grid_color, 1.0, dashed=True))
            for line in self._sheet.grid_lines(grid_kind):
                painter.drawLine(QPointF(line.x1, line.y1), QPointF(line.x2, line.y2))

        if self._current is not None and cfg and bool(cfg.get("glyph.show_pending_outline")):
            painter.setPen(self._pen(ghost, width))
            painter.drawPath(self._path(self._current.strokes))

        painter.setPen(self._pen(color, width))
        for glyph, _text in self._done:
            painter.drawPath(self._path(glyph.strokes))
        visible = self._visible_current()
        if visible is not None:
            painter.drawPath(self._path(visible.strokes))
        painter.end()

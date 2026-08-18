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
    # Keys that affect the Sheet's geometry. Any other key is paint-time-only:
    # the canvas can just re-render existing content with the new value.
    _LAYOUT_KEYS = ("canvas.columns", "canvas.advance", "glyph.size_px", "canvas.wrap")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = None
        self._mode = "sheet"
        self._sheet = Sheet(columns=6, advance=1.15, size=240.0)
        # The third element is the archived glyph's outline contour, already
        # placed into pixel space at commit time (see commit()): once a
        # glyph is done it no longer has a live cell box to place a raw
        # outline with, so the QPainterPath is baked in while the box is
        # still known, rather than trying to keep box-per-entry around.
        self._done: list[tuple[Glyph, str, QPainterPath | None]] = []
        self._current: Glyph | None = None
        self._current_text = ""
        self._current_box = (0.0, 0.0, 0.0)
        self._current_outline: tuple[str, ...] | None = None
        self._timeline: Timeline | None = None
        self._started = 0.0
        self._frozen_strokes: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ---- configuration ----

    def configure(self, cfg) -> bool:
        """Apply cfg to the view.

        Rebuilds the Sheet -- clearing everything committed so far -- only
        when a layout-affecting key changed (columns/advance/size_px/wrap):
        keeping already-placed glyphs while resizing the carriage would leave
        them overlapping the new grid. Paint-time-only changes (colour, grid
        style, animation, ...) keep every committed glyph and the sheet's
        carriage position exactly as they were, so a hot reload can be
        watched taking effect on what is already on screen instead of wiping
        it.

        Returns whether the canvas was cleared, so callers can tell the user.
        """
        previous = self._cfg
        layout_changed = previous is None or any(
            previous.get(key) != cfg.get(key) for key in self._LAYOUT_KEYS
        )
        self._cfg = cfg
        self._mode = str(cfg.get("canvas.mode"))
        if layout_changed:
            self._sheet = Sheet(
                columns=int(cfg.get("canvas.columns")),
                advance=float(cfg.get("canvas.advance")),
                size=float(cfg.get("glyph.size_px")),
                wrap=bool(cfg.get("canvas.wrap")),
            )
            self._done.clear()
            self._current = None
        self.update()
        return layout_changed

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

    def commit(
        self,
        glyph: Glyph,
        text: str,
        ox: float,
        oy: float,
        size: float,
        outline: tuple[str, ...] | None = None,
    ) -> None:
        # Task 20's outline painter needs the cell box to place the typographic
        # contour, so it is kept rather than discarded even though the pixel
        # geometry pushed here is already baked into `glyph`. The outgoing
        # current's contour is placed *before* the box is overwritten below --
        # once overwritten, the old glyph's cell position is gone for good.
        if self._current is not None:
            done_contour = (
                self._outline_path(self._current_outline, *self._current_box)
                if self._current_outline
                else None
            )
            self._done.append((self._current, self._current_text, done_contour))
        self._current_box = (ox, oy, size)
        if self._mode == "single":
            self._done.clear()
        self._current = glyph
        self._current_text = text
        self._current_outline = outline
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

    def _outline_path(self, outline, ox, oy, size) -> QPainterPath:
        from ..render.svgpath import outline_to_box, parse_path  # noqa: PLC0415

        path = QPainterPath()
        for raw in outline:
            for seg in parse_path(raw):
                placed = outline_to_box(seg, ox, oy, size)
                if seg.kind == "M":
                    path.moveTo(QPointF(*placed.points[0]))
                elif seg.kind == "L":
                    path.lineTo(QPointF(*placed.points[0]))
                elif seg.kind == "Q":
                    path.quadTo(QPointF(*placed.points[0]), QPointF(*placed.points[1]))
                elif seg.kind == "C":
                    path.cubicTo(
                        QPointF(*placed.points[0]),
                        QPointF(*placed.points[1]),
                        QPointF(*placed.points[2]),
                    )
                elif seg.kind == "Z":
                    path.closeSubpath()
        return path

    def _paint_outline(self, painter, glyph, outline, box, color) -> None:
        """Fill the contour progressively: clip to it, then sweep along the median."""
        ox, oy, size = box
        contour = self._outline_path(outline, ox, oy, size)
        painter.save()
        painter.setClipPath(contour)
        painter.setPen(self._pen(color, size))  # a pen as wide as the glyph fills the clip
        painter.drawPath(self._path(glyph.strokes))
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        del event
        cfg = self._cfg
        background = str(cfg.get("canvas.background")) if cfg else "#fdfdf7"
        color = str(cfg.get("glyph.color")) if cfg else "#111111"
        ghost = str(cfg.get("glyph.outline_color")) if cfg else "#cccccc"
        width = float(cfg.get("glyph.stroke_width_px")) if cfg else 14.0
        grid_kind = str(cfg.get("canvas.grid")) if cfg else "none"
        grid_color = str(cfg.get("canvas.grid_color")) if cfg else "#e5ded0"
        style = str(cfg.get("glyph.style")) if cfg else "brush"

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
        for glyph, _text, contour in self._done:
            # A finished glyph is 100% revealed, so filling its whole
            # already-placed contour is exactly what the progressive
            # clip-and-sweep in _paint_outline would converge to.
            if style == "outline" and contour is not None:
                painter.fillPath(contour, QColor(color))
            else:
                painter.drawPath(self._path(glyph.strokes))

        visible = self._visible_current()
        if visible is not None:
            if style == "outline" and self._current_outline:
                painter.setPen(self._pen(ghost, width))
                painter.drawPath(self._outline_path(self._current_outline, *self._current_box))
                self._paint_outline(
                    painter, visible, self._current_outline, self._current_box, color
                )
            else:
                painter.drawPath(self._path(visible.strokes))
        painter.end()

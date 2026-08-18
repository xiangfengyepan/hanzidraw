"""The drawing surface: grid, finished glyphs, and the one being animated."""

from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..output.image import STROKE_NUMBER_FRACTION
from ..render.animator import Timeline, Timing
from ..render.glyph import Glyph
from ..render.sheet import Sheet

FRAME_MS = 16


class CanvasView(QWidget):
    #: Emitted when a character's outline data cannot be parsed and the brush was
    #: drawn instead. The window puts it in the status bar: a paintEvent has
    #: nowhere to report anything, which is why the parse happens at commit time.
    outline_failed = Signal(str)

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
        self._current_contour: QPainterPath | None = None
        self._timeline: Timeline | None = None
        self._started = 0.0
        self._frozen_strokes: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._sheet_size = QSize(1, 1)
        self._sync_size()

    # ---- geometry ----

    def _sync_size(self) -> None:
        """Keep the widget exactly as large as the sheet it paints.

        Spec §6: the sheet is ``columns * advance * size_px`` wide and the view
        *scrolls* when the window is narrower than that, rather than reflowing
        or clipping. A widget can never be smaller than its minimum size, so
        this is what makes the enclosing QScrollArea show scrollbars at the
        right moment -- and it has to be re-applied whenever the sheet grows
        (a new row, or an unwrapped carriage) or a layout reload rebuilds it.
        """
        width, height = self._sheet.size_px()
        size = QSize(max(1, math.ceil(width)), max(1, math.ceil(height)))
        if size == self._sheet_size:
            return
        self._sheet_size = size
        self.setMinimumSize(size)
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self._sheet_size

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
        self._sync_size()
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
            self._done.append((self._current, self._current_text, self._current_contour))
        self._current_box = (ox, oy, size)
        if self._mode == "single":
            self._done.clear()
        self._current = glyph
        self._current_text = text
        self._current_outline, self._current_contour = self._parse_outline(outline, ox, oy, size)
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
        self._sync_size()
        self.update()

    def _parse_outline(self, outline, ox: float, oy: float, size: float):
        """Turn outline path data into a placed contour, once, at commit time.

        ``parse_path`` raises on data it does not recognise, and a ``paintEvent``
        is the one place in this project where the "a failure is a message, not a
        traceback" rule cannot be honoured: there is nowhere to put a message and
        an exception leaves the QPainter unended. So the parse happens here, and a
        character whose outline is unusable falls back to the brush with a message.
        """
        if not outline:
            return (None, None)
        try:
            return (outline, self._outline_path(outline, ox, oy, size))
        except ValueError as exc:
            self.outline_failed.emit(
                f"outline data for {self._current_text or '?'} is unusable ({exc}); "
                f"drew brush strokes instead"
            )
            return (None, None)

    def next_cell(self) -> tuple[float, float, float]:
        """The (ox, oy, size) box the next glyph will occupy, without claiming it."""
        ox, oy = self._sheet.next_origin()
        return (ox, oy, self._sheet.size)

    def advance(self, glyph: Glyph, text: str):
        """Claim the next cell for a glyph that has actually been drawn."""
        placed = self._sheet.add(glyph, text)
        self._sync_size()
        return placed

    def undo(self) -> None:
        """Drop the last glyph *and* free its cell.

        The carriage belongs with the drawing: leaving the sheet to the caller
        (as this used to) meant undo only half worked if a caller forgot.
        """
        self._timer.stop()
        if self._current is not None:
            self._current = None
        elif self._done:
            self._done.pop()
        self._sheet.undo()
        self._current_outline = None
        self._current_contour = None
        self._sync_size()
        self.update()

    def clear(self) -> None:
        self._timer.stop()
        self._done.clear()
        self._current = None
        self._current_outline = None
        self._current_contour = None
        self._sheet.clear()
        self._sync_size()
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
        """Export the whole sheet, not the visible viewport.

        ``self.grab()`` only ever captured what fitted in the window, so every
        character past the third was missing from the saved image as well as
        from the screen. Painting into a sheet-sized QImage through the same
        ``_render`` the widget uses keeps the two from drifting apart.
        """
        image = QImage(self._sheet_size, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._render(painter, image.rect())
        painter.end()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(path), "PNG" if path.suffix.lower() != ".jpg" else "JPG"):
            # QImage.save() reports failure by returning False, so discarding it
            # let a failed write be announced as a success.
            raise OSError(f"could not write {path}")

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

    def _paint_stroke_numbers(self, painter: QPainter, color: str) -> None:
        """Number each stroke at its first median point.

        ``single`` mode only, per spec §6 -- a whole sheet of numbered practice
        cells is unreadable. The size fraction is shared with the SVG backend so
        the numbers look the same whichever renderer draws them.
        """
        if self._current is None:
            return
        size = self._current_box[2] or self._sheet.size
        font_px = max(6.0, size * STROKE_NUMBER_FRACTION)
        font = painter.font()
        font.setPixelSize(int(round(font_px)))
        painter.save()
        painter.setFont(font)
        painter.setPen(QPen(QColor(color)))
        for index, stroke in enumerate(self._current.strokes, start=1):
            if not stroke:
                continue
            x, y = stroke[0]
            painter.drawText(QPointF(x + font_px * 0.35, y - font_px * 0.35), str(index))
        painter.restore()

    def _paint_outline(self, painter, glyph, contour, size, color) -> None:
        """Fill the contour progressively: clip to it, then sweep along the median."""
        painter.save()
        painter.setClipPath(contour)
        painter.setPen(self._pen(color, size))  # a pen as wide as the glyph fills the clip
        painter.drawPath(self._path(glyph.strokes))
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._render(painter, self.rect())
        painter.end()

    def _render(self, painter: QPainter, rect) -> None:
        """Paint the sheet into ``rect``. Shared by paintEvent and save()."""
        cfg = self._cfg
        background = str(cfg.get("canvas.background")) if cfg else "#fdfdf7"
        color = str(cfg.get("glyph.color")) if cfg else "#111111"
        ghost = str(cfg.get("glyph.outline_color")) if cfg else "#cccccc"
        width = float(cfg.get("glyph.stroke_width_px")) if cfg else 14.0
        grid_kind = str(cfg.get("canvas.grid")) if cfg else "none"
        grid_color = str(cfg.get("canvas.grid_color")) if cfg else "#e5ded0"
        style = str(cfg.get("glyph.style")) if cfg else "brush"

        painter.fillRect(rect, QColor(background))

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
            if style == "outline" and self._current_contour is not None:
                painter.setPen(self._pen(ghost, width))
                painter.drawPath(self._current_contour)
                self._paint_outline(
                    painter, visible, self._current_contour, self._current_box[2], color
                )
            else:
                painter.drawPath(self._path(visible.strokes))

        if self._mode == "single" and cfg and bool(cfg.get("glyph.stroke_numbers")):
            self._paint_stroke_numbers(painter, color)

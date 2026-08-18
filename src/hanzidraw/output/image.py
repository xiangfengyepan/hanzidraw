"""Headless SVG (and, with Qt available, PNG) output."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from ..render.glyph import Point
from .base import Style


def _num(v: float) -> str:
    return f"{v:g}"


class SvgBackend:
    def __init__(self, width: int, height: int, background: str, style: Style) -> None:
        self.width = width
        self.height = height
        self.background = background
        self.style = style
        self._parts: list[str] = []

    def begin_glyph(self, ox: float, oy: float, size: float) -> None:
        self._parts.append(f'<g data-glyph="{_num(ox)},{_num(oy)},{_num(size)}">')

    def stroke(self, points: Sequence[Point]) -> None:
        pts = " ".join(f"{_num(x)},{_num(y)}" for x, y in points)
        self._parts.append(f'<polyline points="{pts}" />')

    def end_glyph(self) -> None:
        self._parts.append("</g>")

    def advance(self) -> None:  # the sheet owns layout; nothing to do here
        return

    def to_svg(self) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            f'<rect width="100%" height="100%" fill="{self.background}" />'
            f'<g fill="none" stroke="{self.style.color}" '
            f'stroke-width="{_num(self.style.width)}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        return head + "".join(self._parts) + "</g></svg>"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_svg(), encoding="utf-8")


def save_png(backend: SvgBackend, path: Path) -> None:
    """Rasterise the SVG with Qt. PNG output is the one image format that needs Qt.

    This is a headless code path: it must not depend on a display server being
    present. Qt's platform-plugin selection happens in native code the moment a
    QGuiApplication is constructed, and a missing display there is a C++-level
    abort that no Python ``except`` can catch — so the platform must be forced
    to "offscreen" *before* that happens, whenever the caller hasn't already
    chosen one. ``setdefault`` leaves an explicit ``QT_QPA_PLATFORM`` alone.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QByteArray  # noqa: PLC0415
        from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: PLC0415
        from PySide6.QtSvg import QSvgRenderer  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the install extras
        raise RuntimeError(
            "PNG output needs the GUI extra: pip install 'hanzidraw[gui]' (or use --format svg)"
        ) from exc

    if QGuiApplication.instance() is None:  # offscreen is enough for rasterising
        QGuiApplication([])
    renderer = QSvgRenderer(QByteArray(backend.to_svg().encode("utf-8")))
    image = QImage(backend.width, backend.height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"could not write {path}")

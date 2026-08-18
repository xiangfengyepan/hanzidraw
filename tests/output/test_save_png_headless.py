"""save_png must work with no display server at all — no DISPLAY, no
WAYLAND_DISPLAY, no QT_QPA_PLATFORM set by the caller. Qt's platform-plugin
choice is made once, in native code, the moment a QGuiApplication exists, and
is irreversible for the lifetime of the process. That makes an in-process test
dishonest (pytest-qt's own plugin already forces "offscreen" for the whole
test run, and once any QGuiApplication exists in this interpreter, further
platform switches are impossible). A subprocess with a scrubbed environment is
the only way to prove the real failure mode is gone.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

_SCRUB = ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM")


def _scrubbed_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _SCRUB:
        env.pop(key, None)
    return env


def test_save_png_works_headless_with_no_display_and_no_qt_platform_env(tmp_path):
    out = tmp_path / "probe.png"
    script = f"""
from pathlib import Path
from hanzidraw.output.base import Style, draw_glyph
from hanzidraw.output.image import SvgBackend, save_png
from hanzidraw.render.glyph import Glyph

backend = SvgBackend(50, 50, "#ffffff", Style(color="#000000", width=4.0))
draw_glyph(backend, Glyph((((0.0, 0.5), (1.0, 0.5)),)), ox=0.0, oy=0.0, size=50.0)
save_png(backend, Path({str(out)!r}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=_scrubbed_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert out.exists()
    assert out.stat().st_size > 0


def test_draw_command_writes_a_png_headless_with_no_display(tmp_path):
    db = tmp_path / "db.sqlite"
    out = tmp_path / "out.png"
    script = f"""
from pathlib import Path
from hanzidraw.data.store import Store
from hanzidraw import cli

store = Store.create(Path({str(db)!r}))
store.add_char(ord("十"), 1, 1, (((-512, 0), (512, 0)),), None)
store.finish()
store.close()

rc = cli.main(["draw", "十", "-o", {str(out)!r}, "--db", {str(db)!r}])
raise SystemExit(rc)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=_scrubbed_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert out.exists()
    assert out.stat().st_size > 0


def test_an_explicit_qt_qpa_platform_is_left_untouched(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    pytest.importorskip("PySide6.QtSvg")
    from hanzidraw.output.base import Style, draw_glyph
    from hanzidraw.output.image import SvgBackend, save_png
    from hanzidraw.render.glyph import Glyph

    backend = SvgBackend(50, 50, "#ffffff", Style(color="#000000", width=4.0))
    draw_glyph(backend, Glyph((((0.0, 0.5), (1.0, 0.5)),)), ox=0.0, oy=0.0, size=50.0)
    save_png(backend, tmp_path / "explicit.png")

    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"

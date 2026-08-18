import pytest

from hanzidraw.config import load_config
from hanzidraw.render.glyph import Glyph

pytest.importorskip("PySide6")

from hanzidraw.output.base import draw_glyph  # noqa: E402
from hanzidraw.output.canvas import CanvasBackend  # noqa: E402
from hanzidraw.ui.canvasview import CanvasView  # noqa: E402

GLYPH = Glyph((((0.0, 0.5), (1.0, 0.5)), ((0.5, 0.0), (0.5, 1.0))))


@pytest.fixture
def view(qtbot, tmp_path):
    view = CanvasView()
    view.configure(load_config(tmp_path / "none.toml"))
    qtbot.addWidget(view)
    return view


def test_commit_adds_a_glyph_and_starts_animating(view):
    view.commit(GLYPH, "十", ox=0.0, oy=0.0, size=100.0)
    assert view.glyph_count == 1
    assert view.is_animating


def test_undo_and_clear_change_the_glyph_count(view):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    view.commit(GLYPH, "一", 100.0, 0.0, 100.0)
    view.undo()
    assert view.glyph_count == 1
    view.clear()
    assert view.glyph_count == 0
    assert not view.is_animating


def test_animation_finishes_and_the_glyph_stays(view, qtbot):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    qtbot.waitUntil(lambda: not view.is_animating, timeout=5000)
    assert view.glyph_count == 1


def test_disabled_animation_shows_the_glyph_immediately(qtbot, tmp_path):
    (tmp_path / "c.toml").write_text("[glyph.animation]\nenabled = false\n", encoding="utf-8")
    view = CanvasView()
    view.configure(load_config(tmp_path / "c.toml"))
    qtbot.addWidget(view)
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    assert not view.is_animating


def test_single_mode_keeps_only_the_latest_glyph(view):
    view.set_mode("single")
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    view.commit(GLYPH, "一", 0.0, 0.0, 100.0)
    assert view.glyph_count == 1


def test_replay_restarts_the_animation(view, qtbot):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    qtbot.waitUntil(lambda: not view.is_animating, timeout=5000)
    view.replay()
    assert view.is_animating


def test_step_reveals_one_stroke_at_a_time(view):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    view.step(0)  # stop animating, show nothing
    assert not view.is_animating
    view.step(1)
    view.step(1)
    view.step(1)  # past the end is harmless
    assert view.glyph_count == 1


def test_save_writes_a_png(view, tmp_path):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    out = tmp_path / "sheet.png"
    view.save(out)
    assert out.exists() and out.stat().st_size > 0


def test_canvas_backend_forwards_pushed_strokes_to_the_view(view):
    backend = CanvasBackend(view, text="十")
    draw_glyph(backend, GLYPH, ox=10.0, oy=10.0, size=100.0)
    assert view.glyph_count == 1


def test_render_produces_a_non_blank_image(view):
    view.resize(300, 300)
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    view.step(9)  # reveal everything without waiting
    image = view.grab().toImage()
    colours = {image.pixel(x, y) for x in range(0, 300, 25) for y in range(0, 300, 25)}
    assert len(colours) > 1  # something was drawn on the background

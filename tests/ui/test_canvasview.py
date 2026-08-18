import pytest

from hanzidraw.config import load_config
from hanzidraw.render.glyph import Glyph

pytest.importorskip("PySide6")

from hanzidraw.output.base import draw_glyph  # noqa: E402
from hanzidraw.output.canvas import CanvasBackend  # noqa: E402
from hanzidraw.ui.canvasview import CanvasView  # noqa: E402

GLYPH = Glyph((((0.0, 0.5), (1.0, 0.5)), ((0.5, 0.0), (0.5, 1.0))))


def _ink_rgb(cfg) -> tuple[int, int, int]:
    """The configured ink colour as an (r, g, b) tuple, for exact pixel matching."""
    hex_colour = str(cfg.get("glyph.color")).lstrip("#")
    return tuple(int(hex_colour[i : i + 2], 16) for i in (0, 2, 4))


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


def test_step_reveals_one_stroke_at_a_time(qtbot, tmp_path):
    (tmp_path / "c.toml").write_text("[glyph.animation]\nenabled = false\n", encoding="utf-8")
    cfg = load_config(tmp_path / "c.toml")
    ink_rgb = _ink_rgb(cfg)

    # Three horizontal strokes, well separated in pixel space (already-placed
    # geometry, per the canvas's contract) so each one can be checked
    # independently by sampling a single pixel at its centre.
    three_stroke = Glyph(
        (
            ((20.0, 20.0), (180.0, 20.0)),
            ((20.0, 100.0), (180.0, 100.0)),
            ((20.0, 180.0), (180.0, 180.0)),
        )
    )
    sample_points = [(100, 20), (100, 100), (100, 180)]

    def revealed_stroke_count(rendered: CanvasView) -> int:
        image = rendered.grab().toImage()
        revealed = 0
        for x, y in sample_points:
            colour = image.pixelColor(x, y)
            if (colour.red(), colour.green(), colour.blue()) != ink_rgb:
                break  # strokes reveal in order; stop at the first unrevealed one
            revealed += 1
        return revealed

    view = CanvasView()
    view.configure(cfg)
    qtbot.addWidget(view)
    view.resize(200, 200)
    view.commit(three_stroke, "三", 0.0, 0.0, 100.0)
    assert not view.is_animating  # animation disabled

    view.step(0)  # stop animating, show nothing
    assert not view.is_animating
    assert revealed_stroke_count(view) == 0

    view.step(1)
    assert revealed_stroke_count(view) == 1

    view.step(1)
    assert revealed_stroke_count(view) == 2

    view.step(1)
    assert revealed_stroke_count(view) == 3

    view.step(1)  # past the end is harmless: stays clamped, not growing or wrapping
    assert revealed_stroke_count(view) == 3
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


def test_render_produces_a_non_blank_image(view, qtbot, tmp_path):
    cfg = load_config(tmp_path / "none.toml")
    ink_rgb = _ink_rgb(cfg)

    def ink_pixel_count(rendered: CanvasView) -> int:
        image = rendered.grab().toImage()
        count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if (colour.red(), colour.green(), colour.blue()) == ink_rgb:
                    count += 1
        return count

    # Two non-overlapping strokes, already-placed pixel geometry, at the same
    # size and stroke width: the second glyph is the first plus one more
    # stroke, so a real paint must show meaningfully more ink, not just the
    # background and grid colours a blank render would already produce.
    one_stroke = Glyph((((20.0, 100.0), (280.0, 100.0)),))
    two_stroke = Glyph((((20.0, 100.0), (280.0, 100.0)), ((20.0, 200.0), (280.0, 200.0))))

    view.resize(300, 300)
    view.commit(one_stroke, "一", 0.0, 0.0, 100.0)
    view.step(9)  # reveal everything without waiting
    one_stroke_ink = ink_pixel_count(view)
    assert one_stroke_ink > 0  # something beyond background/grid was drawn

    two_stroke_view = CanvasView()
    two_stroke_view.configure(cfg)
    qtbot.addWidget(two_stroke_view)
    two_stroke_view.resize(300, 300)
    two_stroke_view.commit(two_stroke, "十", 0.0, 0.0, 100.0)
    two_stroke_view.step(9)
    two_stroke_ink = ink_pixel_count(two_stroke_view)

    # Ink pixels must scale with the geometry, not just be "more than one
    # colour" — a render that painted the background and grid but no strokes
    # at all would otherwise pass undetected.
    assert two_stroke_ink > one_stroke_ink * 1.5


def test_configure_keeps_committed_glyphs_when_only_paint_properties_change(view, tmp_path):
    # Regression test: a colour-only config reload used to wipe the canvas,
    # which defeats the whole point of hot reload -- the user changes the
    # colour to see it applied, not to lose what they just drew.
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    assert view.glyph_count == 1

    (tmp_path / "paint.toml").write_text('[glyph]\ncolor = "#ff0000"\n', encoding="utf-8")
    cleared = view.configure(load_config(tmp_path / "paint.toml"))

    assert cleared is False
    assert view.glyph_count == 1


def test_configure_clears_and_reports_it_when_layout_changes(view, tmp_path):
    # Layout keys (columns/advance/size_px/wrap) still have to clear: keeping
    # glyphs placed under the old geometry would leave them overlapping the
    # rebuilt grid, which is worse than losing the sheet.
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    assert view.glyph_count == 1

    (tmp_path / "layout.toml").write_text("[glyph]\nsize_px = 80\n", encoding="utf-8")
    cleared = view.configure(load_config(tmp_path / "layout.toml"))

    assert cleared is True
    assert view.glyph_count == 0


NUMBERED = Glyph((((20.0, 60.0), (180.0, 60.0)), ((20.0, 140.0), (180.0, 140.0))))


def _render_bytes(qtbot, tmp_path, *, mode, numbers):
    name = f"{mode}-{numbers}.toml"
    (tmp_path / name).write_text(
        f"[glyph]\nstroke_numbers = {str(numbers).lower()}\n"
        f'[glyph.animation]\nenabled = false\n[canvas]\nmode = "{mode}"\n',
        encoding="utf-8",
    )
    view = CanvasView()
    view.configure(load_config(tmp_path / name))
    qtbot.addWidget(view)
    view.commit(NUMBERED, "十", 0.0, 0.0, 240.0)
    return bytes(view.grab().toImage().constBits())


def test_stroke_numbers_are_painted_in_single_mode_and_only_there(qtbot, tmp_path):
    # glyph.stroke_numbers was documented and never implemented in either
    # renderer. Spec §6 scopes it to `single` mode.
    assert _render_bytes(qtbot, tmp_path, mode="single", numbers=True) != _render_bytes(
        qtbot, tmp_path, mode="single", numbers=False
    )
    assert _render_bytes(qtbot, tmp_path, mode="sheet", numbers=True) == _render_bytes(
        qtbot, tmp_path, mode="sheet", numbers=False
    )

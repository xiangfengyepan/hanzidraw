import pytest

pytest.importorskip("PySide6")

from hanzidraw.config import load_config  # noqa: E402
from hanzidraw.render.glyph import Glyph  # noqa: E402
from hanzidraw.ui.canvasview import CanvasView  # noqa: E402

GLYPH = Glyph((((10.0, 50.0), (90.0, 50.0)),))
OUTLINE = ("M 100 500 L 900 500 L 900 560 L 100 560 Z",)


@pytest.fixture
def view(qtbot, tmp_path):
    (tmp_path / "c.toml").write_text(
        '[glyph]\nstyle = "outline"\n[glyph.animation]\nenabled = false\n', encoding="utf-8"
    )
    view = CanvasView()
    view.configure(load_config(tmp_path / "c.toml"))
    view.resize(200, 200)
    qtbot.addWidget(view)
    return view


def test_outline_style_paints_without_outline_data(view):
    """A glyph with no outline must still draw — falling back to the brush."""
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0)
    # The canvas is never smaller than the sheet it paints (it is scrolled, not
    # squeezed), so resize(200, 200) is a lower bound, not the widget's size.
    assert view.grab().toImage().width() == view.width()
    assert view.width() >= 200


def test_outline_style_uses_the_outline_when_it_is_supplied(view):
    view.commit(GLYPH, "十", 0.0, 0.0, 100.0, outline=OUTLINE)
    image = view.grab().toImage()
    colours = {image.pixel(x, y) for x in range(0, 200, 10) for y in range(0, 200, 10)}
    assert len(colours) > 1


def test_brush_and_outline_styles_render_differently(qtbot, tmp_path):
    def render(style: str) -> bytes:
        (tmp_path / f"{style}.toml").write_text(
            f'[glyph]\nstyle = "{style}"\n[glyph.animation]\nenabled = false\n', encoding="utf-8"
        )
        widget = CanvasView()
        widget.configure(load_config(tmp_path / f"{style}.toml"))
        widget.resize(200, 200)
        qtbot.addWidget(widget)
        widget.commit(GLYPH, "十", 0.0, 0.0, 100.0, outline=OUTLINE)
        image = widget.grab().toImage()
        return bytes(image.constBits())

    assert render("brush") != render("outline")

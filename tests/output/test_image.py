from hanzidraw.output.base import Style, draw_glyph
from hanzidraw.output.image import SvgBackend
from hanzidraw.render.glyph import Glyph

GLYPH = Glyph((((0.0, 0.5), (1.0, 0.5)),))


def _svg():
    backend = SvgBackend(
        width=200, height=200, background="#ffffff", style=Style(color="#112233", width=8.0)
    )
    draw_glyph(backend, GLYPH, ox=0.0, oy=0.0, size=200.0)
    return backend.to_svg()


def test_svg_has_a_root_element_with_the_requested_size():
    svg = _svg()
    assert svg.startswith("<svg")
    assert 'width="200"' in svg and 'height="200"' in svg


def test_svg_paints_the_background_and_the_stroke_style():
    svg = _svg()
    assert "#ffffff" in svg
    assert "#112233" in svg
    assert 'stroke-width="8' in svg
    assert 'stroke-linecap="round"' in svg


def test_svg_contains_one_polyline_per_stroke_with_real_coordinates():
    svg = _svg()
    assert svg.count("<polyline") == 1
    assert "0,100" in svg and "200,100" in svg


def test_svg_output_is_byte_stable():
    assert _svg() == _svg()


def test_save_writes_the_file(tmp_path):
    backend = SvgBackend(100, 100, "#fff", Style("#000", 4.0))
    draw_glyph(backend, GLYPH, 0.0, 0.0, 100.0)
    out = tmp_path / "a.svg"
    backend.save(out)
    assert out.read_text(encoding="utf-8").startswith("<svg")

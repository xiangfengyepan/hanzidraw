from hanzidraw.data.store import Store
from hanzidraw.output.base import draw_glyph, load_glyph
from hanzidraw.render.glyph import Glyph


class RecordingBackend:
    def __init__(self):
        self.events = []

    def begin_glyph(self, ox, oy, size):
        self.events.append(("begin", ox, oy, size))

    def stroke(self, points):
        self.events.append(("stroke", tuple(points)))

    def end_glyph(self):
        self.events.append(("end",))

    def advance(self):
        self.events.append(("advance",))


def test_draw_glyph_emits_begin_then_every_stroke_then_end():
    backend = RecordingBackend()
    glyph = Glyph((((0.0, 0.0), (1.0, 0.0)), ((0.0, 1.0), (1.0, 1.0))))
    draw_glyph(backend, glyph, ox=10.0, oy=20.0, size=100.0)
    kinds = [e[0] for e in backend.events]
    assert kinds == ["begin", "stroke", "stroke", "end"]
    assert backend.events[1][1][0] == (10.0, 20.0)
    assert backend.events[1][1][1] == (110.0, 20.0)


def test_draw_glyph_with_no_strokes_still_brackets_the_glyph():
    backend = RecordingBackend()
    draw_glyph(backend, Glyph(()), 0.0, 0.0, 10.0)
    assert [e[0] for e in backend.events] == ["begin", "end"]


def test_load_glyph_reads_medians_from_the_store(tmp_path):
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 1, 1, (((-512, 0), (512, 0)),), None)
    store.finish()
    glyph = load_glyph(store, ord("十"))
    assert glyph.strokes[0][0] == (0.0, 0.5)

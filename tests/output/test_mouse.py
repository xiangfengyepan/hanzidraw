import threading

import pytest

from hanzidraw.output.base import draw_glyph
from hanzidraw.output.mouse import MouseAbort, MouseBackend
from hanzidraw.render.glyph import Glyph

GLYPH = Glyph((((0.0, 0.0), (1.0, 0.0)), ((0.0, 1.0), (1.0, 1.0))))


class FakePointer:
    def __init__(self):
        self.position = (0.0, 0.0)
        self.events = []

    def move_to(self, x, y):
        self.position = (x, y)
        self.events.append(("move", x, y))

    def press(self):
        self.events.append(("press",))

    def release(self):
        self.events.append(("release",))


def _backend(pointer, **kw):
    kw.setdefault("sleep", lambda _s: None)
    return MouseBackend(pointer, **kw)


def test_each_stroke_is_a_press_moves_release_sequence():
    pointer = FakePointer()
    draw_glyph(_backend(pointer), GLYPH, 0.0, 0.0, 100.0)
    kinds = [e[0] for e in pointer.events]
    assert kinds.count("press") == 2
    assert kinds.count("release") == 2
    # Ruling A (coordinator, task-18): the brief's original assertion had this
    # backwards. A stroke must position the pointer before pressing -- else it
    # drags a stray line from wherever the cursor happened to be -- so "move"
    # comes first, matching test_the_pointer_moves_to_the_start_before_pressing
    # below and the reference stroke() implementation.
    assert kinds.index("move") < kinds.index("press") < kinds.index("release")


def test_the_pointer_moves_to_the_start_before_pressing():
    pointer = FakePointer()
    draw_glyph(_backend(pointer), GLYPH, 10.0, 20.0, 100.0)
    assert pointer.events[0] == ("move", 10.0, 20.0)
    assert pointer.events[1] == ("press",)


def test_scale_multiplies_the_geometry():
    pointer = FakePointer()
    draw_glyph(_backend(pointer, scale=2.0), GLYPH, 0.0, 0.0, 100.0)
    assert ("move", 200.0, 0.0) in pointer.events


def test_clamping_keeps_points_inside_the_screen():
    pointer = FakePointer()
    draw_glyph(_backend(pointer, clamp=(0.0, 0.0, 50.0, 50.0)), GLYPH, 0.0, 0.0, 100.0)
    assert all(
        x <= 50.0 and y <= 50.0 for kind, x, y in [e for e in pointer.events if e[0] == "move"]
    )


def test_a_set_abort_event_stops_the_draw_and_releases_the_button():
    pointer = FakePointer()
    abort = threading.Event()
    abort.set()
    with pytest.raises(MouseAbort):
        draw_glyph(_backend(pointer, abort=abort), GLYPH, 0.0, 0.0, 100.0)
    assert pointer.events[-1] == ("release",)


def test_passing_the_deadline_aborts():
    pointer = FakePointer()
    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0])
    with pytest.raises(MouseAbort) as exc:
        draw_glyph(
            _backend(pointer, deadline_ms=1000, monotonic=lambda: next(clock)),
            GLYPH,
            0.0,
            0.0,
            100.0,
        )
    assert "took too long" in str(exc.value)
    assert pointer.events[-1] == ("release",)


def test_the_user_moving_the_physical_mouse_aborts():
    class Hijacked(FakePointer):
        def __init__(self):
            super().__init__()
            self._moves = 0

        def move_to(self, x, y):
            super().move_to(x, y)
            self._moves += 1
            if self._moves == 2:
                self.position = (9999.0, 9999.0)  # the user grabbed the mouse

    pointer = Hijacked()
    with pytest.raises(MouseAbort) as exc:
        draw_glyph(_backend(pointer), GLYPH, 0.0, 0.0, 100.0)
    assert "moved" in str(exc.value)
    assert pointer.events[-1] == ("release",)


def test_an_unexpected_exception_from_the_pointer_still_releases_the_button():
    # Ruling: the button-release-on-every-path property must also be covered
    # by an exception that is not one of the three abort routes -- something
    # raised from inside the pointer itself, e.g. the real backend hitting an
    # OS-level error mid-stroke. stroke()'s `finally` must release regardless.
    class Flaky(FakePointer):
        def __init__(self):
            super().__init__()
            self._moves = 0

        def move_to(self, x, y):
            self._moves += 1
            if self._moves == 2:
                raise RuntimeError("boom")
            super().move_to(x, y)

    pointer = Flaky()
    with pytest.raises(RuntimeError, match="boom"):
        draw_glyph(_backend(pointer), GLYPH, 0.0, 0.0, 100.0)
    assert pointer.events == [("move", 0.0, 0.0), ("press",), ("release",)]


def test_a_failing_release_does_not_mask_an_in_flight_abort():
    # Finding 1 (coordinator, task-18 review): if release() itself raises
    # while a MouseAbort is already unwinding, the release failure must not
    # replace it -- the window's `except MouseAbort` has to keep catching it
    # -- and `_down` must still be reset so the backend doesn't believe the
    # button is stuck down.
    class BrokenRelease(FakePointer):
        def release(self):
            raise RuntimeError("hardware release failed")

    pointer = BrokenRelease()
    abort = threading.Event()
    abort.set()
    backend = _backend(pointer, abort=abort)
    with pytest.raises(MouseAbort) as exc:
        draw_glyph(backend, GLYPH, 0.0, 0.0, 100.0)
    assert isinstance(exc.value.__cause__, RuntimeError)  # chained, not swallowed
    assert backend._down is False


def test_a_single_point_stroke_still_honours_a_preset_abort_event():
    # Finding 2: a stroke of 0 or 1 points never entered the `points[1:]`
    # loop, so it never called _check() at all -- structurally defeating two
    # of the three ways out. Single-point strokes are real: glyph_from_em
    # filters only empty strokes, not single-point ones.
    pointer = FakePointer()
    abort = threading.Event()
    abort.set()
    glyph = Glyph((((0.5, 0.5),),))
    with pytest.raises(MouseAbort):
        draw_glyph(_backend(pointer, abort=abort), glyph, 0.0, 0.0, 100.0)
    assert pointer.events[-1] == ("release",)


def test_a_single_point_stroke_still_honours_an_exceeded_deadline():
    pointer = FakePointer()
    clock = iter([0.0, 100.0, 100.0])
    glyph = Glyph((((0.5, 0.5),),))
    with pytest.raises(MouseAbort) as exc:
        draw_glyph(
            _backend(pointer, deadline_ms=1000, monotonic=lambda: next(clock)),
            glyph,
            0.0,
            0.0,
            100.0,
        )
    assert "took too long" in str(exc.value)
    assert pointer.events[-1] == ("release",)


def test_a_fully_clamped_stroke_reports_rather_than_pressing():
    # Finding 4: when clamp_to_screen collapses every point of a stroke onto
    # the same pixel, the glyph lies entirely outside the drawable area.
    # Pressing and releasing there would draw nothing while looking like it
    # succeeded, so this must report instead of touching the pointer at all.
    pointer = FakePointer()
    backend = _backend(pointer, clamp=(0.0, 0.0, 10.0, 10.0))
    glyph = Glyph((((5.0, 5.0), (6.0, 5.0)),))
    with pytest.raises(MouseAbort) as exc:
        draw_glyph(backend, glyph, 1000.0, 1000.0, 100.0)
    assert "outside the screen" in str(exc.value)
    assert pointer.events == []


def test_scale_is_applied_before_clamp_so_clamping_stays_a_hard_guarantee():
    # Minor: if clamp ran before scale, a point already inside the box
    # (40 < 50) would escape it after being doubled (80 > 50). Each existing
    # scale/clamp test leaves the other at its default, so an accidental
    # ordering swap would still pass the rest of the suite; this closes that
    # gap by exercising both together.
    pointer = FakePointer()
    glyph = Glyph((((0.2, 0.0), (0.4, 0.0)),))
    draw_glyph(
        _backend(pointer, scale=2.0, clamp=(0.0, 0.0, 50.0, 50.0)),
        glyph,
        0.0,
        0.0,
        100.0,
    )
    moves = [(x, y) for _kind, x, y in [e for e in pointer.events if e[0] == "move"]]
    assert all(x <= 50.0 for x, _y in moves)
    assert moves[-1] == (50.0, 0.0)  # 40 * scale(2) = 80, clamped down to the edge


def test_clamp_caps_at_the_screens_last_addressable_pixel_not_one_past_it():
    # Coordinator correction (task-18 second review): a screen's right edge
    # for cursor placement is its *last addressable pixel column*, not the
    # geometric boundary one past it. For a 1920-wide screen that column is
    # 1919 (valid x range 0..1919) -- Qt's QRect.right() reports exactly
    # that (x() + width() - 1). A prior fix mistakenly added 1 to "correct"
    # for QRect's continuous-geometry convention, which would let a clamped
    # cursor land at column 1920: off the real screen, and onto an adjacent
    # monitor on a multi-monitor desktop. Pin the bound here so it can't be
    # "fixed" back to +1 without a test noticing.
    pointer = FakePointer()
    screen_1920x1080 = (0.0, 0.0, 1919.0, 1079.0)
    glyph = Glyph((((0.0, 0.0), (5.0, 0.0)),))  # far beyond the right edge once placed
    draw_glyph(_backend(pointer, clamp=screen_1920x1080), glyph, 0.0, 0.0, 1000.0)
    xs = [x for _kind, x, _y in [e for e in pointer.events if e[0] == "move"]]
    assert max(xs) == 1919.0
    assert max(xs) != 1920.0


def test_end_glyph_does_not_touch_the_pointer():
    # Ruling B (coordinator, task-18): advance() was removed from the Backend
    # protocol entirely (it had no callers anywhere in the codebase), and
    # MouseBackend deliberately does not grow one back. Only end_glyph()
    # remains to check here.
    pointer = FakePointer()
    backend = _backend(pointer)
    backend.end_glyph()
    assert pointer.events == []


def test_listen_for_abort_is_a_no_op_without_pynput(monkeypatch):
    import builtins

    from hanzidraw.output import mouse

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "pynput":
            raise ImportError("no pynput")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    stop = mouse.listen_for_abort(MouseBackend(FakePointer(), sleep=lambda _s: None))
    stop()  # must not raise

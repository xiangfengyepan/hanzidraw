"""Draw into another application by synthesizing pointer input.

A synthetic pointer that will not stop is hostile, so every draw has three
independent ways out: an abort event, a deadline, and noticing that the pointer
is not where we last put it (the user grabbed the mouse).

Glyphs are drawn at absolute canvas coordinates -- the same ``ox``/``oy``/
``size`` box every other backend receives -- not relative to wherever the
pointer currently sits. See the note in the Task 18 report about revisiting
this once real-pointer behaviour has been checked against a paint program.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from ..render.glyph import Point


class MouseAbort(Exception):
    """The draw was stopped before it finished."""


class Pointer(Protocol):
    position: tuple[float, float]

    def move_to(self, x: float, y: float) -> None: ...
    def press(self) -> None: ...
    def release(self) -> None: ...


class PynputPointer:
    """The real pointer. Imported lazily so the core never needs pynput."""

    def __init__(self, button: str = "left") -> None:
        from pynput.mouse import Button, Controller  # noqa: PLC0415

        self._controller = Controller()
        buttons = {"left": Button.left, "right": Button.right, "middle": Button.middle}
        self._button = buttons[button]

    @property
    def position(self) -> tuple[float, float]:
        return tuple(self._controller.position)

    def move_to(self, x: float, y: float) -> None:
        self._controller.position = (int(round(x)), int(round(y)))

    def press(self) -> None:
        self._controller.press(self._button)

    def release(self) -> None:
        self._controller.release(self._button)


class MouseBackend:
    def __init__(
        self,
        pointer: Pointer,
        *,
        scale: float = 1.0,
        step_delay_ms: float = 4.0,
        deadline_ms: float = 8000.0,
        clamp: tuple[float, float, float, float] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        abort: threading.Event | None = None,
        drift_px: float = 40.0,
    ) -> None:
        self._p = pointer
        self._scale = scale
        self._delay = step_delay_ms / 1000.0
        self._deadline_ms = deadline_ms
        self._clamp = clamp
        self._sleep = sleep
        self._monotonic = monotonic
        self._abort = abort or threading.Event()
        self._drift = drift_px
        self._down = False
        self._started = 0.0
        self._expected: Point = (0.0, 0.0)

    # ---- Backend protocol ----

    def begin_glyph(self, ox: float, oy: float, size: float) -> None:
        del ox, oy, size
        self._started = self._monotonic()

    def stroke(self, points: Sequence[Point]) -> None:
        if not points:
            self._check()  # a degenerate stroke still owes the caller an abort/deadline check
            return
        transformed = [self._transform(point) for point in points]
        if len(transformed) > 1 and len(set(transformed)) == 1:
            # scale/clamp collapsed every point onto the same pixel: the
            # glyph (or this stroke of it) lies entirely outside the drawable
            # area. Pressing and releasing there would draw nothing while
            # looking like it succeeded, so report it instead.
            raise MouseAbort("the glyph fell outside the screen bounds")
        in_flight: BaseException | None = None
        try:
            self._move(transformed[0])
            self._p.press()
            self._down = True
            rest = transformed[1:]
            if not rest:
                # a single-point stroke never enters the loop below, but it
                # still owes the abort event and the deadline a look.
                self._check()
            for point in rest:
                self._check()
                self._move(point)
                if self._delay:
                    self._sleep(self._delay)
        except BaseException as exc:
            in_flight = exc
            raise
        finally:
            if self._down:
                self._down = False  # reset regardless of what release() does below
                try:
                    self._p.release()
                except Exception as release_exc:
                    if in_flight is None:
                        raise
                    # An abort (or any other exception) is already unwinding;
                    # let *that* be what the caller sees so "the user aborted"
                    # and "the hardware release failed" stay distinguishable.
                    # Chain the release failure onto it instead of replacing it.
                    in_flight.__cause__ = release_exc

    def end_glyph(self) -> None:
        return

    # ---- internals ----

    def stop(self) -> None:
        """Ask an in-progress draw to abort (safe to call from another thread)."""
        self._abort.set()

    def _transform(self, point: Point) -> Point:
        x, y = point[0] * self._scale, point[1] * self._scale
        if self._clamp:
            x0, y0, x1, y1 = self._clamp
            x = max(x0, min(x1, x))
            y = max(y0, min(y1, y))
        return (x, y)

    def _move(self, point: Point) -> None:
        self._p.move_to(point[0], point[1])
        self._expected = point
        self._check_drift()

    def _check(self) -> None:
        if self._abort.is_set():
            raise MouseAbort("draw aborted")
        if (self._monotonic() - self._started) * 1000.0 > self._deadline_ms:
            raise MouseAbort("draw took too long and was stopped")

    def _check_drift(self) -> None:
        where = self._p.position
        dx = abs(where[0] - self._expected[0])
        dy = abs(where[1] - self._expected[1])
        if max(dx, dy) > self._drift:
            raise MouseAbort("the pointer moved on its own; draw stopped")


def listen_for_abort(backend: MouseBackend, key: str = "esc"):
    """Temporary global listener, alive only while a draw runs. Returns a stop callable."""
    try:
        from pynput import keyboard  # noqa: PLC0415
    except ImportError:
        return lambda: None

    def on_press(pressed) -> None:
        if pressed == keyboard.Key.esc:
            backend.stop()

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    return listener.stop

"""The main window: key routing, commit handling, status messages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QMainWindow, QScrollArea, QVBoxLayout, QWidget

from ..config import data_dir, load_config
from ..data.glyphs import load_glyph
from ..data.store import Store
from ..ime.learn import Learn
from ..ime.session import Key, Session
from ..ime.sources import CharSource, PhraseSource
from ..output.base import draw_glyph
from ..output.canvas import CanvasBackend
from ..output.mouse import MouseAbort
from .candidatebar import CandidateBar
from .canvasview import CanvasView

_NAMED = {
    int(Qt.Key.Key_Space): "space",
    int(Qt.Key.Key_Return): "enter",
    int(Qt.Key.Key_Enter): "enter",
    int(Qt.Key.Key_Backspace): "backspace",
    int(Qt.Key.Key_Escape): "escape",
    int(Qt.Key.Key_Left): "left",
    int(Qt.Key.Key_Right): "right",
    int(Qt.Key.Key_Tab): "tab",
    int(Qt.Key.Key_PageUp): "pageup",
    int(Qt.Key.Key_PageDown): "pagedown",
    int(Qt.Key.Key_Minus): "minus",
    int(Qt.Key.Key_Equal): "equal",
    int(Qt.Key.Key_Apostrophe): "apostrophe",
    int(Qt.Key.Key_F2): "f2",
    int(Qt.Key.Key_BracketLeft): "bracketleft",
    int(Qt.Key.Key_BracketRight): "bracketright",
    int(Qt.Key.Key_Period): "period",
}


def key_from_event(event: QKeyEvent) -> Key | None:
    ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
    code = int(event.key())  # PySide6 hands back a plain int, not the enum
    if code in _NAMED:
        return Key(_NAMED[code], ctrl)
    if int(Qt.Key.Key_A) <= code <= int(Qt.Key.Key_Z):
        return Key(chr(code).lower(), ctrl)
    if int(Qt.Key.Key_1) <= code <= int(Qt.Key.Key_9):
        return Key(chr(code), ctrl)
    return None


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: Store,
        cfg,
        learn_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("hanzidraw")
        self._store = store
        self._learn_path = learn_path or data_dir() / "learn.json"
        self.canvas = CanvasView()
        # Spec §6: the sheet is `columns * advance * size_px` wide and the view
        # SCROLLS when the window is narrower than that, and never reflows on
        # resize -- hence widgetResizable(False), which leaves the canvas at its
        # own sheet-driven size instead of squeezing it into the viewport.
        # NoFocus matters: a focusable scroll area would swallow the arrow,
        # Tab and PageUp/PageDown keys the candidate bar needs.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setWidget(self.canvas)
        self.canvas.outline_failed.connect(self.status)
        self.bar = CandidateBar()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll, stretch=1)
        layout.addWidget(self.bar)
        self.setCentralWidget(central)
        self.apply_config(cfg)  # builds the Learn store and the Session
        self.canvas.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---- configuration ----

    def apply_config(self, cfg) -> None:
        self._cfg = cfg
        self._canvas_cleared = self.canvas.configure(cfg)
        self._learn = Learn(self._learn_path, enabled=bool(cfg.get("ime.learn")))
        sources = [CharSource(self._store)]
        if bool(cfg.get("ime.phrases")):
            sources.insert(0, PhraseSource(self._store))
        self._session = Session(
            sources,
            page_size=int(cfg.get("ime.page_size")),
            learn=self._learn,
            max_candidates=int(cfg.get("ime.max_candidates")),
        )
        on_top = bool(cfg.get("canvas.always_on_top"))
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != on_top:
            # Qt re-parents and *hides* an already-created widget when its window
            # flags change. Calling this on every reload therefore made the window
            # vanish for good -- there is no tray icon and no way back, and the
            # drawn sheet went with it. Change the flag only when the value really
            # changed, and show the window again if it was on screen.
            was_visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
            if was_visible:
                self.show()
        messages = list(cfg.errors) + list(cfg.warnings)
        if (
            cfg.get("glyph.style") == "outline"
            and self._store.get_meta("build_medians_only") == "1"
        ):
            messages.insert(
                0,
                "glyph.style = outline needs outlines, but this database is medians-only; "
                "rebuild with 'hanzidraw fetch-data --rebuild' (without --medians-only)",
            )
        self.status(" | ".join(messages) if messages else "ready")
        self.bar.show_state(self._session.state)

    def reload_config(self, path: Path | None = None) -> None:
        self.apply_config(load_config(path))
        if self._canvas_cleared:
            note = "canvas cleared: layout settings changed"
            current = self.statusBar().currentMessage()
            self.status(f"{current} | {note}" if current and current != "ready" else note)

    def status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    # ---- input ----

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt naming
        key = key_from_event(event)
        if key is None:
            super().keyPressEvent(event)
            return
        state = self._session.feed(key)
        for action in state.actions:
            self.handle_action(action)
        commits = self._session.take_commits()
        for cand in commits:
            self.commit_candidate(cand)
        if commits:
            self._learn.save()
        self.bar.show_state(self._session.state)
        event.accept()

    def handle_action(self, action: str) -> None:
        if action == "toggle_mode":
            self.canvas.set_mode("single" if self.canvas.mode == "sheet" else "sheet")
        elif action == "undo":
            self.canvas.undo()  # owns the sheet's carriage too, like clear()
        elif action == "clear":
            self.canvas.clear()
            # The sheet's width does not shrink on clear (only its height
            # does, back to one empty row), so a horizontal scroll position
            # left over from a wide sheet would otherwise survive the clear
            # and hide the very first glyph drawn afterwards off to the side.
            self.scroll.horizontalScrollBar().setValue(0)
            self.scroll.verticalScrollBar().setValue(0)
        elif action == "save":
            target = Path(str(self._cfg.get("output.image.dir"))).expanduser() / "sheet.png"
            try:
                self.canvas.save(target)
            except OSError as exc:
                # A paintEvent-adjacent Qt path has nowhere to put a traceback,
                # and reporting "saved" for a write that never happened is worse
                # than the failure itself.
                self.status(f"could not save {target}: {exc.strerror or exc}")
            else:
                self.status(f"saved {target}")
        elif action == "replay":
            self.canvas.replay()
        elif action == "step_forward":
            self.canvas.step(1)
        elif action == "step_back":
            self.canvas.step(-1)
        elif action == "abort":
            backend = getattr(self, "_mouse", None)
            if backend is None:
                self.status("nothing to abort")
            else:
                backend.stop()
                self.status("draw aborted")

    def _backend(self):
        which = str(self._cfg.get("output.backend"))
        if which == "mouse":
            from ..output.mouse import MouseBackend, PynputPointer  # noqa: PLC0415

            try:
                pointer = PynputPointer(str(self._cfg.get("output.mouse.button")))
            except ImportError:
                self.status("mouse output needs pynput: pip install 'hanzidraw[mouse]'")
                return CanvasBackend(self.canvas)
            clamp = None
            if bool(self._cfg.get("output.mouse.clamp_to_screen")):
                geo = self.screen().geometry()
                # QRect.right()/bottom() are the last *addressable pixel*
                # (x()+width()-1), not the geometric edge (x()+width()) --
                # and PynputPointer.move_to rounds to an int pixel column, so
                # this is exactly the bound a placed cursor must not exceed.
                # A previous fix mistakenly added 1 here to "correct" for
                # QRect's continuous-geometry convention; that let the clamp
                # place the cursor one column past the real screen, which a
                # single monitor silently re-clamps but which spills onto an
                # adjacent display on a multi-monitor desktop -- precisely
                # what clamp_to_screen exists to prevent. Do not add 1 back.
                clamp = (
                    float(geo.left()),
                    float(geo.top()),
                    float(geo.right()),
                    float(geo.bottom()),
                )
            self._mouse = MouseBackend(
                pointer,
                scale=float(self._cfg.get("output.mouse.scale")),
                step_delay_ms=float(self._cfg.get("output.mouse.step_delay_ms")),
                clamp=clamp,
                window_rect=self._frame_rect,
            )
            return self._mouse
        if which == "image":
            # The image/SVG backend is the headless hanzidraw draw path (see
            # cli.py); the window has nowhere to put a file per keystroke and
            # no canvas feedback for it, so silently building one here would
            # discard every glyph without a crash or a message. Report and
            # fall back instead of inventing per-commit file semantics.
            self.status("output.backend = image is for the draw command; drawing to the canvas")
        return CanvasBackend(self.canvas)

    def _frame_rect(self) -> tuple[float, float, float, float]:
        """Our own window's frame, read at draw time, for the mouse guard."""
        geo = self.frameGeometry()
        return (float(geo.left()), float(geo.top()), float(geo.right()), float(geo.bottom()))

    def commit_candidate(self, cand) -> None:
        backend = self._backend()
        stop_listener = None
        if backend is getattr(self, "_mouse", None):
            from ..output.mouse import listen_for_abort  # noqa: PLC0415

            stop_listener = listen_for_abort(backend)
        try:
            for codepoint in cand.codepoints:
                if not self._store.has_char(codepoint):
                    self.status(f"no stroke data for {chr(codepoint)}")
                    continue
                glyph = load_glyph(self._store, codepoint)
                text = chr(codepoint)
                ox, oy, size = self.canvas.next_cell()
                if isinstance(backend, CanvasBackend):
                    backend.set_text(text)
                    if str(self._cfg.get("glyph.style")) == "outline":
                        backend.set_outline(self._store.outline(codepoint))
                try:
                    draw_glyph(backend, glyph, ox, oy, size)
                except MouseAbort as exc:
                    self.status(str(exc))
                    break
                # Only a completed draw advances the carriage: an aborted mouse
                # draw used to leave a gap in the sheet where nothing was drawn.
                self.canvas.advance(glyph, text)
        finally:
            if stop_listener is not None:
                stop_listener()

    # ---- lifecycle ----

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        self._learn.save()
        super().closeEvent(event)

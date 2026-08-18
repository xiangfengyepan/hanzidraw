"""The main window: key routing, commit handling, status messages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from ..config import data_dir, load_config
from ..data.store import Store
from ..ime.learn import Learn
from ..ime.session import Key, Session
from ..ime.sources import CharSource, PhraseSource
from ..output.base import draw_glyph, load_glyph
from ..output.canvas import CanvasBackend
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
        self.bar = CandidateBar()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.bar)
        self.setCentralWidget(central)
        self._learn = Learn(self._learn_path, enabled=True)
        self._session = Session([PhraseSource(store), CharSource(store)])
        self.apply_config(cfg)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---- configuration ----

    def apply_config(self, cfg) -> None:
        self._cfg = cfg
        self.canvas.configure(cfg)
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
        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint, bool(cfg.get("canvas.always_on_top"))
        )
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
            self.canvas.undo()
            self.canvas.sheet.undo()
        elif action == "clear":
            self.canvas.clear()
        elif action == "save":
            target = Path(str(self._cfg.get("output.image.dir"))).expanduser() / "sheet.png"
            self.canvas.save(target)
            self.status(f"saved {target}")
        elif action == "replay":
            self.canvas.replay()
        elif action == "step_forward":
            self.canvas.step(1)
        elif action == "step_back":
            self.canvas.step(-1)
        elif action == "abort":
            self.status("nothing to abort")

    def commit_candidate(self, cand) -> None:
        backend = CanvasBackend(self.canvas)
        for codepoint in cand.codepoints:
            if not self._store.has_char(codepoint):
                self.status(f"no stroke data for {chr(codepoint)}")
                continue
            placed = self.canvas.sheet.add(load_glyph(self._store, codepoint), chr(codepoint))
            backend.set_text(placed.text)
            draw_glyph(backend, placed.glyph, placed.ox, placed.oy, placed.size)

    # ---- lifecycle ----

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        self._learn.save()
        super().closeEvent(event)

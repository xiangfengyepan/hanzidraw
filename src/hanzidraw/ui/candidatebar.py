"""The preedit + numbered candidate strip along the bottom of the window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..ime.session import SessionState


class CandidateBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preedit = QLabel("")
        self._cands = QLabel("")
        self._page = QLabel("")
        self._cands.setTextFormat(Qt.TextFormat.RichText)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self._preedit)
        layout.addWidget(self._cands, stretch=1)
        layout.addWidget(self._page)

    def text(self) -> str:
        """Plain-text view of the bar — what the tests assert on."""
        return f"{self._preedit.text()} {self._cands.text()} {self._page.text()}"

    def show_state(self, state: SessionState) -> None:
        self._preedit.setText(state.display)
        chunks = []
        for i, cand in enumerate(state.page):
            label = f"{i + 1}.{cand.text}"
            chunks.append(f"<b>{label}</b>" if i == state.highlight else label)
        self._cands.setText("  ".join(chunks))
        self._page.setText(
            f"{state.page_index + 1}/{state.page_count}" if state.page_count > 1 else ""
        )

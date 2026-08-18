"""The compose state machine: keys in, preedit + candidate page out.

Pure: no Qt, no file access, no clock. Everything the UI needs is in the
returned ``SessionState``; everything the UI must *do* arrives in ``actions``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .candidates import collect, paginate, rank
from .learn import Learn
from .segment import segment
from .sources import Candidate, CandidateSource

_COMMANDS = {
    ("f2", False): "toggle_mode",
    ("z", True): "undo",
    ("l", True): "clear",
    ("s", True): "save",
    ("r", True): "replay",
    ("bracketright", True): "step_forward",
    ("bracketleft", True): "step_back",
    ("period", True): "abort",
}


@dataclass(frozen=True)
class Key:
    name: str
    ctrl: bool = False


@dataclass(frozen=True)
class SessionState:
    preedit: str = ""
    display: str = ""
    page: tuple[Candidate, ...] = ()
    page_index: int = 0
    page_count: int = 0
    highlight: int = 0
    actions: tuple[str, ...] = ()


class Session:
    def __init__(
        self,
        sources: Sequence[CandidateSource],
        *,
        page_size: int = 9,
        learn: Learn | None = None,
        max_candidates: int = 200,
    ) -> None:
        self._sources = list(sources)
        self._page_size = page_size
        self._learn = learn or Learn(None, enabled=False)
        self._max = max_candidates
        self._preedit = ""
        self._pages: list[tuple[Candidate, ...]] = []
        self._page_index = 0
        self._highlight = 0
        self._actions: tuple[str, ...] = ()
        self._commits: list[Candidate] = []
        self._display = ""

    # ---- public API ----

    @property
    def state(self) -> SessionState:
        page = self._pages[self._page_index] if self._pages else ()
        return SessionState(
            preedit=self._preedit,
            display=self._display,
            page=page,
            page_index=self._page_index,
            page_count=len(self._pages),
            highlight=self._highlight,
            actions=self._actions,
        )

    def take_commits(self) -> list[Candidate]:
        out, self._commits = self._commits, []
        return out

    def feed(self, key: Key) -> SessionState:
        self._actions = ()
        command = _COMMANDS.get((key.name, key.ctrl))
        if command:
            self._actions = (command,)
            return self.state
        if key.ctrl:
            return self.state

        name = key.name
        if len(name) == 1 and name.isalpha():
            self._preedit += name
            self._refresh()
        elif name == "apostrophe":
            if self._preedit and not self._preedit.endswith("'"):
                self._preedit += "'"
                self._refresh()
        elif name == "backspace":
            self._preedit = self._preedit[:-1]
            self._refresh()
        elif name == "escape":
            self._clear()
        elif name in ("space", "enter"):
            self._commit(self._highlight)
        elif len(name) == 1 and name.isdigit():
            self._commit(int(name) - 1)
        elif name in ("right", "tab"):
            self._move(1)
        elif name == "left":
            self._move(-1)
        elif name in ("equal", "pagedown"):
            self._turn_page(1)
        elif name in ("minus", "pageup"):
            self._turn_page(-1)
        return self.state

    # ---- internals ----

    def _clear(self) -> None:
        self._preedit = ""
        self._display = ""
        self._pages = []
        self._page_index = 0
        self._highlight = 0

    def _refresh(self) -> None:
        self._page_index = 0
        self._highlight = 0
        if not self._preedit:
            self._display = ""
            self._pages = []
            return
        segs = segment(self._preedit)
        self._display = segs[0].display if segs else self._preedit
        if not segs:
            self._pages = []
            return
        found = collect(self._sources, segs[0], self._max)
        ordered = rank(found, self._learn, segs[0].key + segs[0].partial, len(segs[0].syllables))
        self._pages = paginate(ordered[: self._max], self._page_size)

    def _move(self, delta: int) -> None:
        page = self._pages[self._page_index] if self._pages else ()
        if not page:
            return
        self._highlight = max(0, min(len(page) - 1, self._highlight + delta))

    def _turn_page(self, delta: int) -> None:
        if not self._pages:
            return
        self._page_index = max(0, min(len(self._pages) - 1, self._page_index + delta))
        self._highlight = 0

    def _commit(self, index: int) -> None:
        if not self._pages or not self._preedit:
            return
        page = self._pages[self._page_index]
        if not 0 <= index < len(page):
            return
        cand = page[index]
        segs = segment(self._preedit)
        key = (segs[0].key + segs[0].partial) if segs else self._preedit
        self._learn.record(key, cand.text)
        self._commits.append(cand)

        remaining = ""
        if segs and cand.consumed:
            seg = segs[0]
            rest = seg.syllables[cand.consumed :]
            remaining = "".join(rest) + seg.partial
        self._preedit = remaining
        if remaining:
            self._refresh()
        else:
            self._clear()

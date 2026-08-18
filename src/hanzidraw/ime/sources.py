"""Where candidates come from. Adding a new source means adding a class here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..data.store import Store
from .segment import Segmentation


@dataclass(frozen=True)
class Candidate:
    text: str
    codepoints: tuple[int, ...]
    source: str
    weight: float
    consumed: int


class CandidateSource(Protocol):
    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]: ...


class CharSource:
    """Single characters for the first syllable being typed."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]:
        if seg.syllables:
            rows = self._store.chars_for_reading(seg.syllables[0], limit)
        elif seg.partial:
            rows = self._store.chars_for_prefix(seg.partial, limit)
        else:
            return []
        out: list[Candidate] = []
        seen: set[int] = set()
        for codepoint, _pinyin, rank in rows:
            if codepoint in seen:
                continue
            seen.add(codepoint)
            out.append(
                Candidate(
                    text=chr(codepoint),
                    codepoints=(codepoint,),
                    source="char",
                    weight=1e6 / (1.0 + rank),
                    consumed=1 if seg.syllables else 0,
                )
            )
        return out


class PhraseSource:
    """Multi-character words, exact key first then longer keys sharing the prefix."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]:
        key = seg.key + seg.partial
        if not key:
            return []
        rows = self._store.phrases_for_key(key, limit)
        exact = {text for text, _ in rows}
        if len(rows) < limit:
            for text, weight in self._store.phrases_for_prefix(key, limit - len(rows)):
                if text not in exact:
                    rows.append((text, weight))
        out: list[Candidate] = []
        for text, weight in rows:
            out.append(
                Candidate(
                    text=text,
                    codepoints=tuple(ord(ch) for ch in text),
                    source="phrase",
                    weight=float(weight) + (1e9 if text in exact else 0.0),
                    consumed=len(text),
                )
            )
        return out

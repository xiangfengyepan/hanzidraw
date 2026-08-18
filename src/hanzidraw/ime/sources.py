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
    consumed: int  # How many syllables this candidate eats. May exceed the
    # segmentation's syllable count when a reading resegments (e.g.,
    # segment("xian") is 1 syllable but 西安 is 2 characters). Consumers
    # must slice with it, never index or assert on it.


class CandidateSource(Protocol):
    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]: ...


class CharSource:
    """Single characters for the first syllable being typed."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]:
        if limit <= 0:
            return []
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
    """Multi-character words: exact key first, then predictions that continue it.

    A complete segmentation (``seg.partial`` empty) gets an exact-key lookup
    plus predictions from keys that continue at a syllable boundary. An
    incomplete segmentation (the user is mid-syllable) skips the exact lookup
    entirely and predicts from a plain-string-prefix match instead, since the
    last syllable isn't finished yet and there is no boundary to respect.
    """

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]:
        if limit <= 0:
            return []
        exact: set[str] = set()
        if seg.partial:
            exact_rows: list[tuple[str, float]] = []
            partial_key = " ".join((*seg.syllables, seg.partial))
            prefix_rows = self._store.phrases_for_partial(partial_key, limit)
        else:
            key = " ".join(seg.syllables)
            if not key:
                return []
            exact_rows = self._store.phrases_for_key(key, limit)
            exact = {text for text, _ in exact_rows}
            prefix_rows = self._store.phrases_for_syllable_prefix(key, limit - len(exact_rows))
        # phrases_for_syllable_prefix structurally excludes the exact key (see
        # Task 10b), so the exact and prefix result sets are disjoint and each
        # is already distinct thanks to GROUP BY text -- no over-fetch
        # headroom is needed. The `seen` set is kept as cheap insurance only.
        rows: list[tuple[str, float]] = list(exact_rows)
        seen = set(exact)
        for text, weight in prefix_rows:
            if text in seen:
                continue
            seen.add(text)
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

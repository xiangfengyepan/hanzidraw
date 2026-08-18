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
    """Multi-character words, exact key first then longer keys sharing the prefix."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def lookup(self, seg: Segmentation, limit: int) -> list[Candidate]:
        key = seg.key + seg.partial
        if not key or limit <= 0:
            return []
        exact_rows = self._store.phrases_for_key(key, limit)
        exact = {text for text, _ in exact_rows}
        rows: list[tuple[str, float]] = list(exact_rows)
        seen = set(exact)
        # The prefix range includes `key` itself, so the exact rows come back
        # first; ask for headroom and filter rather than topping up by the
        # shortfall, which those rows would consume entirely. Measured maximum
        # real phrase weight is ~665,000 (就是), about 1,505× below the bonus.
        for text, weight in self._store.phrases_for_prefix(key, limit + len(exact_rows)):
            if len(rows) >= limit:
                break
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

"""Split a run of pinyin letters into syllables.

Exhaustive search with memoisation (inputs are short — the preedit is a handful
of syllables), then a deterministic ranking. Enumeration is exhaustive up to the
_MAX_SPLITS cap; pathological all-ambiguous input is truncated gracefully.
An unfinished trailing syllable is kept as ``partial`` so candidates can be
looked up while you are still typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .syllables import MAX_SYLLABLE_LEN, is_syllable, is_syllable_prefix

_INTERJECTION_ONLY = frozenset({"n", "ng", "m", "hm", "hng"})
_MAX_INPUT_LEN = 32
_MAX_SPLITS = 2048


@dataclass(frozen=True)
class Segmentation:
    syllables: tuple[str, ...]
    complete: bool
    partial: str

    @property
    def key(self) -> str:
        return "".join(self.syllables)

    @property
    def display(self) -> str:
        parts = [*self.syllables]
        if self.partial:
            parts.append(self.partial)
        return "'".join(parts)


@lru_cache(maxsize=4096)
def _all_splits(text: str) -> tuple[tuple[str, ...], ...]:
    if not text:
        return ((),)
    out: list[tuple[str, ...]] = []
    for size in range(min(MAX_SYLLABLE_LEN, len(text)), 0, -1):
        head = text[:size]
        if not is_syllable(head):
            continue
        for rest in _all_splits(text[size:]):
            out.append((head, *rest))
            if len(out) >= _MAX_SPLITS:
                return tuple(out)
    return tuple(out)


def _rank_key(sylls: tuple[str, ...]) -> tuple:
    junk = sum(1 for s in sylls if s in _INTERJECTION_ONLY)
    return (len(sylls), junk, tuple(-len(s) for s in sylls), sylls)


def _segment_run(run: str) -> list[Segmentation]:
    """Segment one apostrophe-free run, allowing an unfinished tail."""
    if not run:
        return []
    complete = sorted(_all_splits(run), key=_rank_key)
    results = [Segmentation(tuple(s), True, "") for s in complete]

    # A tail that is a legal prefix means the user is mid-syllable. Only worth
    # searching when no complete segmentation exists, otherwise it is just noise.
    for cut in range(len(run) - 1, 0, -1) if not results else ():
        head, tail = run[:cut], run[cut:]
        if not is_syllable_prefix(tail):
            continue
        for sylls in sorted(_all_splits(head), key=_rank_key):
            results.append(Segmentation(tuple(sylls), False, tail))
        if results:
            break
    if not results and is_syllable_prefix(run):
        results.append(Segmentation((), False, run))
    return results


def segment(raw: str, max_alternatives: int = 2) -> list[Segmentation]:
    """Return up to ``max_alternatives`` segmentations, best first."""
    if not raw or len(raw) > _MAX_INPUT_LEN:
        return []
    runs = [r for r in raw.split("'") if r]
    if not runs:
        return []

    per_run: list[list[Segmentation]] = []
    for i, run in enumerate(runs):
        options = _segment_run(run)
        if not options:
            return []
        # Only the final run may be incomplete.
        if i < len(runs) - 1:
            options = [o for o in options if o.complete]
            if not options:
                return []
        per_run.append(options[: max(2, max_alternatives)])

    combos: list[Segmentation] = []
    for first in per_run[0]:
        acc = [first]
        for options in per_run[1:]:
            nxt = options[0]
            acc = [
                Segmentation(a.syllables + nxt.syllables, nxt.complete, nxt.partial) for a in acc
            ]
        combos.extend(acc)

    seen: set[tuple] = set()
    unique: list[Segmentation] = []
    for c in sorted(combos, key=lambda s: (not s.complete, _rank_key(s.syllables))):
        sig = (c.syllables, c.complete, c.partial)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(c)
    return unique[:max_alternatives]

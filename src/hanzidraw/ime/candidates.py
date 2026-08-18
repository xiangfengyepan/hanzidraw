"""Merge candidates from several sources into one ordered, paginated list."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .learn import Learn
from .segment import Segmentation
from .sources import Candidate, CandidateSource

_SOURCE_PRIORITY = {"phrase": 0, "char": 1}


def collect(
    sources: Iterable[CandidateSource], segs: Sequence[Segmentation], limit: int
) -> list[Candidate]:
    out: list[Candidate] = []
    for seg in segs:
        for source in sources:
            out.extend(source.lookup(seg, limit))
    return out


def rank(cands: Iterable[Candidate], learn: Learn, key: str) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for cand in cands:
        current = best.get(cand.text)
        if current is None or cand.weight > current.weight:
            best[cand.text] = cand

    def sort_key(cand: Candidate) -> tuple:
        return (
            -learn.bonus(key, cand.text),
            _SOURCE_PRIORITY.get(cand.source, 9),
            -cand.weight,
            cand.text,
        )

    return sorted(best.values(), key=sort_key)


def paginate(cands: Sequence[Candidate], page_size: int) -> list[tuple[Candidate, ...]]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    return [tuple(cands[i : i + page_size]) for i in range(0, len(cands), page_size)]

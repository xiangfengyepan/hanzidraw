from hanzidraw.ime.candidates import collect, paginate, rank
from hanzidraw.ime.learn import Learn
from hanzidraw.ime.segment import segment
from hanzidraw.ime.sources import Candidate


def _c(text, source, weight, consumed=1):
    return Candidate(text, tuple(ord(ch) for ch in text), source, weight, consumed)


class FakeSource:
    def __init__(self, *cands):
        self.cands = list(cands)
        self.calls = []

    def lookup(self, seg, limit):
        self.calls.append((seg.syllables, seg.partial, limit))
        return self.cands[:limit]


def test_collect_queries_every_source_with_every_segmentation():
    a, b = FakeSource(_c("北", "char", 5)), FakeSource(_c("北京", "phrase", 9, 2))
    segs = segment("xian")  # two alternatives
    out = collect([a, b], segs, limit=10)
    assert len(a.calls) == len(segs)
    assert {c.text for c in out} == {"北", "北京"}


def test_rank_puts_phrases_before_characters_at_equal_weight():
    out = rank([_c("北", "char", 100.0), _c("北京", "phrase", 100.0, 2)], Learn(None, False), "bei")
    assert [c.text for c in out] == ["北京", "北"]


def test_rank_orders_by_weight_within_a_source():
    out = rank([_c("背", "char", 5.0), _c("北", "char", 50.0)], Learn(None, False), "bei")
    assert [c.text for c in out] == ["北", "背"]


def test_rank_promotes_a_learned_pick_above_everything(tmp_path):
    learn = Learn(tmp_path / "l.json")
    learn.record("bei", "背")
    out = rank([_c("北", "char", 1e5), _c("背", "char", 1.0)], learn, "bei")
    assert [c.text for c in out] == ["背", "北"]


def test_rank_deduplicates_by_text_keeping_the_best():
    out = rank([_c("北", "char", 1.0), _c("北", "char", 99.0)], Learn(None, False), "bei")
    assert len(out) == 1
    assert out[0].weight == 99.0


def test_rank_is_deterministic_for_equal_weights():
    cands = [_c("背", "char", 1.0), _c("北", "char", 1.0)]
    assert rank(cands, Learn(None, False), "bei") == rank(
        list(reversed(cands)), Learn(None, False), "bei"
    )


def test_paginate_splits_into_full_pages_then_a_remainder():
    cands = [_c(chr(0x4E00 + i), "char", float(i)) for i in range(11)]
    pages = paginate(cands, 9)
    assert len(pages) == 2
    assert len(pages[0]) == 9
    assert len(pages[1]) == 2


def test_paginate_of_nothing_is_no_pages():
    assert paginate([], 9) == []

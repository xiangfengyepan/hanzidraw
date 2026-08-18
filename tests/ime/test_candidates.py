import tempfile
from pathlib import Path

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
    out = rank(
        [_c("北", "char", 100.0), _c("北京", "phrase", 100.0, 2)],
        Learn(None, False),
        "bei",
        2,
    )
    assert [c.text for c in out] == ["北京", "北"]


def test_rank_orders_by_weight_within_a_source():
    out = rank(
        [_c("背", "char", 5.0), _c("北", "char", 50.0)],
        Learn(None, False),
        "bei",
        1,
    )
    assert [c.text for c in out] == ["北", "背"]


def test_rank_promotes_a_learned_pick_above_everything(tmp_path):
    learn = Learn(tmp_path / "l.json")
    learn.record("bei", "背")
    out = rank([_c("北", "char", 1e5), _c("背", "char", 1.0)], learn, "bei", 1)
    assert [c.text for c in out] == ["背", "北"]


def test_rank_deduplicates_by_text_keeping_the_best():
    out = rank(
        [_c("北", "char", 1.0), _c("北", "char", 99.0)],
        Learn(None, False),
        "bei",
        1,
    )
    assert len(out) == 1
    assert out[0].weight == 99.0


def test_rank_is_deterministic_for_equal_weights():
    cands = [_c("背", "char", 1.0), _c("北", "char", 1.0)]
    assert rank(cands, Learn(None, False), "bei", 1) == rank(
        list(reversed(cands)), Learn(None, False), "bei", 1
    )


def test_rank_full_match_beats_prediction():
    """Full match (consumed == syllables) beats prediction (consumed > syllables).

    This test catches the original feng/ye bug: a single character with
    consumed=1 should outrank a predictive phrase with consumed=2 when
    syllables_typed=1.
    """
    out = rank(
        [_c("北", "char", 1.0), _c("北京", "phrase", 100.0, 2)],
        Learn(None, False),
        "bei",
        1,
    )
    # "北" tier 0 (full), "北京" tier 1 (prediction): char wins
    assert [c.text for c in out] == ["北", "北京"]


def test_rank_prediction_beats_partial():
    """Prediction (consumed > syllables) beats partial (consumed < syllables)."""
    out = rank(
        [_c("北", "char", 1.0), _c("北京市", "phrase", 100.0, 3)],
        Learn(None, False),
        "beijing",
        2,
    )
    # "北" tier 2 (partial, consumed=1 < 2), "北京市" tier 1 (prediction, consumed=3 > 2)
    assert [c.text for c in out] == ["北京市", "北"]


def test_rank_source_priority_within_tier():
    """Within the same tier, phrases still precede characters."""
    phrase_cand = Candidate("北京", (ord("北"), ord("京")), "phrase", 100.0, 2)
    char_cand = Candidate("北", (ord("北"),), "char", 100.0, 2)
    out = rank([char_cand, phrase_cand], Learn(None, False), "beijing", 2)
    # Both tier 0 (full match), phrase priority 0 < char priority 1
    assert out[0].source == "phrase"


def test_rank_learned_pick_beats_full_match():
    """Learned bonus still wins from a worse tier.

    A learned prediction should outrank an unlearned full match, because
    bonus is the first sort element.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        learn = Learn(Path(tmpdir) / "l.json")
        # Record bonus for a prediction (consumed=3)
        learn.record("beijing", "北京市")
        learn.save()

        # Prediction with bonus
        pred_cand = _c("北京市", "phrase", 1.0, 3)
        # Full match without bonus
        full_cand = _c("北", "char", 1000.0, 2)

        out = rank([full_cand, pred_cand], learn, "beijing", 2)
        # Prediction has bonus (tier 1), full match is tier 0
        # But bonus (-learn.bonus, ...) sorts first
        assert out[0].text == "北京市"


def test_rank_zero_syllables_typed():
    """With syllables_typed=0 (incomplete syllable), consumed=0 is full match."""
    out = rank(
        [_c("北", "char", 1.0, 0), _c("北京", "phrase", 100.0, 2)],
        Learn(None, False),
        "be",
        0,
    )
    # "北" tier 0 (full match for incomplete), "北京" tier 1 (prediction)
    assert [c.text for c in out] == ["北", "北京"]


def test_paginate_splits_into_full_pages_then_a_remainder():
    cands = [_c(chr(0x4E00 + i), "char", float(i)) for i in range(11)]
    pages = paginate(cands, 9)
    assert len(pages) == 2
    assert len(pages[0]) == 9
    assert len(pages[1]) == 2


def test_paginate_of_nothing_is_no_pages():
    assert paginate([], 9) == []

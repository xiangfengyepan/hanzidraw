from hanzidraw.data.store import Store
from hanzidraw.ime.segment import segment
from hanzidraw.ime.sources import CharSource, PhraseSource

MEDIANS = (((0, 0), (10, 10)),)


def _store(tmp_path):
    store = Store.create(tmp_path / "db.sqlite")
    for cp, rank, readings in (
        (ord("北"), 300, ("bei",)),
        (ord("背"), 900, ("bei",)),
        (ord("京"), 700, ("jing",)),
    ):
        store.add_char(cp, freq_rank=rank, nstroke=1, medians=MEDIANS, outline=None)
        for reading in readings:
            store.add_reading(reading, cp)
    store.add_phrase("beijing", "北京", 5000.0)
    store.add_phrase("beijing", "背景", 4000.0)
    store.add_phrase("beijingren", "北京人", 100.0)
    store.finish()
    return store


def test_char_source_returns_first_syllable_candidates_by_frequency(tmp_path):
    src = CharSource(_store(tmp_path))
    cands = src.lookup(segment("beijing")[0], limit=10)
    assert [c.text for c in cands] == ["北", "背"]
    assert all(c.consumed == 1 for c in cands)
    assert all(c.source == "char" for c in cands)


def test_char_source_uses_the_partial_tail_when_nothing_is_complete(tmp_path):
    src = CharSource(_store(tmp_path))
    cands = src.lookup(segment("be")[0], limit=10)
    assert [c.text for c in cands] == ["北", "背"]


def test_phrase_source_prefers_the_exact_key_then_prefix_matches(tmp_path):
    src = PhraseSource(_store(tmp_path))
    cands = src.lookup(segment("beijing")[0], limit=10)
    assert [c.text for c in cands][:2] == ["北京", "背景"]
    assert "北京人" in [c.text for c in cands]
    assert cands[0].consumed == 2
    assert cands[0].codepoints == (ord("北"), ord("京"))


def test_phrase_source_returns_nothing_for_a_key_it_does_not_have(tmp_path):
    src = PhraseSource(_store(tmp_path))
    assert src.lookup(segment("wo")[0], limit=10) == []


def test_char_weights_decrease_with_frequency_rank(tmp_path):
    cands = CharSource(_store(tmp_path)).lookup(segment("bei")[0], limit=10)
    assert cands[0].weight > cands[1].weight

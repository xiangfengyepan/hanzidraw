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
    store.add_phrase("bei jing", "北京", 5000.0)
    store.add_phrase("bei jing", "背景", 4000.0)
    store.add_phrase("bei jing ren", "北京人", 100.0)
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


def test_phrase_source_deduplicates_prefix_vs_prefix_duplicates(tmp_path):
    """Prefix-vs-prefix duplicates are deduped (mirroring ce du/ce duo -> 测度)."""
    store = Store.create(tmp_path / "db_dup.sqlite")
    # Add two phrases with the same text but different (longer) continuations of "ce"
    store.add_phrase("ce du", "测度", 100.0)
    store.add_phrase("ce duo", "测度", 90.0)
    store.finish()
    src = PhraseSource(store)
    cands = src.lookup(segment("ce")[0], limit=5000)
    texts = [c.text for c in cands]
    # 测度 should appear exactly once, not twice
    assert texts.count("测度") == 1


def test_phrase_source_honours_limit_when_distinct_candidates_exist(tmp_path):
    """limit is honoured even when exact rows eat into the budget."""
    store = Store.create(tmp_path / "db_limit.sqlite")
    # One exact-key phrase and one longer-key syllable-prefix phrase
    store.add_phrase("bei jing", "北京", 5000.0)
    store.add_phrase("bei jing ren", "北京人", 100.0)
    store.finish()
    src = PhraseSource(store)
    # At limit=2, we should get exactly 2 candidates (not under-filled)
    cands = src.lookup(segment("beijing")[0], limit=2)
    assert len(cands) == 2
    # Both should be present
    assert [c.text for c in cands] == ["北京", "北京人"]


def test_char_source_returns_empty_for_zero_and_negative_limits(tmp_path):
    """limit=0 and limit=-1 return [] to avoid SQLite footgun."""
    src = CharSource(_store(tmp_path))
    assert src.lookup(segment("bei")[0], limit=0) == []
    assert src.lookup(segment("bei")[0], limit=-1) == []


def test_phrase_source_returns_empty_for_zero_and_negative_limits(tmp_path):
    """limit=0 and limit=-1 return [] to avoid SQLite footgun."""
    src = PhraseSource(_store(tmp_path))
    assert src.lookup(segment("beijing")[0], limit=0) == []
    assert src.lookup(segment("beijing")[0], limit=-1) == []


def test_consumed_can_exceed_segmentation_syllables_on_resegmentation(tmp_path):
    """consumed > seg.syllables when reading resegments."""
    store = Store.create(tmp_path / "db_reseg.sqlite")
    # A two-character phrase keyed by a single-syllable reading
    store.add_phrase("xian", "西安", 1000.0)
    store.finish()
    src = PhraseSource(store)
    # segment("xian") is 1 syllable
    seg = segment("xian")[0]
    assert len(seg.syllables) == 1
    cands = src.lookup(seg, limit=10)
    # But the phrase 西安 is 2 characters
    assert len(cands) == 1
    assert cands[0].consumed == 2
    # Consumer must slice, not index/assert on this


def test_phrase_source_returns_exact_limit_when_prefix_deduped(tmp_path):
    """When deduplicating prefix rows, still return exactly limit candidates."""
    store = Store.create(tmp_path / "db_prefix_dup.sqlite")
    # Same text keyed under two different continuations of "ce" - internally duplicated
    store.add_phrase("ce du", "测度", 100.0)
    store.add_phrase("ce duo", "测度", 90.0)
    # One unique text to reach the limit
    store.add_phrase("ce dai", "测代", 80.0)
    store.finish()
    src = PhraseSource(store)
    # "ce" has no exact key in this store, so lookup uses only prefix rows
    seg = segment("ce")[0]
    # Despite 3 rows in the DB, they contain only 2 distinct texts.
    # With limit=2, we should get exactly 2 candidates.
    cands = src.lookup(seg, limit=2)
    assert len(cands) == 2
    texts = [c.text for c in cands]
    # Should have the two distinct texts
    assert set(texts) == {"测度", "测代"}
    # 测度 should appear exactly once with the max weight
    assert texts.count("测度") == 1


def test_phrase_source_typing_xian_has_no_bled_xiang_prediction(tmp_path):
    """Task 10b's bug: 'xian' must not surface 想要 (xiang|yao)."""
    store = Store.create(tmp_path / "db_xian.sqlite")
    store.add_phrase("xian", "西安", 1000.0)
    store.add_phrase("xiang yao", "想要", 900.0)
    store.finish()
    src = PhraseSource(store)
    cands = src.lookup(segment("xian")[0], limit=10)
    assert [c.text for c in cands] == ["西安"]


def test_phrase_source_typing_hen_has_no_bled_he_or_heng_prediction(tmp_path):
    """Task 10b's bug: 'hen' must not surface 河南 (he|nan) or 衡量 (heng-)."""
    store = Store.create(tmp_path / "db_hen.sqlite")
    store.add_phrase("he nan", "河南", 800.0)
    store.add_phrase("heng liang", "衡量", 700.0)
    store.finish()
    src = PhraseSource(store)
    assert src.lookup(segment("hen")[0], limit=10) == []


def test_phrase_source_typing_beijing_offers_exact_then_syllable_prediction(tmp_path):
    """Complete input: exact match first, then a genuine syllable-boundary continuation."""
    store = Store.create(tmp_path / "db_beijing.sqlite")
    store.add_phrase("bei jing", "北京", 5000.0)
    store.add_phrase("bei jing shi", "北京市", 100.0)
    store.finish()
    src = PhraseSource(store)
    cands = src.lookup(segment("beijing")[0], limit=10)
    assert [c.text for c in cands] == ["北京", "北京市"]
    assert cands[0].consumed == 2
    assert cands[1].consumed == 3


def test_phrase_source_incomplete_final_syllable_uses_partial_lookup(tmp_path):
    """Mid-syllable input ('beij' = bei + partial 'j'): no exact lookup, plain-prefix prediction."""
    store = Store.create(tmp_path / "db_partial.sqlite")
    store.add_phrase("bei jing", "北京", 5000.0)
    store.finish()
    src = PhraseSource(store)
    seg = segment("beij")[0]
    assert seg.syllables == ("bei",)
    assert seg.partial == "j"  # incomplete: mid-syllable, not yet "jing"
    cands = src.lookup(seg, limit=10)
    assert [c.text for c in cands] == ["北京"]

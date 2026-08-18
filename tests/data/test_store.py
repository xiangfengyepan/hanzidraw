import pytest

from hanzidraw.data.store import (
    SCHEMA_VERSION,
    Store,
    StoreError,
    decode_medians,
    encode_medians,
)

MEDIANS = (((-412, -142), (388, -142)), ((0, -512), (0, 288)))


def test_blob_codec_round_trips_exactly():
    assert decode_medians(encode_medians(MEDIANS)) == MEDIANS


def test_blob_codec_round_trips_extreme_coordinates():
    extreme = (((-32768, 32767), (0, 0)),)
    assert decode_medians(encode_medians(extreme)) == extreme


def test_blob_codec_rejects_an_impossibly_long_stroke():
    with pytest.raises(ValueError):
        encode_medians((tuple((i, i) for i in range(256)),))


def _build(path):
    store = Store.create(path)
    store.add_char(ord("十"), freq_rank=131, nstroke=2, medians=MEDIANS, outline=("M 0 0 Z",))
    store.add_char(ord("是"), freq_rank=4, nstroke=9, medians=MEDIANS, outline=None)
    store.add_reading("shi", ord("十"))
    store.add_reading("shi", ord("是"))
    store.add_phrase("shi shi", "实施", 100.0)
    store.add_phrase("shi", "十", 5.0)
    store.set_meta("source_graphics_sha256", "abc")
    store.finish()
    return store


def test_round_trip_of_chars_readings_and_phrases(tmp_path):
    store = _build(tmp_path / "db.sqlite")
    assert store.has_char(ord("十"))
    assert not store.has_char(ord("龘"))
    assert store.medians(ord("十")) == MEDIANS
    assert store.outline(ord("十")) == ("M 0 0 Z",)
    assert store.outline(ord("是")) is None
    assert store.char_meta(ord("十")) == (131, 2)
    assert store.get_meta("source_graphics_sha256") == "abc"


def test_reading_lookup_is_ordered_by_frequency(tmp_path):
    store = _build(tmp_path / "db.sqlite")
    rows = store.chars_for_reading("shi", limit=10)
    assert [r[0] for r in rows] == [ord("是"), ord("十")]  # rank 4 before rank 131


def test_prefix_lookup_matches_a_partial_reading(tmp_path):
    store = _build(tmp_path / "db.sqlite")
    assert {r[0] for r in store.chars_for_prefix("sh", limit=10)} == {ord("十"), ord("是")}
    assert store.chars_for_prefix("zzz", limit=10) == []


def test_phrase_lookup_by_exact_key_and_by_syllable_prefix_and_partial(tmp_path):
    store = _build(tmp_path / "db.sqlite")
    assert store.phrases_for_key("shi shi", limit=5) == [("实施", 100.0)]
    # syllable_prefix excludes the exact key "shi" (十, 1 syllable) and only
    # returns keys that continue at a boundary, i.e. "shi shi" (实施).
    assert store.phrases_for_syllable_prefix("shi", limit=5) == [("实施", 100.0)]
    # partial is plain-string-prefix and so includes the exact key literally;
    # commonest first: weight dominates, length only breaks ties.
    assert [p[0] for p in store.phrases_for_partial("shi", limit=5)] == ["实施", "十"]


def test_open_rejects_a_missing_database(tmp_path):
    with pytest.raises(StoreError) as exc:
        Store.open(tmp_path / "nope.sqlite")
    assert "fetch-data" in str(exc.value)


def test_open_rejects_a_stale_schema(tmp_path):
    path = tmp_path / "db.sqlite"
    store = _build(path)
    store.set_meta("schema_version", str(SCHEMA_VERSION + 1))
    store.finish()
    store.close()
    with pytest.raises(StoreError) as exc:
        Store.open(path)
    assert "schema" in str(exc.value).lower()


def test_open_rejects_the_old_schema_version_1(tmp_path):
    """A real pre-Task-10b database (schema_version 1) must be rejected, not mismatched."""
    path = tmp_path / "db.sqlite"
    store = _build(path)
    store.set_meta("schema_version", "1")
    store.finish()
    store.close()
    with pytest.raises(StoreError) as exc:
        Store.open(path)
    assert "--rebuild" in str(exc.value)


def test_open_rejects_the_old_schema_version_2(tmp_path):
    """A real pre-Task-19-fix database (schema_version 2, no reading provenance) is rejected."""
    path = tmp_path / "db.sqlite"
    store = _build(path)
    store.set_meta("schema_version", "2")
    store.finish()
    store.close()
    with pytest.raises(StoreError) as exc:
        Store.open(path)
    assert "--rebuild" in str(exc.value)


def test_first_reading_prefers_the_primary_reading_over_an_earlier_alternate(tmp_path):
    """Alphabetical order must not override provenance: 'xie' < 'ye', but 'ye' is primary."""
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("叶"), freq_rank=1, nstroke=5, medians=MEDIANS, outline=None)
    store.add_reading("ye", ord("叶"), is_primary=True)
    store.add_reading("xie", ord("叶"), is_primary=False)
    store.finish()
    assert store.first_reading(ord("叶")) == "ye"


def test_first_reading_falls_back_to_any_reading_when_none_is_primary(tmp_path):
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("叶"), freq_rank=1, nstroke=5, medians=MEDIANS, outline=None)
    store.add_reading("xie", ord("叶"), is_primary=False)
    store.finish()
    assert store.first_reading(ord("叶")) == "xie"


def test_phrases_for_syllable_and_partial_prefix_both_dedupe_by_text(tmp_path):
    """Same phrase text under two different continuations dedupes for both methods."""
    store = Store.create(tmp_path / "db_dup.sqlite")
    # Add the same text under two different keys with different weights
    store.add_phrase("ce du", "测度", 100.0)
    store.add_phrase("ce duo", "测度", 90.0)
    store.finish()
    # Should return the text once with the higher weight, from either method
    sp_rows = store.phrases_for_syllable_prefix("ce", limit=100)
    assert [t for t, w in sp_rows] == ["测度"]
    assert [w for t, w in sp_rows] == [100.0]
    partial_rows = store.phrases_for_partial("ce", limit=100)
    assert [t for t, w in partial_rows] == ["测度"]
    assert [w for t, w in partial_rows] == [100.0]


def test_phrases_for_key_ordering_is_deterministic_on_ties(tmp_path):
    """phrases_for_key: same weight and length -> consistent text order."""
    store = Store.create(tmp_path / "db_det_key.sqlite")
    # Add phrases with identical weight and length under one key
    store.add_phrase("testkey", "aaa", 500.0)
    store.add_phrase("testkey", "bbb", 500.0)
    store.add_phrase("testkey", "zzz", 500.0)
    store.finish()
    # Call multiple times and verify the order is stable
    for _ in range(3):
        rows = store.phrases_for_key("testkey", limit=10)
        assert [t for t, w in rows] == ["aaa", "bbb", "zzz"]


def test_phrases_for_syllable_prefix_ordering_is_deterministic_on_ties(tmp_path):
    """phrases_for_syllable_prefix: distinct texts, same weight/length -> stable order."""
    store = Store.create(tmp_path / "db_det_prefix.sqlite")
    # Three distinct continuations of "ce", each a different two-syllable key,
    # each with a different (but tied) text.
    store.add_phrase("ce ai", "aaa", 500.0)
    store.add_phrase("ce an", "bbb", 500.0)
    store.add_phrase("ce ang", "zzz", 500.0)
    store.finish()
    # Call multiple times and verify the order is stable
    for _ in range(3):
        rows = store.phrases_for_syllable_prefix("ce", limit=10)
        assert [t for t, w in rows] == ["aaa", "bbb", "zzz"]


def test_phrases_for_syllable_prefix_respects_syllable_boundaries(tmp_path):
    """Predictions must not bleed across a syllable boundary (Task 10b's bug)."""
    store = Store.create(tmp_path / "db_boundary.sqlite")
    store.add_phrase("xian", "西安", 1000.0)
    store.add_phrase("xiang yao", "想要", 900.0)
    store.add_phrase("he nan", "河南", 800.0)
    store.add_phrase("heng liang", "衡量", 700.0)
    store.add_phrase("bei jing", "北京", 5000.0)
    store.add_phrase("bei jing shi", "北京市", 100.0)
    store.finish()
    # 想要 (xiang|yao) must not bleed in; 西安 is the exact key, excluded here.
    assert store.phrases_for_syllable_prefix("xian", limit=10) == []
    # 北京市 continues at a boundary; 北京 itself (the exact key) is excluded.
    assert store.phrases_for_syllable_prefix("bei jing", limit=10) == [("北京市", 100.0)]
    # Neither he|nan nor heng- bleeds into a "hen" query.
    assert store.phrases_for_syllable_prefix("hen", limit=10) == []
    # But "he" genuinely continues into "he nan".
    assert store.phrases_for_syllable_prefix("he", limit=10) == [("河南", 800.0)]


def test_phrases_for_partial_is_plain_string_prefix_matching(tmp_path):
    """phrases_for_partial is mid-syllable prediction: literal prefix, no boundary check."""
    store = Store.create(tmp_path / "db_partial.sqlite")
    store.add_phrase("xian", "西安", 1000.0)
    store.add_phrase("xiang yao", "想要", 900.0)
    store.add_phrase("he nan", "河南", 800.0)
    store.add_phrase("heng liang", "衡量", 700.0)
    store.add_phrase("bei jing", "北京", 5000.0)
    store.add_phrase("bei jing shi", "北京市", 100.0)
    store.finish()
    assert store.phrases_for_partial("bei j", limit=10) == [("北京", 5000.0), ("北京市", 100.0)]
    # "be" is a legal partial syllable (a prefix of "bei"/"ben"/"beng"), and
    # "bei jing" literally starts with the two characters "be" -- plain prefix
    # matching correctly offers it here. This is not a boundary bleed: "be" is
    # a prefix of the *first syllable itself* ("bei"), not a jump past it, so
    # syllable-boundary awareness (phrases_for_syllable_prefix's job) does not
    # apply to an incomplete final syllable. This is the intended behaviour
    # for a user who is mid-way through typing "bei": offering 北京/北京市 is
    # exactly what a real IME should do.
    assert store.phrases_for_partial("be", limit=10) == [("北京", 5000.0), ("北京市", 100.0)]
    assert store.phrases_for_partial("bei", limit=10) == [("北京", 5000.0), ("北京市", 100.0)]

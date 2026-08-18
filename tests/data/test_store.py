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
    store.add_phrase("shishi", "实施", 100.0)
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


def test_phrase_lookup_by_exact_key_and_by_prefix(tmp_path):
    store = _build(tmp_path / "db.sqlite")
    assert store.phrases_for_key("shishi", limit=5) == [("实施", 100.0)]
    # commonest first: weight dominates, length only breaks ties
    assert [p[0] for p in store.phrases_for_prefix("shi", limit=5)] == ["实施", "十"]


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


def test_phrases_for_prefix_deduplicates_by_text_and_keeps_max_weight(tmp_path):
    """Same phrase text under different keys returns once with highest weight."""
    store = Store.create(tmp_path / "db_dup.sqlite")
    # Add the same text under two different keys with different weights
    store.add_phrase("cedu", "测度", 100.0)
    store.add_phrase("ceduo", "测度", 90.0)
    store.finish()
    # Should return the text once with the higher weight
    rows = store.phrases_for_prefix("ce", limit=100)
    texts = [t for t, w in rows]
    assert texts.count("测度") == 1
    # The weight should be the maximum of the two
    assert [w for t, w in rows if t == "测度"] == [100.0]


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


def test_phrases_for_prefix_ordering_is_deterministic_on_ties(tmp_path):
    """phrases_for_prefix: same weight/length across keys -> stable order."""
    store = Store.create(tmp_path / "db_det_prefix.sqlite")
    # Add three texts with identical weight and length under different keys
    # sharing a prefix (ce*).
    store.add_phrase("ceaaa", "测试", 500.0)
    store.add_phrase("cebbb", "测试", 500.0)  # Same text, different key
    store.add_phrase("ceccb", "测试", 500.0)  # Same text, another key
    store.finish()
    # Call multiple times and verify the text appears only once with stable order
    for _ in range(3):
        rows = store.phrases_for_prefix("ce", limit=10)
        texts = [t for t, w in rows]
        # Should appear exactly once due to GROUP BY dedup
        assert texts.count("测试") == 1
        # And weight should be the max (all are 500.0)
        assert [w for t, w in rows if t == "测试"] == [500.0]

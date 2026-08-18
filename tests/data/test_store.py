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

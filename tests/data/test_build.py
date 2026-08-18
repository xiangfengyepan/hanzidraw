import gzip

from hanzidraw.data.build import build
from hanzidraw.data.store import Store


def _raw(tmp_path, fixtures, *, with_essay=True):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "graphics.txt").write_text(
        (fixtures / "graphics_sample.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (raw / "hanziDB.csv").write_text(
        (fixtures / "hanzidb_sample.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with gzip.open(raw / "cedict.txt.gz", "wt", encoding="utf-8") as fh:
        fh.write((fixtures / "cedict_sample.u8").read_text(encoding="utf-8"))
    if with_essay:
        (raw / "essay.txt").write_text(
            (fixtures / "essay_sample.txt").read_text(encoding="utf-8"), encoding="utf-8"
        )
    return raw


def test_build_inserts_only_characters_that_can_be_drawn(tmp_path, fixtures):
    db = tmp_path / "db.sqlite"
    report = build(_raw(tmp_path, fixtures), db)
    store = Store.open(db)
    assert store.has_char(ord("十"))
    assert store.has_char(ord("一"))
    assert not store.has_char(ord("的"))  # in hanziDB, no medians in the fixture
    assert report.chars == 2
    assert report.chars_without_geometry >= 1


def test_build_drops_a_phrase_whose_characters_are_not_all_drawable(tmp_path, fixtures):
    db = tmp_path / "db.sqlite"
    report = build(_raw(tmp_path, fixtures), db)
    store = Store.open(db)
    assert store.phrases_for_key("yishi", limit=5) == [("一十", 12.0)]  # both chars present
    assert store.phrases_for_key("beijing", limit=5) == []  # 北京 has no medians here
    assert report.phrases_dropped >= 2


def test_build_without_essay_falls_back_to_a_frequency_heuristic(tmp_path, fixtures):
    db = tmp_path / "db.sqlite"
    build(_raw(tmp_path, fixtures, with_essay=False), db)
    store = Store.open(db)
    rows = store.phrases_for_key("yishi", limit=5)
    assert len(rows) == 1
    assert rows[0][1] > 0


def test_medians_only_build_omits_outlines(tmp_path, fixtures):
    db = tmp_path / "db.sqlite"
    report = build(_raw(tmp_path, fixtures), db, medians_only=True)
    store = Store.open(db)
    assert store.outline(ord("十")) is None
    assert report.outlines is False


def test_build_records_digests_and_schema_in_meta(tmp_path, fixtures):
    db = tmp_path / "db.sqlite"
    build(_raw(tmp_path, fixtures), db, digests={"graphics": "deadbeef"})
    store = Store.open(db)
    assert store.get_meta("source_graphics_sha256") == "deadbeef"
    assert store.get_meta("build_medians_only") == "0"


def test_report_summary_mentions_the_counts(tmp_path, fixtures):
    report = build(_raw(tmp_path, fixtures), tmp_path / "db.sqlite")
    text = report.summary()
    assert "characters" in text and "phrases" in text


def test_build_report_lists_unknown_syllables(tmp_path, fixtures):
    raw = _raw(tmp_path, fixtures)
    (raw / "hanziDB.csv").write_text(
        "character,pinyin,stroke_count,frequency_rank\n十,shi,2,131\n啊,xq,1,999\n",
        encoding="utf-8",
    )
    report = build(raw, tmp_path / "db.sqlite")
    assert report.unknown_syllables == ("xq",)

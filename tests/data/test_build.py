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


def test_build_dedupes_duplicate_hanzidb_rows(tmp_path, fixtures):
    raw = _raw(tmp_path, fixtures)
    duplicated = (fixtures / "hanzidb_sample.csv").read_text(encoding="utf-8")
    duplicated += "3,十,shí,ten,十,24.0,2,1,3,131\n"  # exact duplicate of the 十 row
    (raw / "hanziDB.csv").write_text(duplicated, encoding="utf-8")

    db = tmp_path / "db.sqlite"
    report = build(raw, db)
    store = Store.open(db)
    assert report.duplicate_chars == 1
    assert report.chars == len(list(store.all_chars_by_rank()))


def test_build_dedupes_duplicate_cedict_entries(tmp_path, fixtures):
    raw = _raw(tmp_path, fixtures)
    duplicated = (fixtures / "cedict_sample.u8").read_text(encoding="utf-8")
    duplicated += "一十 一十 [yi1 shi2] /ten (again)/\n"  # duplicate (pinyin_key, text)
    with gzip.open(raw / "cedict.txt.gz", "wt", encoding="utf-8") as fh:
        fh.write(duplicated)

    report = build(raw, tmp_path / "db.sqlite")
    assert report.duplicate_phrases == 1
    assert report.phrases == 1


def test_build_harvests_extra_readings_only_for_stored_characters(tmp_path, fixtures):
    raw = _raw(tmp_path, fixtures)
    # Make 乐 drawable in THIS test's raw copy only: it has one hanziDB reading
    # (lè) and a genuinely different CC-CEDICT reading (lao4), which is exactly
    # the heteronym case this feature exists for.
    with (raw / "graphics.txt").open("a", encoding="utf-8") as fh:
        fh.write(
            '\n{"character":"乐","strokes":["M 0 0 Z"],'
            '"medians":[[[100,600],[900,600]],[[512,700],[512,200]]]}\n'
        )
    with (raw / "hanziDB.csv").open("a", encoding="utf-8") as fh:
        fh.write("5,乐,lè,happy,丿,4.0,5,1,5,300\n")
    with gzip.open(raw / "cedict.txt.gz", "rt", encoding="utf-8") as fh:
        existing = fh.read()
    extra = (fixtures / "cedict_chars_sample.u8").read_text(encoding="utf-8")
    with gzip.open(raw / "cedict.txt.gz", "wt", encoding="utf-8") as fh:
        fh.write(existing + "\n" + extra)

    db = tmp_path / "db.sqlite"
    report = build(raw, db)
    store = Store.open(db)
    # 乐 is drawable here, so its second CC-CEDICT reading was harvested…
    assert {cp for cp, _py, _rank in store.chars_for_reading("le", limit=5)} == {ord("乐")}
    assert {cp for cp, _py, _rank in store.chars_for_reading("lao", limit=5)} == {ord("乐")}
    # …while 行 is not drawable in these fixtures, so nothing was inserted for it
    assert store.chars_for_reading("hang", limit=5) == []
    assert store.chars_for_reading("xing", limit=5) == []
    assert report.extra_readings == 1


def test_build_does_not_duplicate_a_reading_it_already_has(tmp_path, fixtures):
    raw = _raw(tmp_path, fixtures)
    with gzip.open(raw / "cedict.txt.gz", "rt", encoding="utf-8") as fh:
        existing = fh.read()
    with gzip.open(raw / "cedict.txt.gz", "wt", encoding="utf-8") as fh:
        fh.write(existing + "\n一 一 [yi1] /one/\n")
    db = tmp_path / "db.sqlite"
    build(raw, db)
    store = Store.open(db)
    rows = store.chars_for_reading("yi", limit=10)
    assert len([r for r in rows if r[0] == ord("一")]) == 1

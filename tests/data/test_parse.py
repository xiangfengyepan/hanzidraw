import pytest

from hanzidraw.data.parse import (
    DataFormatError,
    parse_cedict_line,
    parse_essay,
    parse_graphics_line,
    parse_hanzidb,
    to_em,
)


def test_to_em_centres_and_flips_y():
    assert to_em(512, 388) == (0, 0)
    assert to_em(1024, 388) == (512, 0)
    assert to_em(512, 900) == (0, -512)  # top of the em box is negative (y grows downward)
    assert to_em(512, -124) == (0, 512)


def test_parse_graphics_line_converts_medians_to_em_units(fixtures):
    lines = (fixtures / "graphics_sample.txt").read_text(encoding="utf-8").splitlines()
    rec = parse_graphics_line(lines[0])
    assert rec.char == "十"
    assert rec.medians == (((-412, -142), (388, -142)), ((0, -512), (0, 288)))
    assert len(rec.outline) == 2


def test_parse_graphics_line_skips_entries_without_medians(fixtures):
    lines = (fixtures / "graphics_sample.txt").read_text(encoding="utf-8").splitlines()
    assert parse_graphics_line(lines[2]) is None
    assert parse_graphics_line("not json") is None
    assert parse_graphics_line("") is None


def test_parse_graphics_line_rejects_valid_json_that_isnt_a_dict():
    assert parse_graphics_line("[1,2,3]") is None
    assert parse_graphics_line("42") is None
    assert parse_graphics_line('"str"') is None
    assert parse_graphics_line("null") is None


def test_parse_graphics_line_rejects_non_numeric_coordinates():
    assert (
        parse_graphics_line('{"character":"十","strokes":[],"medians":[[["x","y"],[1,2]]]}') is None
    )


def test_parse_graphics_line_rejects_coordinates_with_too_few_values():
    assert parse_graphics_line('{"character":"十","strokes":[],"medians":[[[1],[2,3]]]}') is None


def test_parse_graphics_line_rejects_entry_with_any_unparseable_stroke():
    assert (
        parse_graphics_line(
            '{"character":"十","strokes":[],"medians":[[[100,500],[900,500]],[[1,2],["x","y"]]]}'
        )
        is None
    )


def test_parse_hanzidb_reads_readings_rank_and_strokes(fixtures):
    rows = parse_hanzidb((fixtures / "hanzidb_sample.csv").read_text(encoding="utf-8"))
    by_char = {r.char: r for r in rows}
    assert by_char["十"].freq_rank == 131
    assert by_char["十"].nstroke == 2
    assert by_char["十"].readings == ("shi",)
    assert by_char["长"].readings == ("chang", "zhang")


def test_parse_hanzidb_names_the_missing_column(fixtures):
    with pytest.raises(DataFormatError) as exc:
        parse_hanzidb("character,pinyin\n十,shi\n")
    assert "frequency_rank" in str(exc.value)
    assert "character" in str(exc.value)  # the error lists what it did find


def test_parse_hanzidb_accepts_the_upstream_charcter_typo():
    # Real hanziDB.csv misspells "character" as "charcter"; both must work.
    rows = parse_hanzidb("charcter,pinyin,stroke_count,frequency_rank\n十,shi2,2,131\n")
    assert rows[0].char == "十"
    assert rows[0].freq_rank == 131


def test_parse_hanzidb_raises_when_neither_character_spelling_is_present():
    with pytest.raises(DataFormatError) as exc:
        parse_hanzidb("hanzi,pinyin,stroke_count,frequency_rank\n十,shi2,2,131\n")
    assert "character" in str(exc.value)
    assert "hanzi" in str(exc.value)  # the error lists what it did find


def test_parse_hanzidb_collects_unknown_syllables_and_skips_the_row():
    unknown: set[str] = set()
    rows = parse_hanzidb(
        "character,pinyin,stroke_count,frequency_rank\n啊,xq,1,1\n", unknown=unknown
    )
    assert unknown == {"xq"}
    assert rows == []


def test_parse_cedict_takes_the_simplified_form_and_a_toneless_key():
    entry = parse_cedict_line("北京 北京 [Bei3 jing1] /Beijing, capital of China/")
    assert entry.text == "北京"
    assert entry.pinyin_key == "beijing"
    assert parse_cedict_line("中國 中国 [Zhong1 guo2] /China/").text == "中国"


def test_parse_cedict_rejects_comments_and_non_hanzi_entries():
    assert parse_cedict_line("# CC-CEDICT") is None
    assert parse_cedict_line("") is None
    assert parse_cedict_line("AA制 AA制 [A A zhi4] /to split the bill/") is None


def test_parse_cedict_rejects_a_key_that_is_not_all_legal_syllables():
    assert parse_cedict_line("啊呀 啊呀 [a1 xq1] /oh/") is None


def test_parse_essay_reads_word_and_weight(fixtures):
    pairs = parse_essay((fixtures / "essay_sample.txt").read_text(encoding="utf-8"))
    assert ("中国", 918273.0) in pairs
    assert len(pairs) == 3

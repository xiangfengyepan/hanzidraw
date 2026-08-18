import pytest

from hanzidraw.ime.syllables import (
    MAX_SYLLABLE_LEN,
    SYLLABLES,
    is_syllable,
    is_syllable_prefix,
    normalise_pinyin,
    split_readings,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("fēng", "feng"),
        ("hǎo", "hao"),
        ("lǜ", "lv"),
        ("nu:3", "nv"),
        ("Bei3", "bei"),
        ("  JING1 ", "jing"),
        ("xu:e4", "xve"),
    ],
)
def test_normalise_strips_tones_case_and_maps_u_umlaut(raw, expected):
    assert normalise_pinyin(raw) == expected


def test_split_readings_handles_every_separator_the_sources_use():
    assert split_readings("zhǎng/cháng") == ("zhang", "chang")
    assert split_readings("hao3, hao4") == ("hao", "hao")
    assert split_readings("bei3 jing1") == ("bei", "jing")
    assert split_readings("") == ()


def test_inventory_contains_real_syllables_and_rejects_impossible_ones():
    for good in ("a", "er", "feng", "zhuang", "lv", "nve", "xian", "shui", "n", "ng"):
        assert is_syllable(good), good
    for bad in ("", "q", "xg", "fenq", "zzz", "iang", "vv"):
        assert not is_syllable(bad), bad


def test_max_syllable_len_matches_the_inventory():
    assert max(len(s) for s in SYLLABLES) == MAX_SYLLABLE_LEN


def test_prefix_test_accepts_partial_typing_and_rejects_dead_ends():
    assert is_syllable_prefix("zhu")
    assert is_syllable_prefix("x")
    assert not is_syllable_prefix("xq")
    assert not is_syllable_prefix("")

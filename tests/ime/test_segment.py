from hanzidraw.ime.segment import Segmentation, segment


def test_single_syllable():
    assert segment("feng") == [Segmentation(("feng",), True, "")]


def test_multi_syllable_word():
    best = segment("beijing")[0]
    assert best.syllables == ("bei", "jing")
    assert best.display == "bei'jing"
    assert best.key == "beijing"


def test_prefers_fewest_syllables():
    # "xian" is one syllable, not xi+an
    assert segment("xian")[0].syllables == ("xian",)


def test_apostrophe_forces_the_boundary():
    assert segment("xi'an")[0].syllables == ("xi", "an")
    assert segment("nan'an")[0].syllables == ("nan", "an")


def test_ambiguous_input_offers_the_alternative_second():
    alts = segment("xian")
    assert alts[0].syllables == ("xian",)
    assert ("xi", "an") in [a.syllables for a in alts]


def test_ng_boundary_is_resolved_toward_fewer_syllables():
    # "fangan" -> fang'an (2) rather than fan'gan (2); tie broken by longest first syllable
    assert segment("fangan")[0].syllables == ("fang", "an")


def test_incomplete_tail_is_reported_as_partial():
    seg = segment("beij")[0]
    assert seg.syllables == ("bei",)
    assert seg.complete is False
    assert seg.partial == "j"
    assert seg.display == "bei'j"


def test_input_that_cannot_start_a_syllable_yields_no_segmentation():
    assert segment("qx") == []


def test_empty_input_yields_nothing():
    assert segment("") == []


def test_alternatives_are_capped_and_deterministic():
    alts = segment("nihaoma", max_alternatives=2)
    assert len(alts) <= 2
    assert alts == segment("nihaoma", max_alternatives=2)


def test_ambiguous_returns_exactly_two_by_default():
    # With fixed ranking, xian returns exactly [("xian",), ("xi","an")]
    alts = segment("xian")
    assert len(alts) == 2
    assert alts[0].syllables == ("xian",)
    assert alts[1].syllables == ("xi", "an")


def test_interjection_syllables_penalised_in_ranking():
    # ("bei","ji","ng") should not appear in beijing results
    alts = segment("beijing")
    assert alts[0].syllables == ("bei", "jing")
    syllable_lists = [a.syllables for a in alts]
    assert ("bei", "ji", "ng") not in syllable_lists


def test_greedy_tie_break_survives_interjection_penalty():
    # fangan still prefers fang'an over fan'gan despite fan not being junk
    alts = segment("fangan")
    assert alts[0].syllables == ("fang", "an")


def test_long_input_exceeding_max_returns_empty():
    # Inputs longer than 32 chars return empty list
    result = segment("a" * 33)
    assert result == []


def test_long_all_ambiguous_input_is_bounded():
    # 32 chars of all-ambiguous input completes and is bounded
    result = segment("a" * 32)
    assert isinstance(result, list)
    assert len(result) <= 2


def test_very_long_all_ambiguous_input_no_exception():
    # 2000 chars should not raise RecursionError
    result = segment("a" * 2000)
    assert result == []


def test_pathological_all_ambiguous_input_completes():
    # an*16 (32 chars) should complete without RecursionError
    result = segment("an" * 16)
    assert isinstance(result, list)
    assert len(result) <= 2


def test_trailing_apostrophe_ignored():
    # segment("xian'") should work like segment("xian")
    result = segment("xian'")
    assert len(result) > 0
    assert result[0].syllables == ("xian",)


def test_leading_apostrophe_ignored():
    # segment("'xian") should work like segment("xian")
    result = segment("'xian")
    assert len(result) > 0
    assert result[0].syllables == ("xian",)


def test_only_apostrophes_yields_nothing():
    # segment("'") and segment("''") should return []
    assert segment("'") == []
    assert segment("''") == []

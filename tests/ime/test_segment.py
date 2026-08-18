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

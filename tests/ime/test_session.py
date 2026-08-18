from hanzidraw.ime.session import Key, Session
from hanzidraw.ime.sources import Candidate


class FakeSource:
    """Returns one candidate per syllable plus a phrase for the whole key."""

    def lookup(self, seg, limit):
        out = []
        if seg.syllables:
            first = seg.syllables[0]
            out.append(Candidate(f"<{first}>", (ord("一"),), "char", 10.0, 1))
        if len(seg.syllables) > 1:
            text = "".join(f"[{s}]" for s in seg.syllables)
            out.append(
                Candidate(
                    text,
                    tuple(ord("一") for _ in seg.syllables),
                    "phrase",
                    100.0,
                    len(seg.syllables),
                )
            )
        return out


class OverConsumingSource:
    """Always returns one phrase candidate that consumes more syllables than
    the segmentation has -- mirrors the real xian/西安 case (Candidate.consumed
    may exceed the segmentation's syllable count)."""

    def lookup(self, seg, limit):
        return [Candidate("西安", (ord("西"), ord("安")), "phrase", 100.0, 2)]


def _type(session, text):
    state = session.state
    for ch in text:
        state = session.feed(Key(ch))
    return state


def test_typing_builds_the_preedit_and_shows_candidates():
    session = Session([FakeSource()])
    state = _type(session, "beijing")
    assert state.preedit == "beijing"
    assert state.display == "bei'jing"
    assert state.page
    assert state.highlight == 0


def test_space_commits_the_highlighted_candidate():
    session = Session([FakeSource()])
    _type(session, "beijing")
    session.feed(Key("space"))
    commits = session.take_commits()
    assert len(commits) == 1
    assert commits[0].text.startswith("[bei]")
    assert session.take_commits() == []  # the queue is drained


def test_committing_a_phrase_clears_the_whole_preedit():
    session = Session([FakeSource()])
    _type(session, "beijing")
    state = session.feed(Key("space"))
    assert state.preedit == ""
    assert state.page == ()


def test_committing_a_single_character_leaves_the_rest_composing():
    session = Session([FakeSource()])
    _type(session, "beijing")
    # the char candidate for the first syllable is second in the fake ordering
    state = session.feed(Key("2"))
    assert session.take_commits()[0].text == "<bei>"
    assert state.preedit == "jing"


def test_digits_select_by_position_on_the_current_page():
    session = Session([FakeSource()], page_size=2)
    _type(session, "beijing")
    session.feed(Key("1"))
    assert session.take_commits()[0].text.startswith("[")


def test_digits_are_ignored_with_an_empty_preedit():
    session = Session([FakeSource()])
    state = session.feed(Key("5"))
    assert state.preedit == ""
    assert session.take_commits() == []


def test_arrows_and_tab_move_the_highlight_without_wrapping_past_the_page():
    session = Session([FakeSource()])
    _type(session, "beijing")
    assert session.feed(Key("right")).highlight == 1
    assert session.feed(Key("right")).highlight == 1  # only two candidates
    assert session.feed(Key("left")).highlight == 0
    assert session.feed(Key("tab")).highlight == 1


def test_page_keys_move_between_pages_and_reset_the_highlight():
    session = Session([FakeSource()], page_size=1)
    _type(session, "beijing")
    state = session.feed(Key("equal"))
    assert state.page_index == 1
    assert state.highlight == 0
    assert session.feed(Key("minus")).page_index == 0


def test_backspace_removes_one_letter_and_refreshes_candidates():
    session = Session([FakeSource()])
    _type(session, "beijing")
    state = session.feed(Key("backspace"))
    assert state.preedit == "beijin"


def test_escape_clears_the_composition():
    session = Session([FakeSource()])
    _type(session, "beijing")
    state = session.feed(Key("escape"))
    assert state.preedit == ""
    assert state.page == ()
    assert session.feed(Key("escape")).preedit == ""


def test_apostrophe_is_part_of_the_preedit_and_forces_a_boundary():
    session = Session([FakeSource()])
    _type(session, "xi")
    state = session.feed(Key("apostrophe"))
    state = _type(session, "an")
    assert state.preedit == "xi'an"
    assert state.display == "xi'an"


def test_enter_commits_like_space():
    session = Session([FakeSource()])
    _type(session, "bei")
    session.feed(Key("enter"))
    assert session.take_commits()


def test_commands_emit_actions_and_do_not_touch_the_preedit():
    session = Session([FakeSource()])
    _type(session, "bei")
    assert session.feed(Key("f2")).actions == ("toggle_mode",)
    assert session.feed(Key("z", ctrl=True)).actions == ("undo",)
    assert session.feed(Key("l", ctrl=True)).actions == ("clear",)
    assert session.feed(Key("s", ctrl=True)).actions == ("save",)
    assert session.feed(Key("r", ctrl=True)).actions == ("replay",)
    assert session.feed(Key("period", ctrl=True)).actions == ("abort",)
    assert session.state.preedit == "bei"


def test_actions_are_cleared_on_the_next_key():
    session = Session([FakeSource()])
    session.feed(Key("f2"))
    assert session.feed(Key("b")).actions == ()


def test_a_learned_pick_is_promoted_on_the_next_composition(tmp_path):
    from hanzidraw.ime.learn import Learn

    learn = Learn(tmp_path / "l.json")
    session = Session([FakeSource()], learn=learn)
    _type(session, "beijing")
    session.feed(Key("2"))  # pick the character, not the phrase
    session.take_commits()
    session.feed(Key("escape"))
    state = _type(session, "beijing")
    assert state.page[0].text == "<bei>"


def test_committing_a_candidate_that_overconsumes_clears_the_preedit_without_raising():
    # segment("xian") is one syllable, but a real phrase candidate for it (e.g.
    # 西安) can have consumed=2. Committing it must slice, not index or assert,
    # so the preedit clears cleanly instead of raising.
    session = Session([OverConsumingSource()])
    _type(session, "xian")
    state = session.feed(Key("space"))
    assert session.take_commits()[0].text == "西安"
    assert state.preedit == ""
    assert state.page == ()

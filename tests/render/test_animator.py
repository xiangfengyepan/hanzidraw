import pytest

from hanzidraw.render.animator import Timeline, Timing, ease
from hanzidraw.render.glyph import Glyph

GLYPH = Glyph((((0.0, 0.0), (10.0, 0.0)), ((0.0, 5.0), (10.0, 5.0))))
TIMING = Timing(stroke_ms=100.0, gap_ms=50.0, easing="linear")


def test_total_duration_covers_every_stroke_and_the_gaps_between():
    assert Timeline(GLYPH, TIMING).total_ms == pytest.approx(250.0)


def test_nothing_is_drawn_before_time_zero():
    assert Timeline(GLYPH, TIMING).at(-10.0).strokes == ()


def test_a_stroke_is_revealed_progressively():
    partial = Timeline(GLYPH, TIMING).at(50.0)
    assert len(partial.strokes) == 1
    assert partial.strokes[0][-1][0] == pytest.approx(5.0)


def test_a_completed_stroke_stays_complete_during_the_gap():
    partial = Timeline(GLYPH, TIMING).at(120.0)
    assert len(partial.strokes) == 1
    assert partial.strokes[0] == GLYPH.strokes[0]


def test_all_strokes_are_present_at_the_end_and_after():
    timeline = Timeline(GLYPH, TIMING)
    assert timeline.at(timeline.total_ms).strokes == GLYPH.strokes
    assert timeline.at(timeline.total_ms + 5000.0).strokes == GLYPH.strokes


def test_stroke_progress_reports_the_active_stroke_and_fraction():
    timeline = Timeline(GLYPH, TIMING)
    assert timeline.stroke_progress(25.0) == (0, pytest.approx(0.25))
    assert timeline.stroke_progress(175.0) == (1, pytest.approx(0.25))
    assert timeline.stroke_progress(1000.0)[0] == len(GLYPH.strokes)


def test_the_timeline_is_deterministic():
    timeline = Timeline(GLYPH, TIMING)
    assert timeline.at(63.0) == timeline.at(63.0)


def test_easing_functions_hit_both_endpoints():
    for name in ("linear", "ease_in", "ease_out", "ease_in_out"):
        assert ease(name, 0.0) == pytest.approx(0.0)
        assert ease(name, 1.0) == pytest.approx(1.0)


def test_ease_out_starts_faster_than_linear():
    assert ease("ease_out", 0.25) > 0.25


def test_unknown_easing_falls_back_to_linear():
    assert ease("wobble", 0.3) == pytest.approx(0.3)


def test_zero_gap_still_produces_a_sane_timeline():
    timeline = Timeline(GLYPH, Timing(stroke_ms=100.0, gap_ms=0.0, easing="linear"))
    assert timeline.total_ms == pytest.approx(200.0)
    assert timeline.at(200.0).strokes == GLYPH.strokes


def test_timing_from_config_reads_the_animation_table(tmp_path):
    from hanzidraw.config import load_config

    timing = Timing.from_config(load_config(tmp_path / "missing.toml"))
    assert timing.stroke_ms == 380.0
    assert timing.easing == "ease_out"

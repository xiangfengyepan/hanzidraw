import math

from hanzidraw.render.glyph import Glyph, glyph_from_em, place, polyline_length, walk

# a horizontal stroke across the middle, and a vertical stroke down the middle
MEDIANS = (((-512, 0), (512, 0)), ((0, -512), (0, 512)))


def test_glyph_from_em_maps_the_em_box_onto_the_unit_box():
    glyph = glyph_from_em(MEDIANS)
    assert glyph.strokes[0][0] == (0.0, 0.5)
    assert glyph.strokes[0][1] == (1.0, 0.5)
    assert glyph.strokes[1][0] == (0.5, 0.0)  # top of the box
    assert glyph.strokes[1][1] == (0.5, 1.0)


def test_place_scales_and_offsets_into_pixels():
    glyph = place(glyph_from_em(MEDIANS), ox=100.0, oy=200.0, size=240.0)
    assert glyph.strokes[0][0] == (100.0, 320.0)
    assert glyph.strokes[0][1] == (340.0, 320.0)


def test_bounds_covers_every_stroke():
    assert glyph_from_em(MEDIANS).bounds() == (0.0, 0.0, 1.0, 1.0)


def test_polyline_length_sums_the_segments():
    assert polyline_length(((0.0, 0.0), (3.0, 4.0))) == 5.0
    assert polyline_length(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))) == 2.0
    assert polyline_length(((5.0, 5.0),)) == 0.0


def test_walk_at_zero_returns_just_the_start_point():
    assert walk(((0.0, 0.0), (10.0, 0.0)), 0.0) == ((0.0, 0.0),)


def test_walk_at_one_returns_the_whole_polyline():
    points = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0))
    assert walk(points, 1.0) == points


def test_walk_interpolates_the_cut_point():
    points = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0))
    partial = walk(points, 0.75)  # 15 of 20 units
    assert partial[-1] == (10.0, 5.0)
    assert len(partial) == 3


def test_walk_clamps_out_of_range_fractions():
    points = ((0.0, 0.0), (10.0, 0.0))
    assert walk(points, -1.0) == ((0.0, 0.0),)
    assert walk(points, 2.0) == points


def test_walk_of_a_zero_length_stroke_is_the_point_itself():
    assert walk(((3.0, 3.0), (3.0, 3.0)), 0.5) == ((3.0, 3.0), (3.0, 3.0))


def test_glyph_is_hashable_so_it_can_be_cached():
    assert isinstance(hash(glyph_from_em(MEDIANS)), int)


def test_empty_glyph_has_zero_bounds():
    assert Glyph(()).bounds() == (0.0, 0.0, 0.0, 0.0)
    assert math.isfinite(polyline_length(()))

import pytest

from hanzidraw.render.svgpath import Seg, outline_to_box, parse_path, svg_transform


def test_moveto_and_lineto_absolute():
    segs = parse_path("M 100 200 L 300 400")
    assert segs[0] == Seg("M", ((100.0, 200.0),))
    assert segs[1] == Seg("L", ((300.0, 400.0),))


def test_relative_commands_accumulate_from_the_current_point():
    segs = parse_path("m 100 100 l 10 20 l 10 0")
    assert segs[1] == Seg("L", ((110.0, 120.0),))
    assert segs[2] == Seg("L", ((120.0, 120.0),))


def test_horizontal_and_vertical_shorthands_become_linetos():
    segs = parse_path("M 10 10 H 50 V 90 h -20 v -10")
    assert [s.points[-1] for s in segs] == [
        (10.0, 10.0),
        (50.0, 10.0),
        (50.0, 90.0),
        (30.0, 90.0),
        (30.0, 80.0),
    ]


def test_quadratic_and_cubic_carry_their_control_points():
    segs = parse_path("M 0 0 Q 10 10 20 0 C 30 10 40 10 50 0")
    assert segs[1].kind == "Q" and len(segs[1].points) == 2
    assert segs[2].kind == "C" and len(segs[2].points) == 3
    assert segs[2].points[-1] == (50.0, 0.0)


def test_repeated_coordinate_pairs_reuse_the_command():
    segs = parse_path("M 0 0 L 10 0 20 0")
    assert [s.kind for s in segs] == ["M", "L", "L"]


def test_close_path_and_comma_separators():
    segs = parse_path("M0,0L10,0Z")
    assert segs[-1] == Seg("Z", ())


def test_unknown_command_is_rejected_loudly():
    with pytest.raises(ValueError, match="A"):
        parse_path("M 0 0 A 1 1 0 0 1 10 10")


def test_arc_with_realistic_arguments_is_rejected_by_name():
    # Pinned against data that looks like a real SVG elliptical arc (rx ry
    # x-axis-rotation large-arc-flag sweep-flag x y), not just the brief's
    # minimal synthetic case: if the tokenizer ever regresses to matching
    # only the supported command letters, an arc like this one is silently
    # misparsed instead of raising -- see the comment on _TOKEN.
    with pytest.raises(ValueError, match="A"):
        parse_path("M 100 100 L 150 100 A 50 30 0 1 0 250 100 L 300 100")


def test_empty_path_is_no_segments():
    assert parse_path("") == ()
    assert parse_path("   ") == ()


def test_outline_to_box_matches_the_median_mapping():
    # the em-box centre (512, 388) must land in the middle of the placed box,
    # exactly where glyph_from_em puts it
    from hanzidraw.render.glyph import glyph_from_em, place

    seg = outline_to_box(Seg("M", ((512.0, 388.0),)), ox=0.0, oy=0.0, size=100.0)
    centre = place(glyph_from_em((((0, 0),),)), 0.0, 0.0, 100.0).strokes[0][0]
    assert seg.points[0] == pytest.approx(centre)


def test_outline_to_box_flips_y():
    top = outline_to_box(Seg("M", ((512.0, 900.0),)), 0.0, 0.0, 100.0).points[0]
    bottom = outline_to_box(Seg("M", ((512.0, -124.0),)), 0.0, 0.0, 100.0).points[0]
    assert top[1] < bottom[1]


def test_svg_transform_is_a_usable_attribute_value():
    text = svg_transform(10.0, 20.0, 200.0)
    assert "translate(10" in text
    assert "scale(" in text

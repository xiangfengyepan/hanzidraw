"""Validation and failure-reporting behaviour of the `draw` subcommand.

Every case here builds its own tiny store in tmp_path — never the real
database — so these tests stay fast, deterministic, and offline.
"""

from __future__ import annotations

import os

import pytest

from hanzidraw import cli
from hanzidraw.data.store import Store


def _make_store(path):
    store = Store.create(path)
    store.add_char(ord("沣"), 1, 7, (((-512, 0), (512, 0)),), None)
    store.finish()
    store.close()
    return path


@pytest.mark.parametrize(
    "flag,value",
    [("--columns", "0"), ("--columns", "-1"), ("--size", "0"), ("--size", "-5")],
)
def test_bad_numeric_flags_are_rejected_and_write_nothing(tmp_path, capsys, flag, value):
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), flag, value])

    captured = capsys.readouterr()
    assert rc == 1
    assert value in captured.err
    assert "Traceback" not in captured.err
    assert not out.exists()


def test_empty_color_is_rejected(tmp_path, capsys):
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--color", ""])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert not out.exists()


def test_a_malformed_color_is_rejected_with_a_clean_message(tmp_path, capsys):
    # I1: the CLI used to validate --color for emptiness only, so a value
    # config.toml would reject outright (not a hex triplet, not one of the
    # 20 named colours) sailed straight through here and reached Qt/the SVG
    # backend as a bare, unvalidated string.
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--color", "not a colour"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "not a colour" in captured.err
    assert not out.exists()


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_or_whitespace_only_text_is_rejected(tmp_path, capsys, text):
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", text, "-o", str(out), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "nothing to draw" in captured.err
    assert "Traceback" not in captured.err
    assert not out.exists()


def test_unwritable_destination_reports_a_message_not_a_traceback(tmp_path, capsys):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write permissions")

    db = _make_store(tmp_path / "db.sqlite")
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    out = ro_dir / "x.svg"
    ro_dir.chmod(0o555)
    try:
        rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db)])
    finally:
        ro_dir.chmod(0o755)

    captured = capsys.readouterr()
    assert rc == 1
    assert "could not write" in captured.err
    assert "Traceback" not in captured.err
    assert not out.exists()


def test_destination_whose_parent_is_a_plain_file_reports_a_message(tmp_path, capsys):
    db = _make_store(tmp_path / "db.sqlite")
    blocker = tmp_path / "notadir"
    blocker.write_text("not a directory", encoding="utf-8")
    out = blocker / "x.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "could not write" in captured.err
    assert "Traceback" not in captured.err


def test_size_one_and_columns_one_still_work(tmp_path, capsys):
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--size", "1", "--columns", "1"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "wrote" in captured.out
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<svg")


# Seven trivial strokes, one per row, so the "shape" of the output (polyline
# count vs path count) mirrors what the coordinator measured against the real
# database for 沣 (7 strokes): "polylines: 7   filled paths: 0" in brush mode.
_SEVEN_STROKE_MEDIANS = tuple(((-400, y), (400, y)) for y in range(-300, 400, 100))
_OUTLINE = ("M 100 500 L 900 500 L 900 560 L 100 560 Z",)


def _make_store_with_outline(path):
    """A store whose one character has both medians and an outline."""
    store = Store.create(path)
    store.add_char(ord("沣"), 1, 7, _SEVEN_STROKE_MEDIANS, _OUTLINE)
    store.finish()
    store.close()
    return path


def _make_medians_only_store(path):
    """A store built as if by `fetch-data --medians-only`: no outlines at all."""
    store = Store.create(path)
    store.add_char(ord("沣"), 1, 7, _SEVEN_STROKE_MEDIANS, None)
    store.set_meta("build_medians_only", "1")
    store.finish()
    store.close()
    return path


def test_outline_style_emits_filled_paths_and_no_polylines(tmp_path, capsys):
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text('[glyph]\nstyle = "outline"\n', encoding="utf-8")

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Traceback" not in captured.out and "Traceback" not in captured.err
    svg = out.read_text(encoding="utf-8")
    assert "<path" in svg
    assert "<polyline" not in svg


def test_default_brush_style_is_unchanged_by_the_outline_feature(tmp_path, capsys):
    # Same store as the outline test above -- it has an outline too -- so this
    # proves brush mode really ignores it rather than happening to pass by
    # having no outline data to pick up.
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db)])

    assert rc == 0
    svg = out.read_text(encoding="utf-8")
    assert svg.count("<polyline") == 7
    assert svg.count("<path") == 0


def test_outline_style_falls_back_to_polylines_on_a_medians_only_database(tmp_path, capsys):
    db = _make_medians_only_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text('[glyph]\nstyle = "outline"\n', encoding="utf-8")

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Traceback" not in captured.out and "Traceback" not in captured.err
    svg = out.read_text(encoding="utf-8")
    assert svg.count("<polyline") == 7
    assert "<path" not in svg
    assert "medians-only" in captured.out


def test_outline_mode_svg_output_is_byte_stable(tmp_path):
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text('[glyph]\nstyle = "outline"\n', encoding="utf-8")
    out1 = tmp_path / "out1.svg"
    out2 = tmp_path / "out2.svg"

    cli.main(["draw", "沣", "-o", str(out1), "--db", str(db), "--config", str(cfg_path)])
    cli.main(["draw", "沣", "-o", str(out2), "--db", str(db), "--config", str(cfg_path)])

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


def test_stroke_numbers_label_every_stroke_in_single_mode(tmp_path, capsys):
    # glyph.stroke_numbers was documented in spec §6 and the README and never
    # implemented: it validated and then did nothing at all.
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text(
        '[glyph]\nstroke_numbers = true\n[canvas]\nmode = "single"\n', encoding="utf-8"
    )

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)])

    assert rc == 0
    svg = out.read_text(encoding="utf-8")
    assert svg.count("<text") == 7  # one per stroke of the 7-stroke fixture
    for number in range(1, 8):
        assert f">{number}</text>" in svg


def test_stroke_numbers_off_emits_no_labels(tmp_path, capsys):
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text(
        '[glyph]\nstroke_numbers = false\n[canvas]\nmode = "single"\n', encoding="utf-8"
    )

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)])

    assert rc == 0
    assert "<text" not in out.read_text(encoding="utf-8")


def test_stroke_numbers_are_not_drawn_in_sheet_mode(tmp_path, capsys):
    # Spec §6 puts stroke-order numbers in `single` mode only: a sheet of
    # practice cells numbered stroke-by-stroke would be unreadable.
    db = _make_store_with_outline(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text(
        '[glyph]\nstroke_numbers = true\n[canvas]\nmode = "sheet"\n', encoding="utf-8"
    )

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)])

    assert rc == 0
    assert "<text" not in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["out.txt", "out", "out.jpeg"])
def test_an_unrecognised_output_suffix_is_a_clean_validation_error(tmp_path, capsys, name):
    # `draw -o out.txt` used to write SVG under a non-SVG suffix in silence.
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / name

    rc = cli.main(["draw", "沣", "-o", str(out), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert ".svg" in captured.err and ".png" in captured.err
    assert "Traceback" not in captured.err
    assert not out.exists()


def _make_store_with_eight(path):
    store = Store.create(path)
    for index, ch in enumerate("一二三四五六七八"):
        store.add_char(ord(ch), index + 1, 1, (((-400, 0), (400, 0)),), None)
    store.finish()
    store.close()
    return path


def _svg_origins(svg: str) -> list[tuple[float, float]]:
    """The (ox, oy) of each glyph group the backend emitted."""
    return [
        (float(parts[0]), float(parts[1]))
        for parts in (chunk.split('"')[0].split(",") for chunk in svg.split('data-glyph="')[1:])
    ]


def _svg_size(svg: str) -> tuple[int, int]:
    return (
        int(svg.split('width="')[1].split('"')[0]),
        int(svg.split('height="')[1].split('"')[0]),
    )


def test_draw_places_cells_exactly_where_the_sheet_does(tmp_path):
    # I4: cli.py and render/sheet.py computed cell origins with two
    # character-for-character identical formulas, so they agreed only by textual
    # coincidence. The sheet is now the single source.
    from hanzidraw.config import load_config
    from hanzidraw.render.glyph import Glyph
    from hanzidraw.render.sheet import Sheet

    db = _make_store_with_eight(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text("", encoding="utf-8")
    cfg = load_config(cfg_path)

    rc = cli.main(
        ["draw", "一二三四五六七八", "-o", str(out), "--db", str(db), "--config", str(cfg_path)]
    )
    assert rc == 0

    sheet = Sheet(
        columns=int(cfg.get("canvas.columns")),
        advance=float(cfg.get("canvas.advance")),
        size=float(cfg.get("glyph.size_px")),
        wrap=bool(cfg.get("canvas.wrap")),
    )
    expected = [
        (placed.ox, placed.oy) for placed in [sheet.add(Glyph(()), ch) for ch in "一二三四五六七八"]
    ]
    assert _svg_origins(out.read_text(encoding="utf-8")) == expected


def test_draw_honours_canvas_wrap(tmp_path):
    # `draw` never read canvas.wrap at all: at index 7 with wrap = false the
    # sheet gives (1950.0, 18.0) and the old CLI formula gave (294.0, 294.0).
    db = _make_store_with_eight(tmp_path / "db.sqlite")
    text = "一二三四五六七八"

    wrapped = tmp_path / "wrap.toml"
    wrapped.write_text("[canvas]\nwrap = true\n", encoding="utf-8")
    out_wrapped = tmp_path / "wrapped.svg"
    assert (
        cli.main(["draw", text, "-o", str(out_wrapped), "--db", str(db), "--config", str(wrapped)])
        == 0
    )

    flat = tmp_path / "flat.toml"
    flat.write_text("[canvas]\nwrap = false\n", encoding="utf-8")
    out_flat = tmp_path / "flat.svg"
    assert (
        cli.main(["draw", text, "-o", str(out_flat), "--db", str(db), "--config", str(flat)]) == 0
    )

    wrapped_svg = out_wrapped.read_text(encoding="utf-8")
    flat_svg = out_flat.read_text(encoding="utf-8")
    pitch = 240.0 * 1.15  # glyph.size_px * canvas.advance, the stock defaults
    pad = (pitch - 240.0) / 2.0

    # wrap = true: six columns then a second row.
    assert _svg_origins(wrapped_svg)[6] == (pad, pad + pitch)
    assert _svg_size(wrapped_svg) == (int(6 * pitch), int(2 * pitch))

    # wrap = false: one long row, which is what the sheet has always done.
    assert _svg_origins(flat_svg)[7] == (pad + 7 * pitch, pad)
    assert _svg_size(flat_svg) == (int(8 * pitch), int(pitch))


def test_draw_canvas_size_is_unchanged_for_a_partial_row(tmp_path):
    # A one-character render must still be one cell, not a whole blank sheet.
    db = _make_store(tmp_path / "db.sqlite")
    out = tmp_path / "out.svg"
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text("", encoding="utf-8")

    assert cli.main(["draw", "沣", "-o", str(out), "--db", str(db), "--config", str(cfg_path)]) == 0
    assert _svg_size(out.read_text(encoding="utf-8")) == (276, 276)

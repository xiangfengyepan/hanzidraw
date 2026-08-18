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

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

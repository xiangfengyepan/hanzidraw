import dataclasses
import gzip

import pytest

from hanzidraw import cli
from hanzidraw.cli import main
from hanzidraw.data import sources


def _raw_without_hanzidb(tmp_path, fixtures):
    """A raw dir with the three well-formed sources; the caller supplies hanziDB.csv."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "graphics.txt").write_text(
        (fixtures / "graphics_sample.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with gzip.open(raw / "cedict.txt.gz", "wt", encoding="utf-8") as fh:
        fh.write((fixtures / "cedict_sample.u8").read_text(encoding="utf-8"))
    (raw / "essay.txt").write_text(
        (fixtures / "essay_sample.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return raw


def test_fetch_data_reports_a_message_not_a_traceback_for_an_empty_hanzidb(
    tmp_path, fixtures, capsys, monkeypatch
):
    raw = _raw_without_hanzidb(tmp_path, fixtures)

    # hanziDB.csv is genuinely empty (0 bytes) and absent from `raw`, so the
    # cache-reuse check in _cmd_fetch_data won't treat it as already present;
    # it will be "downloaded" from a local file:// URL pointing at an empty
    # file, keeping the test off the real network while still exercising the
    # real fetch-then-build code path.
    empty_upstream = tmp_path / "upstream-hanziDB.csv"
    empty_upstream.write_text("", encoding="utf-8")
    patched_sources = tuple(
        dataclasses.replace(s, url=empty_upstream.resolve().as_uri()) if s.name == "hanzidb" else s
        for s in sources.SOURCES
    )
    monkeypatch.setattr(sources, "SOURCES", patched_sources)

    db = tmp_path / "db.sqlite"
    rc = cli.main(["fetch-data", "--raw-dir", str(raw), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "column" in captured.err
    assert not db.exists()


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in ("run", "fetch-data", "draw", "export-firmware"):
        assert command in out


def test_draw_reports_a_missing_database(tmp_path, capsys):
    code = main(
        ["draw", "十", "-o", str(tmp_path / "o.svg"), "--db", str(tmp_path / "none.sqlite")]
    )
    assert code == 1
    assert "fetch-data" in capsys.readouterr().err


def test_draw_writes_an_svg_from_a_small_database(tmp_path):
    from hanzidraw.data.store import Store

    db = tmp_path / "db.sqlite"
    store = Store.create(db)
    store.add_char(ord("十"), 1, 2, (((-512, 0), (512, 0)), ((0, -512), (0, 512))), None)
    store.finish()
    store.close()
    out = tmp_path / "o.svg"
    assert (
        main(["draw", "十", "-o", str(out), "--db", str(db), "--config", str(tmp_path / "n.toml")])
        == 0
    )
    assert out.read_text(encoding="utf-8").count("<polyline") == 2


def test_export_firmware_reports_a_missing_database(tmp_path, capsys):
    code = main(
        ["export-firmware", "-o", str(tmp_path / "h.c"), "--db", str(tmp_path / "n.sqlite")]
    )
    assert code == 1


def test_fetch_data_reports_a_message_not_a_traceback_for_an_unrecognised_header(
    tmp_path, fixtures, capsys
):
    raw = _raw_without_hanzidb(tmp_path, fixtures)
    (raw / "hanziDB.csv").write_text("foo,bar\n1,2\n", encoding="utf-8")

    db = tmp_path / "db.sqlite"
    rc = cli.main(["fetch-data", "--raw-dir", str(raw), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "column" in captured.err
    assert not db.exists()


def test_fetch_data_reports_a_message_not_a_traceback_for_a_corrupt_gzip_source(
    tmp_path, fixtures, capsys, monkeypatch
):
    """A corrupt cached download is a message naming the file, not a traceback.

    The cedict source URL is redirected at a local corrupt file, so the test is
    offline and behaves the same whether the cached copy is reused or refetched.
    """
    raw = _raw_without_hanzidb(tmp_path, fixtures)
    (raw / "hanziDB.csv").write_text(
        (fixtures / "hanzidb_sample.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    corrupt = tmp_path / "upstream-cedict.txt.gz"
    corrupt.write_bytes(b"this is not a gzip stream")
    (raw / "cedict.txt.gz").write_bytes(corrupt.read_bytes())
    patched_sources = tuple(
        dataclasses.replace(s, url=corrupt.resolve().as_uri()) if s.name == "cedict" else s
        for s in sources.SOURCES
    )
    monkeypatch.setattr(sources, "SOURCES", patched_sources)

    db = tmp_path / "db.sqlite"
    rc = cli.main(["fetch-data", "--raw-dir", str(raw), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "cedict.txt.gz" in captured.err
    assert "--refetch" in captured.err
    assert not db.exists()
    assert not db.with_suffix(".sqlite.tmp").exists()


def test_fetch_data_refetches_a_corrupt_cached_download(tmp_path, fixtures, capsys, monkeypatch):
    """A non-empty file said nothing about whether it could be read back.

    A truncated compressed cache was reused on the strength of st_size > 0
    alone, which is the live route into a failed build.
    """
    raw = _raw_without_hanzidb(tmp_path, fixtures)
    (raw / "hanziDB.csv").write_text(
        (fixtures / "hanzidb_sample.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # A good replacement upstream, served from a local file:// URL…
    upstream = tmp_path / "upstream-cedict.txt.gz"
    with gzip.open(upstream, "wt", encoding="utf-8") as fh:
        fh.write((fixtures / "cedict_sample.u8").read_text(encoding="utf-8"))
    patched_sources = tuple(
        dataclasses.replace(s, url=upstream.resolve().as_uri()) if s.name == "cedict" else s
        for s in sources.SOURCES
    )
    monkeypatch.setattr(sources, "SOURCES", patched_sources)
    # …and a corrupt but non-empty cached copy.
    (raw / "cedict.txt.gz").write_bytes(b"truncated, not a gzip stream")

    db = tmp_path / "db.sqlite"
    rc = cli.main(["fetch-data", "--raw-dir", str(raw), "--db", str(db)])

    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "cedict.txt.gz" in captured.out
    assert "re-downloading" in captured.out
    assert "reusing cedict.txt.gz" not in captured.out
    assert db.exists()

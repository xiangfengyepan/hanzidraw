import dataclasses
import gzip

from hanzidraw import cli
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

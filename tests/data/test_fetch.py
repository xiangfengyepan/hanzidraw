import hashlib

import pytest

from hanzidraw.data.fetch import FetchError, download, fetch_all
from hanzidraw.data.sources import SOURCES, Source


def _file_url(path):
    return path.resolve().as_uri()


def test_sources_are_declared_with_licences_and_one_optional():
    assert {s.name for s in SOURCES} >= {"graphics", "hanzidb", "cedict"}
    assert all(s.licence for s in SOURCES)
    assert any(not s.required for s in SOURCES)  # rime-essay is optional


def test_download_writes_the_file_and_returns_its_digest(tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello strokes")
    dest = tmp_path / "out" / "src.txt"
    digest = download(_file_url(src), dest)
    assert dest.read_bytes() == b"hello strokes"
    assert digest == hashlib.sha256(b"hello strokes").hexdigest()
    assert not (dest.parent / "src.txt.part").exists()


def test_download_reports_progress(tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(b"x" * 5000)
    seen = []
    download(
        _file_url(src), tmp_path / "o.txt", progress=lambda got, total: seen.append(got), chunk=1024
    )
    assert seen and seen[-1] == 5000


def test_download_of_a_missing_url_raises_fetch_error(tmp_path):
    with pytest.raises(FetchError):
        download(_file_url(tmp_path / "nope.txt"), tmp_path / "o.txt")


def test_fetch_all_skips_a_failing_optional_source(tmp_path):
    good = tmp_path / "g.txt"
    good.write_bytes(b"ok")
    sources = (
        Source("required", _file_url(good), "g.txt", True, "CC0"),
        Source("optional", _file_url(tmp_path / "missing.txt"), "m.txt", False, "CC0"),
    )
    digests = fetch_all(tmp_path / "raw", sources=sources)
    assert "required" in digests
    assert "optional" not in digests


def test_fetch_all_fails_loudly_on_a_missing_required_source(tmp_path):
    sources = (Source("required", _file_url(tmp_path / "missing.txt"), "m.txt", True, "CC0"),)
    with pytest.raises(FetchError) as exc:
        fetch_all(tmp_path / "raw", sources=sources)
    assert "required" in str(exc.value)

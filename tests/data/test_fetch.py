import hashlib

import pytest

from hanzidraw.data.fetch import FetchError, download, fetch_all, sha256_of_file
from hanzidraw.data.sources import SOURCES, Source


def _file_url(path):
    return path.resolve().as_uri()


def test_sources_are_declared_with_attribution_and_one_optional():
    assert {s.name for s in SOURCES} >= {"graphics", "hanzidb", "cedict"}
    assert all(s.attribution for s in SOURCES)
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


def test_download_raises_fetch_error_for_empty_url(tmp_path):
    with pytest.raises(FetchError) as exc:
        download("", tmp_path / "o.txt")
    assert "" in str(exc.value)


def test_download_raises_fetch_error_for_no_scheme_url(tmp_path):
    with pytest.raises(FetchError) as exc:
        download("no-scheme-here", tmp_path / "o.txt")
    assert "no-scheme-here" in str(exc.value)


def test_download_raises_fetch_error_for_whitespace_url(tmp_path):
    with pytest.raises(FetchError) as exc:
        download(" ", tmp_path / "o.txt")
    assert " " in str(exc.value)


def test_sha256_of_file_agrees_with_hashlib(tmp_path):
    path = tmp_path / "data.bin"
    payload = b"the quick brown fox" * 1000
    path.write_bytes(payload)
    assert sha256_of_file(path) == hashlib.sha256(payload).hexdigest()


def test_is_readable_rejects_a_corrupt_gzip_and_accepts_a_good_one(tmp_path):
    import gzip

    from hanzidraw.data.fetch import is_readable

    good = tmp_path / "good.txt.gz"
    with gzip.open(good, "wt", encoding="utf-8") as fh:
        fh.write("一 一 [yi1] /one/\n")
    assert is_readable(good)

    corrupt = tmp_path / "corrupt.txt.gz"
    corrupt.write_bytes(b"this is not a gzip stream")
    assert not is_readable(corrupt)

    truncated = tmp_path / "truncated.txt.gz"
    truncated.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 2])
    assert not is_readable(truncated)

    plain = tmp_path / "plain.csv"
    plain.write_text("character,pinyin\n十,shi\n", encoding="utf-8")
    assert is_readable(plain)
    assert not is_readable(tmp_path / "missing.csv")

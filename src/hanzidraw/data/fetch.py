"""Resumable downloads with progress and digest recording."""

from __future__ import annotations

import gzip
import hashlib
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from pathlib import Path

from .sources import SOURCES, Source

Progress = Callable[[int, int], None]
_UA = {"User-Agent": "hanzidraw/0.1 (+https://github.com/)"}


class FetchError(Exception):
    """A source could not be downloaded."""


def sha256_of_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def is_readable(path: Path, *, chunk: int = 1 << 16) -> bool:
    """Whether a cached download can actually be read back.

    A non-empty file says nothing about whether it decompresses: a truncated
    ``.gz`` cache is the realistic route into a failed build, so it is checked
    before being reused. Only the first block is read -- this runs on every
    ``fetch-data``, against a 30 MB download.
    """
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as fh:  # type: ignore[operator]
            fh.read(chunk)
    except (OSError, zlib.error, EOFError):
        return False
    return True


def download(
    url: str, dest: Path, *, progress: Progress | None = None, chunk: int = 1 << 16
) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0

    headers = dict(_UA)
    if have and url.startswith("http"):
        headers["Range"] = f"bytes={have}-"

    try:
        request = urllib.request.Request(url, headers=headers)  # noqa: S310
        with urllib.request.urlopen(request) as response:  # noqa: S310
            resumed = response.status == 206 if hasattr(response, "status") else False
            if not resumed:
                have = 0
            total = int(response.headers.get("Content-Length") or 0) + have
            mode = "ab" if resumed and have else "wb"
            with part.open(mode) as fh:
                got = have
                while True:
                    block = response.read(chunk)
                    if not block:
                        break
                    fh.write(block)
                    got += len(block)
                    if progress:
                        progress(got, total)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise FetchError(f"could not download {url}: {exc}") from exc

    digest = sha256_of_file(part)
    part.replace(dest)
    return digest


def fetch_all(
    dest_dir: Path,
    *,
    progress: Progress | None = None,
    sources: tuple[Source, ...] = SOURCES,
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for source in sources:
        dest = dest_dir / source.filename
        try:
            digests[source.name] = download(source.url, dest, progress=progress)
        except FetchError as exc:
            if source.required:
                raise FetchError(f"source {source.name}: {exc}") from exc
    return digests

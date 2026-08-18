"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import data_dir, db_path


def _cmd_fetch_data(args: argparse.Namespace) -> int:
    from .data.build import build
    from .data.fetch import FetchError, fetch_all, sha256_of_file
    from .data.parse import DataFormatError
    from .data.sources import SOURCES
    from .data.store import StoreError

    raw = Path(args.raw_dir) if args.raw_dir else data_dir() / "raw"
    db = Path(args.db) if args.db else db_path()

    if db.exists() and not args.rebuild:
        print(f"{db} already exists; pass --rebuild to build it again")
        return 0

    digests: dict[str, str] = {}
    to_fetch = []
    for source in SOURCES:
        dest = raw / source.filename
        if not args.refetch and dest.exists() and dest.stat().st_size > 0:
            digests[source.name] = sha256_of_file(dest)
            print(f"reusing {source.filename} ({dest.stat().st_size / 1e6:.1f} MB)")
        else:
            to_fetch.append(source)

    last = [-1]

    def progress(got: int, total: int) -> None:
        pct = int(got * 100 / total) if total else 0
        if pct != last[0]:
            last[0] = pct
            print(f"\rdownloading… {pct:3d}%", end="", flush=True)

    if to_fetch:
        try:
            digests.update(fetch_all(raw, progress=progress, sources=tuple(to_fetch)))
        except FetchError as exc:
            print(f"\nfetch failed: {exc}", file=sys.stderr)
            return 1
        print("\rdownload complete    ")

    try:
        report = build(raw, db, medians_only=args.medians_only, digests=digests, log=print)
    except (DataFormatError, StoreError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    print(f"database: {db} ({db.stat().st_size / 1e6:.1f} MB)")
    return 0 if report.chars else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hanzidraw", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    fetch = sub.add_parser("fetch-data", help="download the datasets and build the database")
    fetch.add_argument("--rebuild", action="store_true", help="rebuild even if the database exists")
    fetch.add_argument("--medians-only", action="store_true", help="skip outlines (smaller file)")
    fetch.add_argument(
        "--refetch", action="store_true", help="re-download sources even if already present"
    )
    fetch.add_argument("--raw-dir", default=None)
    fetch.add_argument("--db", default=None)
    fetch.set_defaults(func=_cmd_fetch_data)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

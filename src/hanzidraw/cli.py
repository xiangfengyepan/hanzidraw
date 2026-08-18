"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import data_dir, db_path


def _cmd_fetch_data(args: argparse.Namespace) -> int:
    from .data.build import build
    from .data.fetch import FetchError, fetch_all

    raw = Path(args.raw_dir) if args.raw_dir else data_dir() / "raw"
    db = Path(args.db) if args.db else db_path()

    if db.exists() and not args.rebuild:
        print(f"{db} already exists; pass --rebuild to build it again")
        return 0

    last = [-1]

    def progress(got: int, total: int) -> None:
        pct = int(got * 100 / total) if total else 0
        if pct != last[0]:
            last[0] = pct
            print(f"\rdownloading… {pct:3d}%", end="", flush=True)

    try:
        digests = fetch_all(raw, progress=progress)
    except FetchError as exc:
        print(f"\nfetch failed: {exc}", file=sys.stderr)
        return 1
    print("\rdownload complete    ")

    report = build(raw, db, medians_only=args.medians_only, digests=digests, log=print)
    print(f"database: {db} ({db.stat().st_size / 1e6:.1f} MB)")
    return 0 if report.chars else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hanzidraw", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    fetch = sub.add_parser("fetch-data", help="download the datasets and build the database")
    fetch.add_argument("--rebuild", action="store_true", help="rebuild even if the database exists")
    fetch.add_argument("--medians-only", action="store_true", help="skip outlines (smaller file)")
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

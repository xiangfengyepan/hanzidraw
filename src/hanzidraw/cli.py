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


def _cmd_draw(args: argparse.Namespace) -> int:
    from .config import load_config
    from .data.store import Store, StoreError
    from .output.base import Style, draw_glyph, load_glyph
    from .output.image import SvgBackend, save_png

    cfg = load_config(Path(args.config) if args.config else None)
    size = float(args.size if args.size is not None else cfg.get("glyph.size_px"))
    columns = int(args.columns if args.columns is not None else cfg.get("canvas.columns"))
    color = str(args.color if args.color is not None else cfg.get("glyph.color"))

    if size <= 0:
        print(f"--size must be greater than 0, got {size!r}", file=sys.stderr)
        return 1
    if columns < 1:
        print(f"--columns must be at least 1, got {columns!r}", file=sys.stderr)
        return 1
    if not color:
        print(f"--color must not be empty, got {color!r}", file=sys.stderr)
        return 1

    chars = [ch for ch in args.text if not ch.isspace()]
    if not chars:
        print("nothing to draw: no characters given", file=sys.stderr)
        return 1

    advance = size * float(cfg.get("canvas.advance"))

    try:
        store = Store.open(Path(args.db) if args.db else db_path())
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    missing = [ch for ch in chars if not store.has_char(ord(ch))]
    if missing:
        print(f"no stroke data for: {' '.join(missing)}", file=sys.stderr)
        return 1

    rows = (len(chars) + columns - 1) // columns
    width = int(advance * min(len(chars), columns))
    height = int(advance * rows)
    backend = SvgBackend(
        width=width,
        height=height,
        background=str(cfg.get("canvas.background")),
        style=Style(
            color=color,
            width=float(cfg.get("glyph.stroke_width_px")),
        ),
    )
    pad = (advance - size) / 2.0
    for index, ch in enumerate(chars):
        ox = pad + advance * (index % columns)
        oy = pad + advance * (index // columns)
        draw_glyph(backend, load_glyph(store, ord(ch)), ox, oy, size)

    out = Path(args.output)
    try:
        if out.suffix.lower() == ".png":
            save_png(backend, out)
        else:
            backend.save(out)
    except (OSError, RuntimeError) as exc:
        print(f"could not write {out}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out}")
    return 0


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

    draw = sub.add_parser("draw", help="render text to an SVG or PNG file without the GUI")
    draw.add_argument("text", help="the characters to draw, e.g. 沣潘叶祥")
    draw.add_argument("-o", "--output", required=True, help="out.svg or out.png")
    draw.add_argument("--size", type=float, default=None)
    draw.add_argument("--color", default=None)
    draw.add_argument("--columns", type=int, default=None)
    draw.add_argument("--config", default=None)
    draw.add_argument("--db", default=None)
    draw.set_defaults(func=_cmd_draw)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

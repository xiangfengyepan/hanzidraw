"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import data_dir, db_path


def _cmd_fetch_data(args: argparse.Namespace) -> int:
    import zlib

    from .data.build import build, failing_source
    from .data.fetch import FetchError, fetch_all, is_readable, sha256_of_file
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
        cached = not args.refetch and dest.exists() and dest.stat().st_size > 0
        if cached and not is_readable(dest):
            # st_size > 0 says nothing about whether the file decompresses, and a
            # truncated cache is the live route into a failed build.
            print(f"{source.filename} is corrupt or truncated; re-downloading")
            cached = False
        if cached:
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
    except (OSError, zlib.error, UnicodeDecodeError, EOFError) as exc:
        # A corrupt or truncated cached download is the realistic trigger here
        # (gzip.BadGzipFile is an OSError; a gzip stream cut off mid-data raises
        # the plain builtin EOFError instead, which is not an OSError); build()
        # tags the offending file onto the exception so this message can point
        # at the right download.
        # The existing database, if any, is untouched -- build() swaps in a
        # temp file only on success.
        name = failing_source(exc) or raw
        print(
            f"build failed: could not read {name} ({exc}); the download may be "
            f"corrupt or truncated -- re-run with "
            f"'hanzidraw fetch-data --rebuild --refetch'",
            file=sys.stderr,
        )
        return 1
    print(f"database: {db} ({db.stat().st_size / 1e6:.1f} MB)")
    return 0 if report.chars else 1


def _cmd_draw(args: argparse.Namespace) -> int:
    from .config import load_config
    from .data.glyphs import load_glyph
    from .data.store import Store, StoreError
    from .output.base import Style, draw_glyph
    from .output.image import SvgBackend, save_png
    from .render.sheet import Sheet

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

    out = Path(args.output)
    suffix = out.suffix.lower()
    if suffix not in (".svg", ".png"):
        # Writing SVG under a .txt name was the old behaviour: the suffix is
        # what chooses the format, so an unknown one has no answer.
        print(
            f"-o must end in .svg or .png, got {args.output!r}",
            file=sys.stderr,
        )
        return 1

    try:
        store = Store.open(Path(args.db) if args.db else db_path())
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    missing = [ch for ch in chars if not store.has_char(ord(ch))]
    if missing:
        print(f"no stroke data for: {' '.join(missing)}", file=sys.stderr)
        return 1

    # One source of cell origins: the Sheet the GUI uses. `draw` used to carry a
    # character-for-character copy of the same formula, which agreed with the
    # sheet only by textual coincidence -- and disagreed outright on
    # canvas.wrap, which it never read at all.
    sheet = Sheet(
        columns=columns,
        advance=float(cfg.get("canvas.advance")),
        size=size,
        wrap=bool(cfg.get("canvas.wrap")),
    )
    glyphs = [load_glyph(store, ord(ch)) for ch in chars]
    placements = [sheet.add(glyph, ch) for glyph, ch in zip(glyphs, chars, strict=True)]

    # Crop to the cells actually used rather than to a whole blank sheet: this is
    # a one-shot render, not a practice page. Derived from the placements, so
    # there is still no second origin formula to drift.
    pad = (sheet.pitch - size) / 2.0
    width = int(max(p.ox + p.size for p in placements) + pad)
    height = int(max(p.oy + p.size for p in placements) + pad)
    backend = SvgBackend(
        width=width,
        height=height,
        background=str(cfg.get("canvas.background")),
        style=Style(
            color=color,
            width=float(cfg.get("glyph.stroke_width_px")),
        ),
    )
    outline_style = str(cfg.get("glyph.style")) == "outline"
    # Spec §6: stroke-order numbers belong to `single` mode -- a whole sheet of
    # numbered practice cells is unreadable.
    numbers = bool(cfg.get("glyph.stroke_numbers")) and str(cfg.get("canvas.mode")) == "single"
    for placed in placements:
        codepoint = ord(placed.text)
        ox, oy = placed.ox, placed.oy
        outline = store.outline(codepoint) if outline_style else None
        if outline:
            backend.begin_glyph(ox, oy, size)
            backend.outline(outline, ox, oy, size)
            backend.end_glyph()
        else:
            # No outline for this character (mixed database), or the whole
            # database was built --medians-only: draw it rather than skip
            # it, so a mixed database still renders everything.
            draw_glyph(backend, placed.glyph, ox, oy, placed.size)
        if numbers:
            backend.stroke_numbers(placed.glyph, ox, oy, placed.size)

    if outline_style and store.get_meta("build_medians_only") == "1":
        print(
            "glyph.style = outline needs outlines, but this database is medians-only; "
            "drew brush strokes instead. Rebuild with 'hanzidraw fetch-data --rebuild' "
            "(without --medians-only) for the real contour."
        )

    try:
        if suffix == ".png":
            save_png(backend, out)
        else:
            backend.save(out)
    except (OSError, RuntimeError) as exc:
        print(f"could not write {out}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out}")
    return 0


def _cmd_export_firmware(args: argparse.Namespace) -> int:
    from .data.store import Store, StoreError
    from .firmware.emit_c import emit_c, emit_h
    from .firmware.subset import select

    try:
        store = Store.open(Path(args.db) if args.db else db_path())
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    budget = int(args.budget_kb * 1024) if args.budget_kb else None
    entries = select(
        store,
        must=args.must or "",
        budget_bytes=budget,
        per_initial=args.per_initial,
        limit=args.limit,
        log=print,  # so an over-budget required set explains the negative headroom
    )
    if not entries:
        print("nothing selected; check --must and --budget-kb", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(emit_c(entries), encoding="utf-8")
    if args.header:
        Path(args.header).write_text(emit_h(entries), encoding="utf-8")

    total = sum(e.cost_bytes for e in entries)
    print(f"{len(entries)} characters, {total / 1024:.1f} KB")
    if budget:
        print(f"budget {budget / 1024:.1f} KB, headroom {(budget - total) / 1024:.1f} KB")
    print(f"wrote {out}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        from .ui.app import run
    except ImportError:
        print("the GUI needs PySide6: pip install 'hanzidraw[gui]'", file=sys.stderr)
        return 1
    return run(
        config=Path(args.config) if args.config else None,
        db=Path(args.db) if args.db else None,
    )


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

    exp = sub.add_parser("export-firmware", help="emit hanzi_data.c for the Keychron firmware")
    exp.add_argument("-o", "--output", required=True)
    exp.add_argument("--header", default=None, help="also write hanzi_data.h here")
    exp.add_argument("--must", default="", help="characters to include first, e.g. 沣潘叶祥")
    exp.add_argument("--budget-kb", type=float, default=None)
    exp.add_argument("--per-initial", type=int, default=None)
    exp.add_argument("--limit", type=int, default=None)
    exp.add_argument("--db", default=None)
    exp.set_defaults(func=_cmd_export_firmware)

    gui = sub.add_parser("run", help="open the drawing window (default)")
    gui.add_argument("--config", default=None)
    gui.add_argument("--db", default=None)
    gui.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args([*(argv or []), "run"])
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

"""Turn the raw downloads into one queryable SQLite file."""

from __future__ import annotations

import gzip
import os
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from .parse import (
    parse_cedict_char_reading,
    parse_cedict_line,
    parse_essay,
    parse_graphics_line,
    parse_hanzidb,
)
from .store import Store, StoreError

Log = Callable[[str], None]


@dataclass
class BuildReport:
    chars: int = 0
    readings: int = 0
    phrases: int = 0
    chars_without_geometry: int = 0
    phrases_dropped: int = 0
    duplicate_chars: int = 0
    duplicate_phrases: int = 0
    unknown_syllables: tuple[str, ...] = field(default_factory=tuple)
    outlines: bool = True
    extra_readings: int = 0

    def summary(self) -> str:
        lines = [
            f"{self.chars} characters with stroke data ({self.readings} readings, "
            f"{self.extra_readings} of them heteronym readings from CC-CEDICT)",
            f"{self.duplicate_chars} duplicate character rows in the source, skipped",
            f"{self.phrases} phrases, {self.phrases_dropped} dropped (undrawable characters)",
            f"{self.duplicate_phrases} duplicate phrase rows in the source, skipped",
            f"{self.chars_without_geometry} characters skipped for having no stroke data",
            f"outlines: {'included' if self.outlines else 'omitted (--medians-only)'}",
        ]
        if self.unknown_syllables:
            lines.append(
                "readings not in the syllable inventory (add them to syllables.py): "
                + ", ".join(self.unknown_syllables)
            )
        return "\n".join(lines)


_SOURCE_ATTR = "hanzidraw_source"


def failing_source(exc: BaseException) -> str | None:
    """Which source file a read failure came from, if the build tagged one on."""
    return getattr(exc, _SOURCE_ATTR, None) or getattr(exc, "filename", None)


@contextmanager
def _naming(path: Path) -> Iterator[None]:
    """Tag a read failure with the offending file and re-raise it unchanged.

    ``gzip.BadGzipFile`` and ``zlib.error`` carry no path of their own, and the
    CLI's message has to tell the user which download to re-fetch. The tag goes
    on an attribute of our own rather than ``OSError.filename``, because setting
    that switches ``str(exc)`` to the "[Errno None] None: path" form and throws
    away the one part that explains what went wrong.
    """
    try:
        yield
    except (OSError, zlib.error, UnicodeDecodeError) as exc:
        if getattr(exc, _SOURCE_ATTR, None) is None:
            setattr(exc, _SOURCE_ATTR, str(path))
        raise


def _report_changed_sources(db: Path, digests: dict[str, str], say: Log) -> None:
    """Record on the first build, compare on a rebuild, name what moved.

    Spec §4 (amended): pinning expected hashes is not viable for sources served
    from a moving ``master`` branch -- they change legitimately and a pinned hash
    would fail every honest rebuild. So the digests recorded in ``meta`` are
    compared against the ones just fetched and each changed source is named,
    with both short digests. Provenance and change detection, not authentication.
    """
    if not digests or not db.exists():
        return
    try:
        previous = Store.open(db)
    except StoreError:
        return  # nothing trustworthy to compare against
    try:
        for name in sorted(digests):
            was = previous.get_meta(f"source_{name}_sha256")
            now = digests[name]
            if was and was != now:
                say(f"source {name} changed since the last build: {was[:12]} -> {now[:12]}")
    finally:
        previous.close()


def _read_text(path: Path) -> str:
    with _naming(path):
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        return path.read_text(encoding="utf-8", errors="replace")


def build(
    raw_dir: Path,
    db: Path,
    *,
    medians_only: bool = False,
    digests: dict[str, str] | None = None,
    log: Log | None = None,
) -> BuildReport:
    """Build the database at ``db``, atomically.

    The file being replaced may be the owner's only copy and takes twenty
    minutes to produce, so the build never touches it: everything is written to
    a sibling temp file and swapped in with ``os.replace`` once ``finish()``
    has succeeded. Any failure removes the temp file and leaves the existing
    database exactly as it was.
    """
    say = log or (lambda _msg: None)
    report = BuildReport(outlines=not medians_only)

    _report_changed_sources(db, digests or {}, say)

    say("reading stroke data")
    geometry = {}
    graphics = raw_dir / "graphics.txt"
    with _naming(graphics), graphics.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            record = parse_graphics_line(line)
            if record:
                geometry[record.char] = record

    say("reading character metadata")
    unknown: set[str] = set()
    rows = parse_hanzidb(_read_text(raw_dir / "hanziDB.csv"), unknown=unknown)

    tmp = db.with_suffix(".sqlite.tmp")
    tmp.unlink(missing_ok=True)  # a stale temp file from an earlier failed build
    store = Store.create(tmp)
    try:
        ranks: dict[str, int] = {}
        seen: set[int] = set()
        seen_readings: set[tuple[str, int]] = set()

        for row in rows:
            codepoint = ord(row.char)
            if codepoint in seen:
                report.duplicate_chars += 1
                continue
            seen.add(codepoint)
            record = geometry.get(row.char)
            if record is None:
                report.chars_without_geometry += 1
                continue
            store.add_char(
                codepoint,
                freq_rank=row.freq_rank,
                nstroke=len(record.medians),
                medians=record.medians,
                outline=None if medians_only else record.outline,
            )
            ranks[row.char] = row.freq_rank
            report.chars += 1
            for reading in row.readings:
                store.add_reading(reading, codepoint, is_primary=True)
                report.readings += 1
                seen_readings.add((reading, codepoint))

        say("reading word frequencies")
        weights: dict[str, float] = {}
        essay = raw_dir / "essay.txt"
        if essay.exists():
            weights = dict(parse_essay(_read_text(essay)))

        say("reading the phrase dictionary")
        cedict_lines = _read_text(raw_dir / "cedict.txt.gz").splitlines()
        seen_phrases: set[tuple[str, str]] = set()
        for line in cedict_lines:
            entry = parse_cedict_line(line)
            if entry is None:
                continue
            if not all(ch in ranks for ch in entry.text):
                report.phrases_dropped += 1
                continue
            key = (entry.pinyin_key, entry.text)
            if key in seen_phrases:
                report.duplicate_phrases += 1
                continue
            seen_phrases.add(key)
            weight = weights.get(entry.text)
            if weight is None:
                weight = 1000.0 / (1.0 + mean(ranks[ch] for ch in entry.text))
            store.add_phrase(entry.pinyin_key, entry.text, float(weight))
            report.phrases += 1

        say("harvesting heteronym readings from CC-CEDICT")
        for line in cedict_lines:
            got = parse_cedict_char_reading(line)
            if got is None:
                continue
            char, reading = got
            if char not in ranks:
                continue  # rule 1: only for a character already stored in `char`
            codepoint = ord(char)
            pair = (reading, codepoint)
            if pair in seen_readings:
                continue  # rule 2: never duplicate a (pinyin, codepoint) pair
            seen_readings.add(pair)
            store.add_reading(reading, codepoint, is_primary=False)
            report.readings += 1
            report.extra_readings += 1

        for name, digest in (digests or {}).items():
            store.set_meta(f"source_{name}_sha256", digest)
        store.set_meta("build_medians_only", "1" if medians_only else "0")
        # The field you want when diagnosing "why does my database differ from
        # yours" (spec §4).
        store.set_meta("build_date", datetime.now(UTC).isoformat(timespec="seconds"))
        # finish() is what stamps schema_version, so nothing before this point
        # can pass for a complete database.
        store.finish()
    except BaseException:
        store.close()
        tmp.unlink(missing_ok=True)
        raise
    store.close()
    os.replace(tmp, db)

    report.unknown_syllables = tuple(sorted(unknown))
    say(report.summary())
    return report

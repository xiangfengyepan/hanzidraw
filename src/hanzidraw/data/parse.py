"""Parsers for the four upstream sources.

Every parser is pure: text in, records out, no I/O and no network. Coordinate
conversion to centred em units with Y pointing down happens here and nowhere
else (see ``to_em``).
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

from ..ime.syllables import is_syllable, split_readings

EM_CENTER_X = 512
EM_CENTER_Y = 388

_HANZI = re.compile(r"^[㐀-䶿一-鿿豈-﫿]+$")
_CEDICT = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]*)\]\s+/")


class DataFormatError(Exception):
    """An upstream file did not look the way the build expects."""


def to_em(mx: int, my: int) -> tuple[int, int]:
    """Make Me a Hanzi coordinates (1024 em box, Y up) -> centred em units, Y down."""
    return (mx - EM_CENTER_X, EM_CENTER_Y - my)


@dataclass(frozen=True)
class GlyphRecord:
    char: str
    medians: tuple[tuple[tuple[int, int], ...], ...]
    outline: tuple[str, ...]


def parse_graphics_line(line: str) -> GlyphRecord | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    try:
        if not isinstance(obj, dict):
            return None
        char = obj.get("character")
        medians = obj.get("medians") or []
        if not char or not medians:
            return None
        strokes: list[tuple[tuple[int, int], ...]] = []
        for stroke in medians:
            points = []
            for p in stroke:
                if len(p) < 2:
                    return None
                x = int(p[0])
                y = int(p[1])
                points.append(to_em(x, y))
            if not points:
                return None
            strokes.append(tuple(points))
        if not strokes:
            return None
        return GlyphRecord(
            char=char, medians=tuple(strokes), outline=tuple(obj.get("strokes") or ())
        )
    except (AttributeError, TypeError, ValueError, KeyError, IndexError):
        return None


@dataclass(frozen=True)
class HanziDbRow:
    char: str
    readings: tuple[str, ...]
    freq_rank: int
    nstroke: int


# Upstream hanziDB misspells this column as "charcter"; accept either, so the
# parser keeps working if they ever fix it.
_CHAR_COLUMNS = ("character", "charcter")
_REQUIRED_HANZIDB = ("pinyin", "stroke_count", "frequency_rank")


def parse_hanzidb(text: str, *, unknown: set[str] | None = None) -> list[HanziDbRow]:
    reader = csv.DictReader(io.StringIO(text))
    found = tuple(reader.fieldnames or ())
    char_col = next((c for c in _CHAR_COLUMNS if c in found), None)
    missing = [c for c in _REQUIRED_HANZIDB if c not in found]
    if char_col is None:
        missing.insert(0, "character (or charcter)")
    if missing:
        raise DataFormatError(
            f"hanziDB is missing column(s) {', '.join(missing)}; columns found: {', '.join(found)}"
        )
    rows: list[HanziDbRow] = []
    for raw in reader:
        char = (raw.get(char_col) or "").strip()
        if len(char) != 1 or not _HANZI.match(char):
            continue
        normalised = split_readings(raw["pinyin"])
        if unknown is not None:
            unknown.update(r for r in normalised if not is_syllable(r))
        readings = tuple(dict.fromkeys(r for r in normalised if is_syllable(r)))
        if not readings:
            continue
        try:
            rank = int(raw["frequency_rank"])
            nstroke = int(raw["stroke_count"])
        except (TypeError, ValueError):
            continue
        rows.append(HanziDbRow(char=char, readings=readings, freq_rank=rank, nstroke=nstroke))
    return rows


@dataclass(frozen=True)
class CedictEntry:
    text: str
    pinyin_key: str


def parse_cedict_line(line: str) -> CedictEntry | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = _CEDICT.match(line)
    if not m:
        return None
    simplified, pinyin = m.group(2), m.group(3)
    if not _HANZI.match(simplified) or len(simplified) < 2:
        return None
    syllables = split_readings(pinyin)
    if not syllables or len(syllables) != len(simplified):
        return None
    if not all(is_syllable(s) for s in syllables):
        return None
    return CedictEntry(text=simplified, pinyin_key=" ".join(syllables))


def parse_cedict_char_reading(line: str) -> tuple[str, str] | None:
    """Harvest one (character, reading) pair from a CC-CEDICT single-character entry.

    Reuses the same regex and normalisation as ``parse_cedict_line``; differs only in
    requiring exactly one character and exactly one syllable, since a CEDICT entry has
    one line per reading rather than one line per character.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = _CEDICT.match(line)
    if not m:
        return None
    simplified, pinyin = m.group(2), m.group(3)
    if not _HANZI.match(simplified) or len(simplified) != 1:
        return None
    syllables = split_readings(pinyin)
    if len(syllables) != 1 or not is_syllable(syllables[0]):
        return None
    return simplified, syllables[0]


def parse_essay(text: str) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        word = parts[0].strip()
        try:
            weight = float(parts[1].strip())
        except ValueError:
            continue
        if word:
            pairs.append((word, weight))
    return pairs

"""The only module that knows the data lives in SQLite.

Swapping the storage format should touch this file and nothing else.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS char (
    codepoint INTEGER PRIMARY KEY,
    freq_rank INTEGER NOT NULL,
    nstroke   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reading (
    pinyin    TEXT NOT NULL,
    codepoint INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS phrase (
    pinyin_key TEXT NOT NULL,
    text       TEXT NOT NULL,
    weight     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS geom (
    codepoint INTEGER PRIMARY KEY,
    medians   BLOB NOT NULL,
    outline   BLOB
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_reading_pinyin ON reading (pinyin);
CREATE INDEX IF NOT EXISTS idx_phrase_key ON phrase (pinyin_key);
CREATE INDEX IF NOT EXISTS idx_char_rank ON char (freq_rank);
"""

MAX_POINTS_PER_STROKE = 255


class StoreError(Exception):
    """The database is missing, unreadable, or built by a different version."""


def encode_medians(strokes) -> bytes:
    if len(strokes) > 255:
        raise ValueError(f"too many strokes: {len(strokes)}")
    out = bytearray(struct.pack("<B", len(strokes)))
    for stroke in strokes:
        if len(stroke) > MAX_POINTS_PER_STROKE:
            raise ValueError(f"stroke has {len(stroke)} points, max is {MAX_POINTS_PER_STROKE}")
        out += struct.pack("<B", len(stroke))
        for x, y in stroke:
            out += struct.pack("<hh", int(x), int(y))
    return zlib.compress(bytes(out), 6)


def decode_medians(blob: bytes) -> tuple[tuple[tuple[int, int], ...], ...]:
    raw = zlib.decompress(blob)
    (nstroke,) = struct.unpack_from("<B", raw, 0)
    off = 1
    strokes: list[tuple[tuple[int, int], ...]] = []
    for _ in range(nstroke):
        (npoints,) = struct.unpack_from("<B", raw, off)
        off += 1
        points: list[tuple[int, int]] = []
        for _ in range(npoints):
            x, y = struct.unpack_from("<hh", raw, off)
            off += 4
            points.append((x, y))
        strokes.append(tuple(points))
    return tuple(strokes)


class Store:
    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self.path = path

    # ---- lifecycle ----

    @classmethod
    def create(cls, path: Path) -> Store:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA)
        store = cls(conn, path)
        store.set_meta("schema_version", str(SCHEMA_VERSION))
        return store

    @classmethod
    def open(cls, path: Path) -> Store:
        if not path.exists():
            raise StoreError(f"no character database at {path}; run 'hanzidraw fetch-data' first")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        store = cls(conn, path)
        try:
            version = store.get_meta("schema_version")
        except sqlite3.DatabaseError as exc:
            raise StoreError(f"{path} is not a hanzidraw database ({exc})") from exc
        if version != str(SCHEMA_VERSION):
            raise StoreError(
                f"{path} has schema version {version}, this build needs "
                f"{SCHEMA_VERSION}; run 'hanzidraw fetch-data --rebuild'"
            )
        return store

    def finish(self) -> None:
        self._conn.executescript(_INDEXES)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- writes ----

    def add_char(self, codepoint: int, freq_rank: int, nstroke: int, medians, outline) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO char (codepoint, freq_rank, nstroke) VALUES (?, ?, ?)",
            (codepoint, freq_rank, nstroke),
        )
        blob = None
        if outline:
            blob = zlib.compress(json.dumps(list(outline), ensure_ascii=False).encode("utf-8"), 6)
        self._conn.execute(
            "INSERT OR REPLACE INTO geom (codepoint, medians, outline) VALUES (?, ?, ?)",
            (codepoint, encode_medians(medians), blob),
        )

    def add_reading(self, pinyin: str, codepoint: int) -> None:
        self._conn.execute(
            "INSERT INTO reading (pinyin, codepoint) VALUES (?, ?)", (pinyin, codepoint)
        )

    def add_phrase(self, pinyin_key: str, text: str, weight: float) -> None:
        self._conn.execute(
            "INSERT INTO phrase (pinyin_key, text, weight) VALUES (?, ?, ?)",
            (pinyin_key, text, weight),
        )

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value))
        )
        self._conn.commit()

    # ---- reads ----

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def has_char(self, codepoint: int) -> bool:
        row = self._conn.execute("SELECT 1 FROM geom WHERE codepoint = ?", (codepoint,)).fetchone()
        return row is not None

    def chars_for_reading(self, pinyin: str, limit: int) -> list[tuple[int, str, int]]:
        rows = self._conn.execute(
            "SELECT r.codepoint, r.pinyin, c.freq_rank FROM reading r "
            "JOIN char c ON c.codepoint = r.codepoint WHERE r.pinyin = ? "
            "ORDER BY c.freq_rank LIMIT ?",
            (pinyin, limit),
        ).fetchall()
        return [(int(a), str(b), int(c)) for a, b, c in rows]

    def chars_for_prefix(self, prefix: str, limit: int) -> list[tuple[int, str, int]]:
        rows = self._conn.execute(
            "SELECT r.codepoint, r.pinyin, c.freq_rank FROM reading r "
            "JOIN char c ON c.codepoint = r.codepoint "
            "WHERE r.pinyin >= ? AND r.pinyin < ? ORDER BY c.freq_rank LIMIT ?",
            (prefix, prefix + "￿", limit),
        ).fetchall()
        return [(int(a), str(b), int(c)) for a, b, c in rows]

    def phrases_for_key(self, key: str, limit: int) -> list[tuple[str, float]]:
        rows = self._conn.execute(
            "SELECT text, weight FROM phrase WHERE pinyin_key = ? "
            "ORDER BY weight DESC, length(text), text LIMIT ?",
            (key, limit),
        ).fetchall()
        return [(str(t), float(w)) for t, w in rows]

    def phrases_for_syllable_prefix(self, prefix: str, limit: int) -> list[tuple[str, float]]:
        """Keys that continue at a syllable boundary. Excludes the exact key itself."""
        lo = prefix + " "
        rows = self._conn.execute(
            "SELECT text, MAX(weight) AS w FROM phrase WHERE pinyin_key >= ? "
            "AND pinyin_key < ? GROUP BY text ORDER BY w DESC, length(text), text LIMIT ?",
            (lo, lo + "￿", limit),
        ).fetchall()
        return [(str(t), float(w)) for t, w in rows]

    def phrases_for_partial(self, prefix: str, limit: int) -> list[tuple[str, float]]:
        """Plain prefix range, for when the last syllable typed is incomplete."""
        rows = self._conn.execute(
            "SELECT text, MAX(weight) AS w FROM phrase WHERE pinyin_key >= ? "
            "AND pinyin_key < ? GROUP BY text ORDER BY w DESC, length(text), text LIMIT ?",
            (prefix, prefix + "￿", limit),
        ).fetchall()
        return [(str(t), float(w)) for t, w in rows]

    def medians(self, codepoint: int) -> tuple[tuple[tuple[int, int], ...], ...]:
        row = self._conn.execute(
            "SELECT medians FROM geom WHERE codepoint = ?", (codepoint,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no stroke data for U+{codepoint:04X}")
        return decode_medians(row[0])

    def outline(self, codepoint: int) -> tuple[str, ...] | None:
        row = self._conn.execute(
            "SELECT outline FROM geom WHERE codepoint = ?", (codepoint,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return tuple(json.loads(zlib.decompress(row[0]).decode("utf-8")))

    def char_meta(self, codepoint: int) -> tuple[int, int]:
        row = self._conn.execute(
            "SELECT freq_rank, nstroke FROM char WHERE codepoint = ?", (codepoint,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no metadata for U+{codepoint:04X}")
        return (int(row[0]), int(row[1]))

    def first_reading(self, codepoint: int) -> str | None:
        row = self._conn.execute(
            "SELECT pinyin FROM reading WHERE codepoint = ? ORDER BY pinyin LIMIT 1", (codepoint,)
        ).fetchone()
        return str(row[0]) if row else None

    def all_chars_by_rank(self) -> Iterator[tuple[int, str, int]]:
        cur = self._conn.execute(
            "SELECT c.codepoint, (SELECT r.pinyin FROM reading r "
            "WHERE r.codepoint = c.codepoint ORDER BY r.pinyin LIMIT 1), "
            "c.freq_rank FROM char c JOIN geom g ON g.codepoint = c.codepoint "
            "ORDER BY c.freq_rank"
        )
        for a, b, c in cur:
            yield (int(a), str(b or ""), int(c))

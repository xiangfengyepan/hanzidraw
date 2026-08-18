"""Where the data comes from, and who to credit for it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    filename: str
    required: bool
    # An identifier to credit the source by, not licence terms: the full text
    # lives in NOTICE, which is what the name used to promise and never held.
    attribution: str


SOURCES: tuple[Source, ...] = (
    Source(
        name="graphics",
        url="https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt",
        filename="graphics.txt",
        required=True,
        attribution="Arphic Public License / LGPL (Make Me a Hanzi)",
    ),
    Source(
        name="hanzidb",
        url="https://raw.githubusercontent.com/ruddfawcett/hanziDB.csv/master/data/hanziDB.csv",
        filename="hanziDB.csv",
        required=True,
        attribution="hanziDB.csv",
    ),
    Source(
        name="cedict",
        url="https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
        filename="cedict.txt.gz",
        required=True,
        attribution="CC BY-SA 4.0 (CC-CEDICT)",
    ),
    Source(
        name="essay",
        url="https://raw.githubusercontent.com/rime/rime-essay/master/essay.txt",
        filename="essay.txt",
        required=False,
        attribution="rime-essay",
    ),
)

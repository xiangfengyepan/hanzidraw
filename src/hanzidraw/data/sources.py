"""Where the data comes from, and under what licence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    filename: str
    required: bool
    licence: str


SOURCES: tuple[Source, ...] = (
    Source(
        name="graphics",
        url="https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt",
        filename="graphics.txt",
        required=True,
        licence="Arphic Public License / LGPL (Make Me a Hanzi)",
    ),
    Source(
        name="hanzidb",
        url="https://raw.githubusercontent.com/ruddfawcett/hanziDB.csv/master/data/hanziDB.csv",
        filename="hanziDB.csv",
        required=True,
        licence="hanziDB.csv",
    ),
    Source(
        name="cedict",
        url="https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
        filename="cedict.txt.gz",
        required=True,
        licence="CC BY-SA 4.0 (CC-CEDICT)",
    ),
    Source(
        name="essay",
        url="https://raw.githubusercontent.com/rime/rime-essay/master/essay.txt",
        filename="essay.txt",
        required=False,
        licence="rime-essay",
    ),
)

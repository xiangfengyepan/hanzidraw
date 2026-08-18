"""A minimal SVG path parser — only what Make Me a Hanzi outlines contain.

Deliberately not a general SVG implementation: an unsupported command raises so
a data change is visible instead of silently drawing a wrong glyph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OUTLINE_EM = 1024.0
OUTLINE_TOP = 900.0

# The command alternative matches *any* letter, not just the supported set:
# an unsupported command (e.g. an arc "A") must still be captured as a token
# so the validation loop below can reject it by name. Narrowing this back to
# [MmLlHhVvQqCcZz] would make an unrecognised letter match neither
# alternative, and an unmatched character is now an error rather than being
# skipped -- but it would be the *wrong* error, reported at a stray letter
# instead of naming the command.
_TOKEN = re.compile(r"([A-Za-z])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")
# Whitespace and commas are the only separators this data uses; everything else
# either matches a token or is a mistake. Scanning position by position instead
# of using finditer is what makes an unmatched character visible: a stray "+"
# before a coordinate, or the leftover "." of a malformed "5.", used to be
# silently dropped, and its neighbours then shifted into the wrong arguments.
_SEPARATOR = re.compile(r"[\s,]+")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6, "Z": 0}


@dataclass(frozen=True)
class Seg:
    kind: str
    points: tuple[tuple[float, float], ...]


def parse_path(d: str) -> tuple[Seg, ...]:
    tokens: list[str | float] = []
    text = d or ""
    pos = 0
    while pos < len(text):
        separator = _SEPARATOR.match(text, pos)
        if separator:
            pos = separator.end()
            continue
        match = _TOKEN.match(text, pos)
        if match is None:
            raise ValueError(f"unexpected character {text[pos]!r} in path data at offset {pos}")
        command, number = match.groups()
        tokens.append(command if command else float(number))
        pos = match.end()

    for token in tokens:
        if isinstance(token, str) and token.upper() not in _ARGS:
            raise ValueError(f"unsupported path command {token!r}")
    if not tokens:
        return ()

    segs: list[Seg] = []
    cx = cy = 0.0
    index = 0
    command = ""
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command = token
            index += 1
            if command.upper() == "Z":
                segs.append(Seg("Z", ()))
                continue
        if not command:
            raise ValueError("path data started with a coordinate")
        upper = command.upper()
        relative = command.islower()
        count = _ARGS[upper]
        if count == 0:
            # Only Z has zero arguments, and its own token is consumed and
            # handled (with a `continue`) above -- reaching here means the
            # current token is a stray number left over after a Z, which
            # `index += count` would never advance past, spinning forever.
            raise ValueError(f"command {command} takes no arguments; found extra data")
        args = [float(v) for v in tokens[index : index + count]]  # type: ignore[arg-type]
        if len(args) < count:
            raise ValueError(f"command {command} is missing arguments")
        index += count

        if upper in ("M", "L"):
            x, y = args
            if relative:
                x, y = cx + x, cy + y
            segs.append(Seg(upper, ((x, y),)))
            cx, cy = x, y
            if upper == "M":
                command = "l" if relative else "L"  # implicit lineto for extra pairs
        elif upper == "H":
            x = cx + args[0] if relative else args[0]
            segs.append(Seg("L", ((x, cy),)))
            cx = x
        elif upper == "V":
            y = cy + args[0] if relative else args[0]
            segs.append(Seg("L", ((cx, y),)))
            cy = y
        elif upper == "Q":
            x1, y1, x, y = args
            if relative:
                x1, y1, x, y = cx + x1, cy + y1, cx + x, cy + y
            segs.append(Seg("Q", ((x1, y1), (x, y))))
            cx, cy = x, y
        elif upper == "C":
            x1, y1, x2, y2, x, y = args
            if relative:
                x1, y1 = cx + x1, cy + y1
                x2, y2 = cx + x2, cy + y2
                x, y = cx + x, cy + y
            segs.append(Seg("C", ((x1, y1), (x2, y2), (x, y))))
            cx, cy = x, y
    return tuple(segs)


def outline_to_box(seg: Seg, ox: float, oy: float, size: float) -> Seg:
    scale = size / OUTLINE_EM
    return Seg(
        seg.kind,
        tuple((ox + mx * scale, oy + (OUTLINE_TOP - my) * scale) for mx, my in seg.points),
    )


def svg_transform(ox: float, oy: float, size: float) -> str:
    scale = size / OUTLINE_EM
    return f"translate({ox:g},{oy:g}) scale({scale:g},{-scale:g}) translate(0,{-OUTLINE_TOP:g})"

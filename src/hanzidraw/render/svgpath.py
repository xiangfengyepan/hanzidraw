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
# alternative, so finditer would silently skip it like a comma -- its numeric
# arguments would then be absorbed into the preceding command instead of
# raising, which is exactly the silent-misparse this module exists to avoid.
_TOKEN = re.compile(r"([A-Za-z])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6, "Z": 0}


@dataclass(frozen=True)
class Seg:
    kind: str
    points: tuple[tuple[float, float], ...]


def parse_path(d: str) -> tuple[Seg, ...]:
    tokens: list[str | float] = []
    for match in _TOKEN.finditer(d or ""):
        command, number = match.groups()
        tokens.append(command if command else float(number))

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

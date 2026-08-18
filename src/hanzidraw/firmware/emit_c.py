"""Emit hanzi_data.c / hanzi_data.h in exactly the firmware's existing format."""

from __future__ import annotations

from collections.abc import Sequence

from .subset import Entry


def _array(values: Sequence[int]) -> str:
    return "{" + ",".join(str(v) for v in values) + "}"


def emit_c(entries: Sequence[Entry]) -> str:
    lines = ['#include "include/hanzi_data.h"', ""]
    for index, entry in enumerate(entries):
        char = chr(entry.codepoint)
        lines.append(f"// {index}: {char} ({entry.pinyin})")
        lines.append(f"static const int16_t x{index}[]={_array(entry.xs)};")
        lines.append(f"static const int16_t y{index}[]={_array(entry.ys)};")
        lines.append(f"static const uint8_t l{index}[]={_array(entry.lens)};")
    lines.append("const hanzi_t hanzi_table[]={")
    for index, entry in enumerate(entries):
        lines.append(
            f"  {{ x{index},y{index},l{index}, {len(entry.lens)}, "
            f'"{entry.pinyin}" }}, // {chr(entry.codepoint)}'
        )
    lines.append("};")
    lines.append(f"const uint16_t hanzi_count = {len(entries)};")
    return "\n".join(lines) + "\n"


def emit_h(entries: Sequence[Entry]) -> str:
    max_strokes = max((len(e.lens) for e in entries), default=0)
    return (
        "#pragma once\n"
        "#include <stdint.h>\n\n"
        "typedef struct {\n"
        "    const int16_t *x;\n"
        "    const int16_t *y;\n"
        "    const uint8_t *len;\n"
        "    uint8_t  nstroke;\n"
        "    const char *py;\n"
        "} hanzi_t;\n\n"
        f"#define HANZI_MAX_STROKES {max_strokes}\n"
        "extern const hanzi_t hanzi_table[];\n"
        "extern const uint16_t hanzi_count;\n"
    )

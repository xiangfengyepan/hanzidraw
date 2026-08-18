"""Defaults, TOML loading/validation, and platform paths.

Validation never raises: a bad value is replaced by its default and recorded in
``Config.errors`` so the UI can show it in the status bar.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP = "hanzidraw"

DEFAULTS: dict[str, Any] = {
    "glyph": {
        "style": "brush",
        "size_px": 240,
        "stroke_width_px": 14,
        "color": "#111111",
        "outline_color": "#cccccc",
        "show_pending_outline": True,
        "stroke_numbers": False,
        "animation": {
            "enabled": True,
            "stroke_ms": 380,
            "gap_ms": 90,
            "easing": "ease_out",
        },
    },
    "canvas": {
        "mode": "sheet",
        "background": "#fdfdf7",
        "grid": "tian",
        "grid_color": "#e5ded0",
        "columns": 6,
        "advance": 1.15,
        "wrap": True,
        "always_on_top": False,
    },
    "ime": {"page_size": 9, "phrases": True, "learn": True, "max_candidates": 200},
    "output": {
        "backend": "canvas",
        "mouse": {"scale": 1.0, "step_delay_ms": 4, "button": "left", "clamp_to_screen": True},
        "image": {"dir": "~/Pictures/hanzidraw"},
    },
    "theme": {"preset": "ink"},
}

PRESETS: dict[str, dict[str, Any]] = {
    "none": {},
    "ink": {
        "glyph": {"color": "#111111", "outline_color": "#cccccc"},
        "canvas": {"background": "#fdfdf7", "grid_color": "#e5ded0"},
    },
    "neon": {
        "glyph": {"color": "#39ff14", "outline_color": "#1c3d1a", "stroke_width_px": 12},
        "canvas": {"background": "#0b0f0a", "grid_color": "#1c2a18"},
    },
    "chalk": {
        "glyph": {"color": "#f2f2f2", "outline_color": "#4a5a4a", "stroke_width_px": 16},
        "canvas": {"background": "#1f2d24", "grid_color": "#33463a"},
    },
}

_CHOICES = {
    "glyph.style": ("brush", "outline"),
    "glyph.animation.easing": ("linear", "ease_in", "ease_out", "ease_in_out"),
    "canvas.mode": ("sheet", "single"),
    "canvas.grid": ("none", "tian", "mi", "cross"),
    "output.backend": ("canvas", "mouse", "image"),
    "output.mouse.button": ("left", "right", "middle"),
    "theme.preset": tuple(PRESETS),
}

_POSITIVE = (
    "glyph.size_px",
    "glyph.stroke_width_px",
    "glyph.animation.stroke_ms",
    "canvas.columns",
    "canvas.advance",
    "ime.page_size",
    "ime.max_candidates",
    "output.mouse.scale",
)

_NON_NEGATIVE = ("glyph.animation.gap_ms", "output.mouse.step_delay_ms")

_COLOURS = ("glyph.color", "glyph.outline_color", "canvas.background", "canvas.grid_color")

# A single colour, as #rgb / #rrggbb or one of the basic CSS names every
# renderer here (Qt and SVG alike) understands. The two-colour gradient form the
# README once advertised is withdrawn: it was accepted without complaint and
# then stringified into stroke="['#c0392b', '#f39c12']", so the strokes silently
# disappeared and the GUI got an invalid QColor.
_HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_NAMED_COLOURS = frozenset(
    (
        "black",
        "silver",
        "gray",
        "grey",
        "white",
        "maroon",
        "red",
        "purple",
        "fuchsia",
        "magenta",
        "green",
        "lime",
        "olive",
        "yellow",
        "navy",
        "blue",
        "teal",
        "aqua",
        "cyan",
        "orange",
    )
)


def _is_colour(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_HEX_COLOUR.match(value)) or value.lower() in _NAMED_COLOURS


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def config_path() -> Path:
    if _is_windows():
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP / "config.toml"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP / "config.toml"


def data_dir() -> Path:
    if _is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP


def db_path() -> Path:
    return data_dir() / "hanzidraw.sqlite"


def _deep_merge(base: dict, over: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _dig(d: dict, dotted: str) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def _put(d: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


@dataclass(frozen=True)
class Config:
    data: dict[str, Any]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    path: Path | None

    def get(self, dotted: str) -> Any:
        return _dig(self.data, dotted)


def _prune_and_validate_structure(
    user: dict, defaults: dict, prefix: str = ""
) -> tuple[dict, list[str], list[str]]:
    """Recursively validate user config structure against DEFAULTS.

    At each key, determine if it is unknown, mistyped (dict vs scalar), or valid,
    and either keep or drop it. Record errors and warnings accordingly.

    Returns: (cleaned_user_dict, errors, warnings)
    """
    cleaned: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for key, user_value in user.items():
        dotted = f"{prefix}{key}" if prefix else key

        if key not in defaults:
            # Unknown key at this level
            warnings.append(f"{dotted}: unknown setting, ignored")
            continue

        default_value = defaults[key]

        # Check type mismatches
        if isinstance(default_value, dict):
            if isinstance(user_value, dict):
                # Both are dicts - recurse into them
                sub_cleaned, sub_errors, sub_warnings = _prune_and_validate_structure(
                    user_value, default_value, dotted + "."
                )
                cleaned[key] = sub_cleaned
                errors.extend(sub_errors)
                warnings.extend(sub_warnings)
            else:
                # Scalar where dict (section) expected
                errors.append(
                    f"{dotted}: expected a section ([{dotted}]), got a scalar value; using defaults"
                )
                # Drop this key - defaults will be used
        else:
            # Default value is a scalar
            if isinstance(user_value, dict):
                # Dict (section) where scalar expected
                errors.append(f"{dotted}: expected a value, got a section; using defaults")
                # Drop this key - defaults will be used
            else:
                # Both are scalars - keep user value
                cleaned[key] = user_value

    return cleaned, errors, warnings


def _validate(merged: dict) -> list[str]:
    errors: list[str] = []
    for key, allowed in _CHOICES.items():
        value = _dig(merged, key)
        if value not in allowed:
            errors.append(f"{key}: {value!r} is not one of {', '.join(map(str, allowed))}")
            _put(merged, key, _dig(DEFAULTS, key))
    for key in _POSITIVE:
        value = _dig(merged, key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"{key}: expected a number greater than 0, got {value!r}")
            _put(merged, key, _dig(DEFAULTS, key))
    for key in _NON_NEGATIVE:
        value = _dig(merged, key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append(f"{key}: expected a number of 0 or more, got {value!r}")
            _put(merged, key, _dig(DEFAULTS, key))
    for key in _COLOURS:
        value = _dig(merged, key)
        if not _is_colour(value):
            errors.append(
                f'{key}: expected one colour, as "#rgb", "#rrggbb" or a basic '
                f"colour name, got {value!r}"
            )
            _put(merged, key, _dig(DEFAULTS, key))
    return errors


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    errors: list[str] = []
    warnings: list[str] = []
    user: dict[str, Any] = {}
    if path.exists():
        try:
            user = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
            errors.append(f"{path}: could not be parsed ({exc}); using defaults")
            user = {}

    # Recursively validate and clean user config structure
    filtered_user, struct_errors, struct_warnings = _prune_and_validate_structure(user, DEFAULTS)
    errors.extend(struct_errors)
    warnings.extend(struct_warnings)

    # Get preset name from cleaned user config
    default_preset = DEFAULTS["theme"]["preset"]
    preset_name = default_preset
    if "theme" in filtered_user and isinstance(filtered_user.get("theme"), dict):
        preset_name = filtered_user["theme"].get("preset", preset_name)

    if preset_name not in PRESETS:
        # A bogus name used to merge *no* preset at all, so the user silently got
        # bare defaults instead of the theme they thought they had chosen. Fall
        # back to the default preset here; _validate reports the named error and
        # resets the key itself, so this stays one message, not two.
        preset_name = default_preset

    preset = PRESETS[preset_name]
    merged = _deep_merge(_deep_merge(DEFAULTS, preset), filtered_user)
    errors += _validate(merged)
    return Config(data=merged, errors=tuple(errors), warnings=tuple(warnings), path=path)

"""Defaults, TOML loading/validation, and platform paths.

Validation never raises: a bad value is replaced by its default and recorded in
``Config.errors`` so the UI can show it in the status bar.
"""

from __future__ import annotations

import os
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
        "image": {"dir": "~/Pictures/hanzidraw", "format": "png"},
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
    "output.image.format": ("png", "svg"),
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


def _walk(d: dict, prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            items += _walk(v, key + ".")
        else:
            items.append((key, v))
    return items


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
    return errors


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    errors: list[str] = []
    warnings: list[str] = []
    user: dict[str, Any] = {}
    if path.exists():
        try:
            user = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: could not be parsed ({exc}); using defaults")
            user = {}

    user_keys = {k for k, _ in _walk(user)}
    for key in sorted(user_keys):
        try:
            _dig(DEFAULTS, key)
        except KeyError:
            warnings.append(f"{key}: unknown setting, ignored")

    preset_name = user.get("theme", {}).get("preset", DEFAULTS["theme"]["preset"])
    preset = PRESETS.get(preset_name, {})
    merged = _deep_merge(_deep_merge(DEFAULTS, preset), user)
    errors += _validate(merged)
    return Config(data=merged, errors=tuple(errors), warnings=tuple(warnings), path=path)

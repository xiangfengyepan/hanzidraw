import textwrap

import pytest

from hanzidraw.config import DEFAULTS, PRESETS, Config, load_config


def test_defaults_are_returned_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.get("glyph.size_px") == DEFAULTS["glyph"]["size_px"]
    assert cfg.get("canvas.mode") == "sheet"
    assert cfg.errors == ()


def test_user_values_override_defaults_and_presets_are_layered_under(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""
        [glyph]
        color = "#ff0000"
        [theme]
        preset = "neon"
    """),
        encoding="utf-8",
    )
    cfg = load_config(p)
    # explicit value wins over the preset it sits under
    assert cfg.get("glyph.color") == "#ff0000"
    # unspecified keys still come from the preset, not the bare defaults
    assert cfg.get("canvas.background") != DEFAULTS["canvas"]["background"]


def test_bad_value_falls_back_to_default_with_an_error_not_an_exception(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[glyph]\nstyle = "graffiti"\nsize_px = -5\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.get("glyph.style") == "brush"
    assert cfg.get("glyph.size_px") == DEFAULTS["glyph"]["size_px"]
    assert len(cfg.errors) == 2
    assert any("glyph.style" in e for e in cfg.errors)


def test_unknown_key_is_a_warning_and_is_kept_readable(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[glyph]\ncolour = "#fff"\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.errors == ()
    assert any("glyph.colour" in w for w in cfg.warnings)
    # Unknown key should not be in the data
    try:
        cfg.get("glyph.colour")
        raise AssertionError("expected KeyError for unknown key glyph.colour")
    except KeyError:
        pass


def test_malformed_toml_reports_one_error_and_uses_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[glyph\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.get("glyph.style") == "brush"
    assert len(cfg.errors) == 1


def test_get_rejects_a_key_that_is_not_in_the_schema():
    cfg = Config(data=DEFAULTS, errors=(), warnings=(), path=None)
    try:
        cfg.get("glyph.nonexistent")
    except KeyError:
        return
    raise AssertionError("expected KeyError for an unknown dotted key")


def test_scalar_value_where_table_is_expected_degrades_gracefully(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('theme = "foo"\n', encoding="utf-8")
    cfg = load_config(p)
    # Should use defaults for theme, not crash
    assert cfg.get("theme.preset") == DEFAULTS["theme"]["preset"]
    # Should record an error about the structure problem
    assert len(cfg.errors) == 1
    assert "theme" in cfg.errors[0]
    assert "section" in cfg.errors[0]


def test_scalar_at_top_level_table_key_degrades_gracefully(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('glyph = "foo"\n', encoding="utf-8")
    cfg = load_config(p)
    # Should use defaults for glyph, not crash
    assert cfg.get("glyph.style") == DEFAULTS["glyph"]["style"]
    # Should record an error about the structure problem
    assert len(cfg.errors) == 1
    assert "glyph" in cfg.errors[0]
    assert "section" in cfg.errors[0]


def test_unreadable_file_degrades_gracefully(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("valid = true\n", encoding="utf-8")
    # Make it unreadable (if we have permissions)
    try:
        p.chmod(0o000)
        cfg = load_config(p)
        # Should fall back to defaults
        assert cfg.get("glyph.style") == DEFAULTS["glyph"]["style"]
        # Should record an error
        assert len(cfg.errors) == 1
        assert "could not be parsed" in cfg.errors[0]
    finally:
        # Restore permissions for cleanup
        p.chmod(0o644)


def test_valid_nested_config_survives_and_overrides_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""
        [glyph.animation]
        enabled = false
        stroke_ms = 500
        [output.mouse]
        scale = 2.0
    """),
        encoding="utf-8",
    )
    cfg = load_config(p)
    # Valid nested values should survive into Config
    assert cfg.get("glyph.animation.enabled") is False
    assert cfg.get("glyph.animation.stroke_ms") == 500
    assert cfg.get("output.mouse.scale") == 2.0
    # No errors or warnings for valid nested config
    assert cfg.errors == ()
    assert cfg.warnings == ()


def test_nested_unknown_leaf_warns_and_is_dropped_siblings_survive(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent("""
        [glyph.animation]
        enabled = false
        wobble = 3
    """),
        encoding="utf-8",
    )
    cfg = load_config(p)
    # Valid nested value survives
    assert cfg.get("glyph.animation.enabled") is False
    # Unknown nested leaf is dropped but warned
    assert any("glyph.animation.wobble" in w for w in cfg.warnings)
    assert cfg.errors == ()
    # Verify wobble is not accessible
    try:
        cfg.get("glyph.animation.wobble")
        raise AssertionError("expected KeyError for glyph.animation.wobble")
    except KeyError:
        pass


def test_theme_scalar_produces_one_error_no_warnings(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('theme = "neon"\n', encoding="utf-8")
    cfg = load_config(p)
    # Should use defaults, not crash
    assert cfg.get("theme.preset") == DEFAULTS["theme"]["preset"]
    # Should have exactly one error (the structural mismatch)
    assert len(cfg.errors) == 1
    assert "theme" in cfg.errors[0]
    assert "section" in cfg.errors[0]
    # No warnings - theme is a known key with the wrong shape, not unknown
    assert cfg.warnings == ()


def test_scalar_expected_but_table_provided(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[glyph.size_px]\na = 1\n", encoding="utf-8")
    cfg = load_config(p)
    # Should fall back to default size_px
    assert cfg.get("glyph.size_px") == DEFAULTS["glyph"]["size_px"]
    # Should record the error
    assert len(cfg.errors) == 1
    assert "glyph.size_px" in cfg.errors[0]
    assert "section" in cfg.errors[0] or "value" in cfg.errors[0]


@pytest.mark.parametrize(
    "value",
    [
        '["#c0392b", "#f39c12"]',  # the README's old gradient promise
        "12",  # not a string at all
        '"#12345"',  # malformed hex
        '"rebeccapurple"',  # a name outside the accepted set
    ],
)
def test_a_colour_that_is_not_a_usable_colour_is_a_reported_error(tmp_path, value):
    # The gradient form was accepted and then stringified into
    # stroke="['#c0392b', '#f39c12']", which is invalid SVG, so the strokes
    # silently vanished and the GUI got an invalid QColor.
    path = tmp_path / "c.toml"
    path.write_text(f"[glyph]\ncolor = {value}\n", encoding="utf-8")
    cfg = load_config(path)
    assert any("glyph.color" in e for e in cfg.errors), cfg.errors
    assert cfg.get("glyph.color") == DEFAULTS["glyph"]["color"]


@pytest.mark.parametrize("value", ["#fff", "#FFFFFF", "#111111", "red", "black"])
def test_a_usable_colour_is_accepted(tmp_path, value):
    path = tmp_path / "c.toml"
    path.write_text(f'[glyph]\ncolor = "{value}"\n', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.errors == ()
    assert cfg.get("glyph.color") == value


def test_every_colour_key_is_validated_not_just_glyph_color(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        '[glyph]\noutline_color = "nope"\n[canvas]\nbackground = 3\ngrid_color = "#gg0000"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    for key in ("glyph.outline_color", "canvas.background", "canvas.grid_color"):
        assert any(key in e for e in cfg.errors), (key, cfg.errors)


def test_output_image_format_is_gone(tmp_path):
    # Withdrawn in the final review: it was validated and never read; `draw`
    # decides the format from the output suffix.
    assert "format" not in DEFAULTS["output"]["image"]
    path = tmp_path / "c.toml"
    path.write_text('[output.image]\nformat = "png"\n', encoding="utf-8")
    cfg = load_config(path)
    assert any("output.image.format" in w for w in cfg.warnings), cfg.warnings


def test_a_bogus_theme_preset_is_a_named_error_and_uses_the_default_preset(tmp_path):
    # Deferred minor #3: the bogus name merged *no* preset (PRESETS.get(name, {}))
    # and was only reported afterwards, so the merge fell through to bare
    # defaults. Today the default preset ("ink") happens to carry the same
    # values as DEFAULTS, which is exactly why this needs pinning rather than
    # eyeballing: comparing against a real default-preset load keeps it honest
    # if either side ever changes.
    bogus = tmp_path / "bogus.toml"
    bogus.write_text('[theme]\npreset = "sparkles"\n', encoding="utf-8")
    default = tmp_path / "default.toml"
    default.write_text(f'[theme]\npreset = "{DEFAULTS["theme"]["preset"]}"\n', encoding="utf-8")

    cfg = load_config(bogus)
    assert any("theme.preset" in e for e in cfg.errors), cfg.errors
    assert cfg.data == load_config(default).data
    assert PRESETS[DEFAULTS["theme"]["preset"]] is not None  # the preset really exists

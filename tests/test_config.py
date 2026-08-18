import textwrap

from hanzidraw.config import DEFAULTS, Config, load_config


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

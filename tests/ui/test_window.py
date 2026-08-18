import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from hanzidraw.config import DEFAULTS, load_config  # noqa: E402
from hanzidraw.data.store import Store  # noqa: E402
from hanzidraw.render.glyph import Glyph  # noqa: E402
from hanzidraw.render.sheet import Sheet  # noqa: E402
from hanzidraw.ui.window import MainWindow  # noqa: E402

MEDIANS = (((-512, 0), (512, 0)), ((0, -512), (0, 512)))


@pytest.fixture
def window(qtbot, tmp_path):
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_char(ord("是"), 4, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.add_reading("shi", ord("是"))
    store.add_phrase("shi shi", "是十", 900.0)
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "none.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    return win


def _type(qtbot, window, text):
    for ch in text:
        qtbot.keyClick(window, ch)


def test_typing_shows_candidates_in_the_bar(qtbot, window):
    _type(qtbot, window, "shi")
    assert "是" in window.bar.text()
    assert "shi" in window.bar.text()


def test_space_commits_the_highlighted_full_match_character(qtbot, window):
    # Typing one syllable makes single characters full matches; the two-character
    # phrase is only a prediction, so a character leads the page.
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_Space)
    assert window.canvas.glyph_count == 1


def test_a_digit_draws_the_single_character_candidate(qtbot, window):
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)  # candidate 1 is the phrase, 2 is 是
    assert window.canvas.glyph_count == 1


def test_a_phrase_commits_two_glyphs_in_one_keystroke(qtbot, window):
    # Type the whole reading, so 是十 is a full match rather than a prediction.
    _type(qtbot, window, "shishi")
    qtbot.keyClick(window, Qt.Key.Key_1)
    assert window.canvas.glyph_count == 2


def test_f2_toggles_the_canvas_mode(qtbot, window):
    qtbot.keyClick(window, Qt.Key.Key_F2)
    assert window.canvas._mode == "single"
    qtbot.keyClick(window, Qt.Key.Key_F2)
    assert window.canvas._mode == "sheet"


def test_ctrl_z_undoes_and_ctrl_l_clears(qtbot, window):
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)  # one character, so one undo empties the canvas
    qtbot.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.canvas.glyph_count == 0
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_Space)
    qtbot.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    assert window.canvas.glyph_count == 0


def test_config_errors_are_shown_in_the_status_bar(qtbot, tmp_path):
    (tmp_path / "c.toml").write_text('[glyph]\nstyle = "graffiti"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    assert "glyph.style" in win.statusBar().currentMessage()


def test_outline_style_without_outlines_reports_a_readable_error(qtbot, tmp_path):
    (tmp_path / "c.toml").write_text('[glyph]\nstyle = "outline"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.set_meta("build_medians_only", "1")
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    assert "medians-only" in win.statusBar().currentMessage()


def test_reload_config_applies_new_values_without_restarting(qtbot, window, tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[glyph]\nsize_px = 80\n", encoding="utf-8")
    window.reload_config(path)
    assert window.canvas.sheet.size == 80.0


def test_the_practice_grid_grows_to_two_rows_after_eight_characters(qtbot, tmp_path):
    # A reviewer flagged, in Task 16, exactly the risk this guards against: if
    # commit_candidate ever forgot to call sheet.add() for each committed glyph,
    # the practice grid would stay frozen at one row no matter how much got
    # drawn, because the window (not the canvas) owns layout.
    store = Store.create(tmp_path / "db.sqlite")
    syllables = ["yi", "er", "san", "si", "wu", "liu", "qi", "ba"]
    chars = "一二三四五六七八"
    assert len(syllables) == len(chars) == 8
    for syl, ch in zip(syllables, chars, strict=True):
        store.add_char(ord(ch), 10, 1, MEDIANS, None)
        store.add_reading(syl, ord(ch))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "none.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    assert win.canvas.sheet.columns == DEFAULTS["canvas"]["columns"]  # six columns, default layout

    for syl in syllables:
        _type(qtbot, win, syl)
        qtbot.keyClick(win, Qt.Key.Key_Space)

    assert win.canvas.glyph_count == 8
    sheet = win.canvas.sheet
    width, height = sheet.size_px()
    assert height == pytest.approx(sheet.pitch * 2)  # grown to two rows, not frozen at one

    one_row = Sheet(
        columns=sheet.columns,
        advance=float(DEFAULTS["canvas"]["advance"]),
        size=sheet.size,
        wrap=sheet.wrap,
    )
    one_row.add(Glyph(()), "x")
    one_row_lines = len(one_row.grid_lines("tian"))
    two_row_lines = len(sheet.grid_lines("tian"))
    assert two_row_lines == one_row_lines * 2
    assert two_row_lines != one_row_lines


def test_a_paint_only_reload_keeps_the_sheet_so_the_next_commit_lands_in_the_next_cell(
    qtbot, window, tmp_path
):
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)  # commits the lone character "是"
    assert window.canvas.glyph_count == 1
    first = window.canvas.sheet.placed[0]

    path = tmp_path / "paint.toml"
    path.write_text('[glyph]\ncolor = "#ff0000"\n', encoding="utf-8")
    window.reload_config(path)

    # The glyph survived the reload, and the carriage kept its position.
    assert window.canvas.glyph_count == 1

    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)
    assert window.canvas.glyph_count == 2
    second = window.canvas.sheet.placed[1]
    assert second.oy == pytest.approx(first.oy)
    assert second.ox == pytest.approx(first.ox + window.canvas.sheet.pitch)


def test_a_layout_reload_clears_reports_it_and_the_next_commit_starts_at_the_first_cell(
    qtbot, window, tmp_path
):
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)
    assert window.canvas.glyph_count == 1

    path = tmp_path / "layout.toml"
    path.write_text("[glyph]\nsize_px = 80\n", encoding="utf-8")
    window.reload_config(path)

    assert window.canvas.glyph_count == 0
    assert "canvas cleared: layout settings changed" in window.statusBar().currentMessage()

    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)
    assert window.canvas.glyph_count == 1
    placed = window.canvas.sheet.placed[0]
    pad = (window.canvas.sheet.pitch - window.canvas.sheet.size) / 2.0
    assert placed.ox == pytest.approx(pad)
    assert placed.oy == pytest.approx(pad)

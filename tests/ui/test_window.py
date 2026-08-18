import math
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

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


def test_mouse_backend_without_pynput_falls_back_to_canvas_and_reports_it(
    qtbot, tmp_path, monkeypatch
):
    # pynput is genuinely unimportable in this headless environment, but the
    # test must not depend on that host fact: monkeypatching PynputPointer
    # itself keeps this deterministic (and safe) on any machine, including
    # one with a real display and pynput installed, where relying on the
    # environment would otherwise let a real MouseBackend seize the pointer.
    from hanzidraw.output import mouse as mouse_module

    def _raise_import_error(self, *_a, **_kw):
        raise ImportError("no pynput")

    monkeypatch.setattr(mouse_module.PynputPointer, "__init__", _raise_import_error)

    (tmp_path / "c.toml").write_text('[output]\nbackend = "mouse"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)

    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)

    assert "pynput" in win.statusBar().currentMessage()
    assert win.canvas.glyph_count == 1
    assert getattr(win, "_mouse", None) is None  # never set up; abort has nothing to grab


def test_image_backend_in_the_window_falls_back_to_canvas_and_reports_it(qtbot, tmp_path):
    # Finding 3 (coordinator, task-18 review): output.backend = "image" is
    # the headless `hanzidraw draw` path -- the window has nowhere to put a
    # file per keystroke, so before this fix it silently drew nothing at all:
    # no crash, no file, no canvas update, no message.
    (tmp_path / "c.toml").write_text('[output]\nbackend = "image"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)

    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)

    assert "draw command" in win.statusBar().currentMessage()
    assert win.canvas.glyph_count == 1


def test_mouse_clamp_uses_the_screens_last_addressable_pixel_not_one_past_it(
    qtbot, tmp_path, monkeypatch
):
    # Coordinator correction (task-18 second review): this is a direct
    # regression test for the specific line that was wrong -- _backend()'s
    # construction of the clamp box from the real screen geometry. A 1920-
    # wide screen's last addressable pixel column is 1919 (QRect.right());
    # a prior fix mistakenly added 1, which would let the clamp place the
    # cursor one column past the real screen.
    from hanzidraw.output import mouse as mouse_module

    monkeypatch.setattr(mouse_module.PynputPointer, "__init__", lambda self, *_a, **_kw: None)

    (tmp_path / "c.toml").write_text('[output]\nbackend = "mouse"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)

    class _FakeScreen:
        def geometry(self):
            return QRect(0, 0, 1920, 1080)

    monkeypatch.setattr(win, "screen", lambda: _FakeScreen())

    win._backend()

    assert win._mouse._clamp == (0.0, 0.0, 1919.0, 1079.0)


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


def test_the_canvas_is_in_a_scroll_area_sized_to_the_whole_sheet(qtbot, window):
    # Spec §6: the sheet is columns * advance * size_px wide and the view
    # scrolls when the window is narrower than that. Before this fix there was
    # no QScrollArea anywhere, so at stock defaults (1656 x 276 px sheet in a
    # 900 px window) the 4th, 5th and 6th character of every row were painted
    # outside the widget with no scrollbar and no indication at all.
    sheet = window.canvas.sheet
    width, height = sheet.size_px()

    assert window.scroll.widget() is window.canvas
    assert window.scroll.widgetResizable() is False  # never reflow on resize
    assert window.canvas.minimumWidth() == math.ceil(width)
    assert window.canvas.minimumHeight() == math.ceil(height)


def test_a_layout_reload_resizes_the_scrolled_canvas(qtbot, window, tmp_path):
    before = window.canvas.minimumWidth()
    path = tmp_path / "layout.toml"
    path.write_text("[glyph]\nsize_px = 80\n", encoding="utf-8")
    window.reload_config(path)

    width, _height = window.canvas.sheet.size_px()
    assert window.canvas.minimumWidth() == math.ceil(width)
    assert window.canvas.minimumWidth() != before


def test_scrollbars_appear_exactly_when_the_sheet_exceeds_the_viewport(qtbot, window):
    window.resize(900, 700)  # the real app's startup size
    window.show()
    qtbot.waitExposed(window)
    sheet_width = math.ceil(window.canvas.sheet.size_px()[0])
    assert sheet_width > window.scroll.viewport().width()
    assert window.scroll.horizontalScrollBar().maximum() > 0

    # Wide enough for the whole sheet: nothing left to scroll.
    window.resize(sheet_width + 400, 700)
    qtbot.waitUntil(lambda: window.scroll.viewport().width() > sheet_width)
    assert window.scroll.horizontalScrollBar().maximum() == 0


def test_ctrl_s_exports_the_whole_sheet_not_just_the_visible_viewport(qtbot, tmp_path):
    # Six characters at stock defaults do not fit in a 900 px window; grab()
    # used to export the viewport only, so characters 4-6 were missing from the
    # saved image as well as from the screen.
    store = Store.create(tmp_path / "db.sqlite")
    syllables = ["yi", "er", "san", "si", "wu", "liu"]
    chars = "一二三四五六"
    for syl, ch in zip(syllables, chars, strict=True):
        store.add_char(ord(ch), 10, 2, MEDIANS, None)
        store.add_reading(syl, ord(ch))
    store.finish()
    out_dir = tmp_path / "shots"
    (tmp_path / "c.toml").write_text(f'[output.image]\ndir = "{out_dir}"\n', encoding="utf-8")
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    win.resize(900, 700)
    win.show()
    qtbot.waitExposed(win)

    for syl in syllables:
        _type(qtbot, win, syl)
        qtbot.keyClick(win, Qt.Key.Key_Space)
    assert win.canvas.glyph_count == 6

    qtbot.keyClick(win, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    saved = out_dir / "sheet.png"
    assert saved.exists()

    sheet = win.canvas.sheet
    width, height = sheet.size_px()
    image = QImage(str(saved))
    assert (image.width(), image.height()) == (math.ceil(width), math.ceil(height))
    assert image.width() > win.scroll.viewport().width()  # more than the viewport held
    for placed in sheet.placed:
        assert 0 <= placed.ox < image.width()
        assert 0 <= placed.oy < image.height()
        assert placed.ox + placed.size <= image.width()
        assert placed.oy + placed.size <= image.height()


def test_toggling_always_on_top_at_runtime_keeps_the_window_visible(qtbot, window, tmp_path):
    # C3: apply_config called setWindowFlag on every reload, and Qt re-parents
    # and *hides* a created widget when its flags change. Nothing called show()
    # again, so the window vanished for good -- no tray icon, no way back, and
    # the drawn sheet gone with it.
    window.show()
    qtbot.waitExposed(window)
    assert window.isVisible()

    on = tmp_path / "on.toml"
    on.write_text("[canvas]\nalways_on_top = true\n", encoding="utf-8")
    window.reload_config(on)
    assert window.isVisible()
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    off = tmp_path / "off.toml"
    off.write_text("[canvas]\nalways_on_top = false\n", encoding="utf-8")
    window.reload_config(off)
    assert window.isVisible()
    assert not bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)


def test_a_reload_that_does_not_change_always_on_top_leaves_the_flag_alone(qtbot, window, tmp_path):
    window.show()
    qtbot.waitExposed(window)
    before = window.windowFlags()

    path = tmp_path / "paint.toml"
    path.write_text('[glyph]\ncolor = "#ff0000"\n', encoding="utf-8")
    window.reload_config(path)

    assert window.windowFlags() == before
    assert window.isVisible()


def test_ctrl_s_into_an_unwritable_directory_reports_a_message_not_an_exception(qtbot, tmp_path):
    # I5: save() discarded the boolean from QImage.save(), so a write that
    # failed without raising still printed "saved …"; and an unwritable
    # directory threw straight out of the Qt key handler.
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write permissions")

    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    (tmp_path / "c.toml").write_text(f'[output.image]\ndir = "{ro_dir}"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)

    ro_dir.chmod(0o555)
    try:
        qtbot.keyClick(win, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    finally:
        ro_dir.chmod(0o755)

    message = win.statusBar().currentMessage()
    assert "could not save" in message
    assert str(ro_dir / "sheet.png") in message
    assert not (ro_dir / "sheet.png").exists()


def test_ctrl_s_whose_directory_cannot_be_created_reports_a_message(qtbot, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write permissions")

    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    target_dir = ro_dir / "nested"
    (tmp_path / "c.toml").write_text(f'[output.image]\ndir = "{target_dir}"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)

    ro_dir.chmod(0o555)
    try:
        qtbot.keyClick(win, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    finally:
        ro_dir.chmod(0o755)

    assert "could not save" in win.statusBar().currentMessage()


def test_ctrl_s_reports_success_only_when_the_file_is_really_written(qtbot, tmp_path):
    out_dir = tmp_path / "shots"
    (tmp_path / "c.toml").write_text(f'[output.image]\ndir = "{out_dir}"\n', encoding="utf-8")
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "c.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)
    qtbot.keyClick(win, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)

    saved = out_dir / "sheet.png"
    assert saved.exists() and saved.stat().st_size > 0
    assert win.statusBar().currentMessage() == f"saved {saved}"


def test_an_aborted_mouse_draw_does_not_advance_the_carriage(qtbot, tmp_path, monkeypatch):
    # The sheet used to be advanced before draw_glyph could raise MouseAbort,
    # so an aborted draw left an empty cell behind and the next character
    # landed one cell further along than the user could see.
    from hanzidraw.output.mouse import MouseBackend

    class _Pointer:
        position = (0.0, 0.0)

        def move_to(self, x, y):
            raise AssertionError("the guard must refuse before touching the pointer")

        def press(self):
            raise AssertionError("the guard must refuse before pressing")

        def release(self):
            pass

    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("十"), 10, 2, MEDIANS, None)
    store.add_reading("shi", ord("十"))
    store.finish()
    win = MainWindow(
        store=store,
        cfg=load_config(tmp_path / "none.toml"),
        learn_path=tmp_path / "learn.json",
    )
    qtbot.addWidget(win)
    aborting = MouseBackend(
        _Pointer(),
        sleep=lambda _s: None,
        window_rect=lambda: (0.0, 0.0, 10_000.0, 10_000.0),  # everything overlaps us
    )
    monkeypatch.setattr(win, "_backend", lambda: aborting)

    _type(qtbot, win, "shi")
    qtbot.keyClick(win, Qt.Key.Key_Space)

    assert "overlaps" in win.statusBar().currentMessage()
    assert win.canvas.sheet.placed == ()  # the carriage never moved


def test_a_completed_draw_still_advances_the_carriage(qtbot, window):
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)
    assert len(window.canvas.sheet.placed) == 1
    _type(qtbot, window, "shi")
    qtbot.keyClick(window, Qt.Key.Key_2)
    placed = window.canvas.sheet.placed
    assert len(placed) == 2
    assert placed[1].ox == pytest.approx(placed[0].ox + window.canvas.sheet.pitch)

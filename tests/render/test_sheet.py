import pytest

from hanzidraw.render.glyph import Glyph
from hanzidraw.render.sheet import GridLine, Sheet

GLYPH = Glyph((((0.0, 0.0), (1.0, 1.0)),))


def _sheet(**kw):
    return Sheet(columns=3, advance=1.5, size=100.0, **kw)


def test_first_glyph_is_centred_in_the_first_cell():
    placed = _sheet().add(GLYPH, "沣")
    assert placed.ox == 25.0  # (150 - 100) / 2
    assert placed.oy == 25.0
    assert placed.size == 100.0


def test_carriage_advances_to_the_right():
    sheet = _sheet()
    sheet.add(GLYPH, "沣")
    second = sheet.add(GLYPH, "潘")
    assert second.ox == 175.0
    assert second.oy == 25.0


def test_carriage_wraps_after_the_last_column():
    sheet = _sheet()
    for ch in "一二三四":
        placed = sheet.add(GLYPH, ch)
    assert placed.ox == 25.0
    assert placed.oy == 175.0
    assert sheet.cursor == (1, 1)


def test_wrap_disabled_keeps_one_growing_row():
    sheet = _sheet(wrap=False)
    for ch in "一二三四":
        placed = sheet.add(GLYPH, ch)
    assert placed.oy == 25.0
    assert sheet.size_px()[0] >= 600.0


def test_undo_removes_the_last_glyph_and_rewinds_the_carriage():
    sheet = _sheet()
    sheet.add(GLYPH, "沣")
    sheet.add(GLYPH, "潘")
    removed = sheet.undo()
    assert removed.text == "潘"
    assert len(sheet.placed) == 1
    assert sheet.add(GLYPH, "叶").ox == 175.0  # the freed cell is reused


def test_undo_on_an_empty_sheet_is_none():
    assert _sheet().undo() is None


def test_clear_empties_the_sheet_and_resets_the_carriage():
    sheet = _sheet()
    sheet.add(GLYPH, "沣")
    sheet.clear()
    assert sheet.placed == ()
    assert sheet.cursor == (0, 0)
    assert sheet.add(GLYPH, "潘").ox == 25.0


def test_size_px_covers_the_full_grid_when_wrapping():
    sheet = _sheet()
    for ch in "一二三四":
        sheet.add(GLYPH, ch)
    assert sheet.size_px() == (450.0, 300.0)


def test_grid_none_has_no_lines():
    assert _sheet().grid_lines("none") == ()


def test_tian_grid_has_a_box_and_a_cross_per_cell():
    lines = _sheet().grid_lines("tian")
    assert len(lines) == 6 * 3  # 4 border + 2 cross lines, one cell per column
    assert any(line.dashed for line in lines)


def test_mi_grid_adds_the_diagonals():
    assert len(_sheet().grid_lines("mi")) > len(_sheet().grid_lines("tian"))


def test_cross_grid_has_only_the_two_centre_lines_per_cell():
    assert len(_sheet().grid_lines("cross")) == 2 * 3


# --- Additional tests for the three required changes ---


def test_grid_lines_unknown_kind_raises_valueerror():
    """grid_lines() raises ValueError for unknown grid kinds."""
    sheet = _sheet()
    with pytest.raises(ValueError) as exc_info:
        sheet.grid_lines("bogus")
    assert "bogus" in str(exc_info.value)
    assert "cross" in str(exc_info.value)


def test_all_grid_kinds_still_work_after_guard():
    """Each valid grid kind still produces output after the guard is added."""
    sheet = _sheet()
    # "none" returns empty
    assert sheet.grid_lines("none") == ()
    # "tian", "mi", "cross" each return a non-empty tuple
    assert isinstance(sheet.grid_lines("tian"), tuple)
    assert len(sheet.grid_lines("tian")) > 0
    assert isinstance(sheet.grid_lines("mi"), tuple)
    assert len(sheet.grid_lines("mi")) > 0
    assert isinstance(sheet.grid_lines("cross"), tuple)
    assert len(sheet.grid_lines("cross")) > 0


def test_advance_zero_raises_valueerror():
    """Sheet rejects advance <= 0 with a ValueError naming the value."""
    with pytest.raises(ValueError) as exc_info:
        Sheet(columns=1, advance=0.0, size=240)
    assert "0" in str(exc_info.value)


def test_advance_negative_raises_valueerror():
    """Sheet rejects advance < 0 with a ValueError naming the value."""
    with pytest.raises(ValueError) as exc_info:
        Sheet(columns=1, advance=-1.5, size=240)
    assert "-1.5" in str(exc_info.value)


def test_size_zero_raises_valueerror():
    """Sheet rejects size <= 0 with a ValueError naming the value."""
    with pytest.raises(ValueError) as exc_info:
        Sheet(columns=1, advance=1.15, size=0.0)
    assert "0" in str(exc_info.value)


def test_size_negative_raises_valueerror():
    """Sheet rejects size < 0 with a ValueError naming the value."""
    with pytest.raises(ValueError) as exc_info:
        Sheet(columns=1, advance=1.15, size=-100.0)
    assert "-100" in str(exc_info.value)


def test_empty_sheet_shows_one_row_grid():
    """A never-touched sheet returns one row of grid for 'tian'."""
    sheet = _sheet()
    assert len(sheet.placed) == 0
    lines = sheet.grid_lines("tian")
    # One row, three columns: 6 lines per cell, 3 cells = 18 lines
    assert len(lines) == 6 * 3
    # All lines should be horizontal or vertical, within one row
    max_y = max(line.y1 for line in lines) if lines else 0.0
    # One row of cells, so max y should be one pitch (the bottom of the row)
    assert max_y == 150.0  # _sheet() has pitch=1.5*100=150


def test_placed_is_immutable():
    """Placed dataclass rejects mutation."""
    placed = _sheet().add(GLYPH, "沣")
    with pytest.raises(AttributeError):
        placed.ox = 999.0  # type: ignore


def test_gridline_is_immutable():
    """GridLine dataclass rejects mutation."""
    line = GridLine(0.0, 0.0, 100.0, 100.0, False)
    with pytest.raises(AttributeError):
        line.x1 = 999.0  # type: ignore


def test_placed_returns_distinct_object_each_call():
    """The 'placed' property returns a new tuple each call."""
    sheet = _sheet()
    sheet.add(GLYPH, "沣")
    tuple1 = sheet.placed
    tuple2 = sheet.placed
    # Same content
    assert tuple1 == tuple2
    # Different objects
    assert tuple1 is not tuple2

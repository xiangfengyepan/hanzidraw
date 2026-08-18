import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from hanzidraw.ui.window import key_from_event  # noqa: E402


def _event(key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers, text)


def test_letters_become_letter_keys():
    assert key_from_event(_event(Qt.Key.Key_B, "b")).name == "b"
    assert key_from_event(_event(Qt.Key.Key_B, "B")).name == "b"  # case folded


def test_digits_and_named_keys_map_across():
    assert key_from_event(_event(Qt.Key.Key_3, "3")).name == "3"
    assert key_from_event(_event(Qt.Key.Key_Space, " ")).name == "space"
    assert key_from_event(_event(Qt.Key.Key_Return, "\r")).name == "enter"
    assert key_from_event(_event(Qt.Key.Key_Backspace)).name == "backspace"
    assert key_from_event(_event(Qt.Key.Key_Escape)).name == "escape"
    assert key_from_event(_event(Qt.Key.Key_Apostrophe, "'")).name == "apostrophe"
    assert key_from_event(_event(Qt.Key.Key_F2)).name == "f2"


def test_control_combinations_set_the_ctrl_flag():
    key = key_from_event(_event(Qt.Key.Key_Z, "z", Qt.KeyboardModifier.ControlModifier))
    assert (key.name, key.ctrl) == ("z", True)


def test_zero_is_not_a_selection_key():
    assert key_from_event(_event(Qt.Key.Key_0, "0")) is None


def test_unrelated_keys_are_ignored():
    assert key_from_event(_event(Qt.Key.Key_F5)) is None
    assert key_from_event(_event(Qt.Key.Key_Shift)) is None

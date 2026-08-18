import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - GUI extra not installed
    QApplication = None

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _qt_application():
    """Create the one Qt application instance the whole session will use.

    Qt's application-class choice, like its platform-plugin choice, is made
    once per process and is irreversible: a bare ``QGuiApplication`` (which
    ``output.image.save_png`` creates lazily when headless PNG rasterising
    needs one and none exists yet) cannot coexist with the ``QApplication``
    pytest-qt's ``qtbot`` fixture needs for widget tests such as
    ``tests/ui/test_canvasview.py`` — mixing the two aborts the interpreter.
    Creating the (compatible, widget-capable) QApplication here, before any
    test runs, means later lazy ``QGuiApplication.instance() is None`` checks
    always find it already satisfied.
    """
    if QApplication is not None and QApplication.instance() is None:
        QApplication([])
    yield


@pytest.fixture(autouse=True)
def _isolate_user_config(tmp_path, monkeypatch):
    """No test may read or write the real user configuration or data directory.

    Several CLI tests call ``cli.main(["draw", ...])`` with no ``--config``, so
    they fall through to ``load_config(config_path())`` -- the owner's own
    ``~/.config/hanzidraw/config.toml``. A machine with ``style = "outline"``
    configured turned the suite red, and the owner is precisely the person who
    has that file. Both platform locations are redirected, so a Windows run is
    isolated too.

    ``XDG_DATA_HOME``/``LOCALAPPDATA`` are isolated the same way, for the same
    reason: nothing but the one test that explicitly opts back out of it (the
    firmware golden comparison in tests/firmware/test_emit_c.py, which reads
    the real database read-only on purpose) should be able to reach the
    owner's real data directory at all. Isolating this used to mean that test
    would ``skip`` instead of ``xfail`` wherever the database was not found --
    which, in practice, was everywhere except this one laptop, so the
    "399 passed, 1 xfailed" baseline was never actually reproducible
    elsewhere. Letting that one test un-isolate itself keeps both properties.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES

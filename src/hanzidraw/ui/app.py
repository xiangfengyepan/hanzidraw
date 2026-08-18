"""Builds the Qt application, watches the config file, shows the window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtWidgets import QApplication

from ..config import config_path, db_path, load_config
from ..data.store import Store, StoreError
from .window import MainWindow


def run(config: Path | None = None, db: Path | None = None) -> int:
    cfg_file = config or config_path()
    try:
        store = Store.open(db or db_path())
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    app = QApplication.instance() or QApplication(sys.argv[:1])
    cfg = load_config(cfg_file)
    window = MainWindow(store=store, cfg=cfg)
    window.resize(900, 700)
    window.show()

    watcher = QFileSystemWatcher()
    if cfg_file.exists():
        watcher.addPath(str(cfg_file))

    def on_changed(_path: str) -> None:
        window.reload_config(cfg_file)
        if cfg_file.exists() and str(cfg_file) not in watcher.files():
            watcher.addPath(str(cfg_file))  # editors replace the file rather than write in place

    watcher.fileChanged.connect(on_changed)
    return int(app.exec())

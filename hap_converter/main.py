"""Entry point: load mapping.json, launch the UI.

When frozen by PyInstaller, mapping.json is looked up next to the executable
so it stays user-editable; in development it comes from config/mapping.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from hap_converter.engine import config as config_mod
from hap_converter.ui.app_window import AppWindow


def default_config_path() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(sys.executable).parent / "mapping.json"
    return Path(__file__).resolve().parents[1] / "config" / "mapping.json"


def main() -> int:
    app = QApplication(sys.argv)
    config_path = default_config_path()
    try:
        config = config_mod.load(config_path)
    except config_mod.ConfigError as exc:
        QMessageBox.critical(None, "Configuration error", str(exc))
        return 1

    window = AppWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

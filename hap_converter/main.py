"""Entry point: load mapping.json, launch the UI.

When frozen by PyInstaller, mapping.json is looked up next to the executable
so it stays user-editable; in development it comes from config/mapping.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from hap_converter.airsizer.engine import config as air_config_mod
from hap_converter.engine import config as config_mod
from hap_converter.ui.app_window import AppWindow


def _resolve_config(name: str) -> Path:
    """Locate an editable config file, bundled or in development.

    Frozen: a copy next to the exe wins (user-editable override), else the
    copy bundled inside it. Each file is resolved independently, so dropping
    one override beside the exe never hides the others. AirSizer's catalogs/
    and diagrams/ are read relative to whichever input_matrix.json wins.
    """
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        beside_exe = Path(sys.executable).parent / name
        if beside_exe.is_file():
            return beside_exe
        return Path(getattr(sys, "_MEIPASS", ".")) / name
    return Path(__file__).resolve().parents[1] / "config" / name


def default_config_path() -> Path:
    return _resolve_config("mapping.json")


def airsizer_config_path() -> Path:
    return _resolve_config("input_matrix.json")


def main() -> int:
    app = QApplication(sys.argv)
    config_path = default_config_path()
    try:
        config = config_mod.load(config_path)
    except config_mod.ConfigError as exc:
        QMessageBox.critical(None, "Configuration error", str(exc))
        return 1

    # AirSizer Pro is optional at startup: if its catalogs cannot be loaded the
    # app still runs HAPExt, with the reason on the disabled tab.
    air_config, air_error = None, ""
    try:
        air_config = air_config_mod.load(airsizer_config_path())
    except air_config_mod.ConfigError as exc:
        air_error = f"AirSizer Pro is unavailable: {exc}"

    window = AppWindow(config, air_config=air_config, air_error=air_error)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

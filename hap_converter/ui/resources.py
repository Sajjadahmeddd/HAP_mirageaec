"""Bundled UI assets (logo, icons): resolves paths in dev and inside the
PyInstaller one-file bundle (where assets are unpacked to sys._MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(getattr(sys, "_MEIPASS", ".")) / "assets" / name
    return Path(__file__).parent / "assets" / name

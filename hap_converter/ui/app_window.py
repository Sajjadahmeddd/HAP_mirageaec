"""Application shell: frameless window with custom title bar, product tab
bar, and a QStackedWidget hosting the four pages. Owns shared state
(selected PDF, output folder, config, last Result) and all navigation.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hap_converter import __version__
from hap_converter.engine.config import Config
from hap_converter.engine.pipeline import Result

from . import theme
from .pages.convert_page import ConvertPage
from .pages.home_page import HomePage
from .pages.result_page import ResultPage
from .pages.upload_page import UploadPage
from .recents import RecentEntry, RecentStore
from .widgets import label
from .worker import ConvertWorker


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow):
        super().__init__()
        self.setObjectName("TitleBar")
        self._window = window
        self._drag_pos = None
        self.setFixedHeight(40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)

        logo = QLabel("▰")
        logo.setStyleSheet(f"color: {theme.GREEN}; font-size: 16px;")
        lay.addWidget(logo)
        brand = QLabel(
            f'<span style="color:{theme.ORANGE}">M</span>'
            f'<span style="color:{theme.GREEN}">AEC</span>'
        )
        brand.setObjectName("BrandLabel")
        brand.setTextFormat(Qt.RichText)
        lay.addWidget(brand)
        lay.addWidget(label(f"v{__version__}", "VersionLabel"))
        lay.addStretch(1)

        for text, handler, name in (
            ("–", window.showMinimized, "WinBtn"),
            ("□", self._toggle_maximize, "WinBtn"),
            ("✕", window.close, "WinBtnClose"),
        ):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(handler)
            lay.addWidget(btn)
            if text == "□":
                self._max_btn = btn

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self._max_btn.setText("□")
        else:
            self._window.showMaximized()
            self._max_btn.setText("❐")

    # window dragging
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        self._toggle_maximize()


class TabBar(QFrame):
    def __init__(self, on_hapext=None):
        super().__init__()
        self.setObjectName("TabBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(4)
        for name, active, enabled in (
            ("HAPExt", True, True),
            ("AirSizer Pro", False, False),
            ("HAPAudit", False, False),
        ):
            btn = QPushButton(name)
            btn.setProperty("tabRole", "tab")
            btn.setProperty("tabActive", "true" if active else "false")
            btn.setEnabled(enabled)
            if enabled and on_hapext:
                btn.setCursor(Qt.PointingHandCursor)
                btn.setToolTip("Go to the HAPExt home screen")
                btn.clicked.connect(on_hapext)
            if not enabled:
                btn.setToolTip("Coming soon")
            lay.addWidget(btn)
        lay.addStretch(1)


class AppWindow(QMainWindow):
    """The `ctx` object passed to every page: navigation + shared state."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.recents = RecentStore()

        # shared conversion state
        self.pdf_path: str | None = None
        self.pdf_pages: int = 0
        self.pdf_size: int = 0
        self.output_dir: str = ""
        self.output_dir_overridden = False
        self.result: Result | None = None
        self.project_details: dict[str, str] | None = None
        self._worker: ConvertWorker | None = None
        self._cancel_requested = False

        self.setWindowTitle("MAEC — HAPExt")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setMinimumSize(1120, 700)
        self.setStyleSheet(theme.APP_QSS)

        shell = QWidget()
        shell.setObjectName("Canvas")
        shell_lay = QVBoxLayout(shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)
        shell_lay.addWidget(TitleBar(self))
        shell_lay.addWidget(TabBar(on_hapext=self.go_home))

        self.stack = QStackedWidget()
        self.home_page = HomePage(self)
        self.upload_page = UploadPage(self)
        self.convert_page = ConvertPage(self)
        self.result_page = ResultPage(self)
        for page in (self.home_page, self.upload_page, self.convert_page, self.result_page):
            self.stack.addWidget(page)
        shell_lay.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

    # ---------------------------------------------------------- navigation
    def go_home(self) -> None:
        self.home_page.refresh()
        self.stack.setCurrentWidget(self.home_page)

    def go_upload(self) -> None:
        self.upload_page.refresh()
        self.stack.setCurrentWidget(self.upload_page)

    # ---------------------------------------------------------- state
    def set_pdf(self, path: str | None, pages: int = 0, size_bytes: int = 0) -> None:
        self.pdf_path = path
        self.pdf_pages = pages
        self.pdf_size = size_bytes

    def open_recent(self, entry: RecentEntry) -> None:
        self.upload_page.refresh()
        self.stack.setCurrentWidget(self.upload_page)
        self.upload_page.preselect(entry.pdf_path)

    # ---------------------------------------------------------- conversion
    @staticmethod
    def staging_dir() -> str:
        """Hidden working folder: converted CSVs live here until the user
        explicitly saves via Download CSV — nothing appears next to the PDF."""
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        path = Path(base) / "MAEC" / "output"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def start_conversion(self) -> None:
        if not self.pdf_path or self._worker is not None:
            return
        self._cancel_requested = False
        # an explicitly chosen output folder is honored; otherwise stage
        out_dir = self.output_dir if self.output_dir_overridden else self.staging_dir()
        self.convert_page.begin(self.pdf_path, self.pdf_size)
        self.stack.setCurrentWidget(self.convert_page)

        self._worker = ConvertWorker(self.pdf_path, out_dir, self.config, parent=self)
        self._worker.progress.connect(self.convert_page.on_progress)
        self._worker.finished_result.connect(self._on_finished)
        self._worker.start()

    def cancel_conversion(self) -> None:
        if self._worker is not None:
            self._cancel_requested = True
            self._worker.cancel()

    def _on_finished(self, result: Result) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.wait()

        cancelled = self._cancel_requested or any(
            issue.field == "cancelled" for issue in result.issues
        )
        if cancelled:
            self.go_upload()
            return

        self.result = result
        self.recents.add(
            RecentEntry(
                pdf_path=self.pdf_path or "",
                output_path=str(result.output_path) if result.output_path else "",
                status="completed" if result.ok else "failed",
                units=result.stats.get("units", 0),
                spaces=result.stats.get("spaces", 0),
            )
        )
        self.home_page.refresh()
        self.upload_page.refresh()
        self.result_page.show_result(result, self.pdf_path or "")
        self.stack.setCurrentWidget(self.result_page)

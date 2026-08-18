"""Application shell: frameless window with custom title bar, product tab
bar, and a QStackedWidget hosting the four pages. Owns shared state
(selected PDF, output folder, config, last Result) and all navigation.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QPixmap
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
from .resources import asset_path
from .pages.change_progress_page import ChangeProgressPage
from .pages.change_request_page import ChangeRequestPage
from .pages.change_review_page import ChangeReviewPage
from .pages.convert_page import ConvertPage
from .pages.failure_page import FailurePage
from .pages.home_page import HomePage
from .pages.result_page import ResultPage
from .pages.upload_page import UploadPage
from .recents import RecentEntry, RecentStore
from .widgets import label
from .worker import ChangeRequestWorker, ConvertWorker


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


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

        logo = QLabel()
        logo_file = asset_path("logo.png")
        if logo_file.is_file():
            logo.setPixmap(
                QPixmap(str(logo_file)).scaledToHeight(
                    26, Qt.SmoothTransformation
                )
            )
        lay.addWidget(logo)
        # same colour split as the "Mirage AEC" hero on the home page
        brand = QLabel(
            f'<span style="color:{theme.TEXT}">M</span>'
            f'<span style="color:{theme.BLUE}">AEC</span>'
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
        window = self._window
        if window.isMaximized():
            window.restore_from_maximized()
        else:
            window.remember_normal_geometry()
            window.showMaximized()

    def sync_maximize_icon(self) -> None:
        """Keep the glyph correct however the state changed (button, double
        click, Win+Up, Aero snap)."""
        self._max_btn.setText("❐" if self._window.isMaximized() else "□")

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
        self.change_xlsx_path: str = ""
        self._worker: ConvertWorker | None = None
        self._cancel_requested = False
        self._was_maximized = False
        self._normal_geometry = None
        self._tracking_suspended = False

        self.setWindowTitle("MAEC — HAPExt")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setMinimumSize(1120, 700)
        self.setStyleSheet(theme.APP_QSS)

        shell = QWidget()
        shell.setObjectName("Canvas")
        shell_lay = QVBoxLayout(shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)
        self.title_bar = TitleBar(self)
        shell_lay.addWidget(self.title_bar)
        shell_lay.addWidget(TabBar(on_hapext=self.go_home))

        self.stack = QStackedWidget()
        self.home_page = HomePage(self)
        self.upload_page = UploadPage(self)
        self.convert_page = ConvertPage(self)
        self.result_page = ResultPage(self)
        self.failure_page = FailurePage(self)
        self.change_request_page = ChangeRequestPage(self)
        self.change_progress_page = ChangeProgressPage(self)
        self.change_review_page = ChangeReviewPage(self)
        for page in (
            self.home_page,
            self.upload_page,
            self.convert_page,
            self.result_page,
            self.failure_page,
            self.change_request_page,
            self.change_progress_page,
            self.change_review_page,
        ):
            self.stack.addWidget(page)
        shell_lay.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

    # ------------------------------------------------------- native resize
    # Frameless windows lose Windows' resize machinery. Restoring it needs
    # three pieces (the standard custom-titlebar recipe):
    #   1. WS_THICKFRAME (+ min/max boxes) added to the native window style,
    #      or Windows will never show resize cursors / start the size loop;
    #   2. WM_NCCALCSIZE answered with "client = whole window" so the frame
    #      the style would draw stays invisible;
    #   3. WM_GETMINMAXINFO pinned to the monitor work area, so maximizing
    #      fills the screen exactly - without it Windows sizes a THICKFRAME
    #      window past the screen edges and the content is clipped;
    #   4. WM_NCHITTEST answered with the edge/corner codes.
    _RESIZE_BORDER = 8  # px, physical

    _WS_BITS = 0x00040000 | 0x00020000 | 0x00010000  # THICKFRAME|MINBOX|MAXBOX

    def _apply_native_style(self) -> None:
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_longlong
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_longlong
        user32.SetWindowLongPtrW.argtypes = [
            wintypes.HWND, ctypes.c_int, ctypes.c_longlong,
        ]
        hwnd = int(self.winId())
        style = user32.GetWindowLongPtrW(hwnd, -16)  # GWL_STYLE
        if (style & self._WS_BITS) != self._WS_BITS:  # any bit missing
            user32.SetWindowLongPtrW(hwnd, -16, style | self._WS_BITS)
            user32.SetWindowPos(  # SWP_FRAMECHANGED|NOMOVE|NOSIZE|NOZORDER|NOACTIVATE
                hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x2 | 0x1 | 0x4 | 0x10
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Qt re-applies its own frameless style during show; write ours after
        # the event loop settles, and re-assert lazily from nativeEvent.
        QTimer.singleShot(0, self._apply_native_style)

    def _fill_minmax_info(self, lparam: int) -> bool:
        """Answer WM_GETMINMAXINFO with both limits of the window.

        Two things are set here, and both must be, because answering this
        message stops Qt from applying its own limits to the native resize
        loop:

        * maximum - pinned to the monitor work area, so maximising fills the
          screen exactly instead of spilling past its edges;
        * minimum - dragging an edge is driven by Windows, which only honours
          ptMinTrackSize. Without it the window can be dragged down to a
          sliver regardless of Qt's setMinimumSize().
        """
        user32 = ctypes.windll.user32
        mmi = _MINMAXINFO.from_address(lparam)

        # minimum: Qt sizes are logical, ptMinTrackSize is physical pixels
        ratio = self.devicePixelRatioF()
        minimum = self.minimumSize()
        min_w = int(minimum.width() * ratio)
        min_h = int(minimum.height() * ratio)

        monitor = user32.MonitorFromWindow(int(self.winId()), 2)  # NEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            mmi.ptMinTrackSize.x, mmi.ptMinTrackSize.y = min_w, min_h
            return True
        work, screen = info.rcWork, info.rcMonitor
        work_w = work.right - work.left
        work_h = work.bottom - work.top

        # never demand more room than the screen has: on a small or heavily
        # scaled laptop our preferred minimum can exceed the work area, and
        # a window that cannot fit its own minimum is unusable
        mmi.ptMinTrackSize.x = min(min_w, work_w)
        mmi.ptMinTrackSize.y = min(min_h, work_h)

        mmi.ptMaxPosition.x = work.left - screen.left
        mmi.ptMaxPosition.y = work.top - screen.top
        mmi.ptMaxSize.x = work_w
        mmi.ptMaxSize.y = work_h
        mmi.ptMaxTrackSize.x = work_w
        mmi.ptMaxTrackSize.y = work_h
        return True

    def remember_normal_geometry(self) -> None:
        if self._tracking_suspended:
            return
        if not self.isMaximized() and not self.isMinimized():
            self._normal_geometry = self.geometry()

    def restore_from_maximized(self) -> None:
        """Put the window back to its pre-maximise size.

        After a minimise/restore round trip Qt's own stored "normal"
        geometry can be the maximised rect, so showNormal() alone leaves
        the window full-screen sized. The size we recorded is read *first*,
        because showNormal() emits a resize that would otherwise overwrite
        it with the maximised rect.
        """
        target = self._normal_geometry
        self._tracking_suspended = True
        self.showNormal()
        if target is not None:
            self.setGeometry(target)
        QTimer.singleShot(0, self._resume_geometry_tracking)

    def _resume_geometry_tracking(self) -> None:
        self._tracking_suspended = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.remember_normal_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.remember_normal_geometry()

    def changeEvent(self, event) -> None:
        """Keep maximise/restore honest across a minimise.

        Qt maximises a frameless window by resizing it to the work area, so
        Windows never marks it maximised. Coming back from the taskbar, Qt
        can hand back the maximised *geometry* while reporting "normal" -
        the restore button then maximises instead of restoring and the first
        click looks dead. Remembering the state ourselves fixes that.
        """
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        came_from_minimised = bool(event.oldState() & Qt.WindowMinimized)
        if self.isMinimized():
            pass  # keep whatever _was_maximized already holds
        elif came_from_minimised:
            if self._was_maximized and not self.isMaximized():
                QTimer.singleShot(0, self.showMaximized)
        else:
            self._was_maximized = self.isMaximized()
            self.remember_normal_geometry()
        self.title_bar.sync_maximize_icon()

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST: keep the style asserted
                self._apply_native_style()
            if msg.message == 0x0024:  # WM_GETMINMAXINFO
                if self._fill_minmax_info(msg.lParam):
                    return True, 0
            if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE
                # client area == whole window, maximized or not: the window
                # itself is already pinned to the work area above, so any
                # inset here would show as a dead border around the content
                return True, 0
            if msg.message == 0x0084 and not self.isMaximized():  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                rect = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(
                    int(self.winId()), ctypes.byref(rect)
                )
                b = self._RESIZE_BORDER
                left = x - rect.left <= b
                right = rect.right - x <= b
                top = y - rect.top <= b
                bottom = rect.bottom - y <= b
                if top and left:
                    return True, 13   # HTTOPLEFT
                if top and right:
                    return True, 14   # HTTOPRIGHT
                if bottom and left:
                    return True, 16   # HTBOTTOMLEFT
                if bottom and right:
                    return True, 17   # HTBOTTOMRIGHT
                if left:
                    return True, 10   # HTLEFT
                if right:
                    return True, 11   # HTRIGHT
                if top:
                    return True, 12   # HTTOP
                if bottom:
                    return True, 15   # HTBOTTOM
        return super().nativeEvent(event_type, message)

    # ---------------------------------------------------------- navigation
    def go_home(self) -> None:
        self.home_page.refresh()
        self.stack.setCurrentWidget(self.home_page)

    def go_upload(self) -> None:
        self.upload_page.refresh()
        self.stack.setCurrentWidget(self.upload_page)

    def go_change_request(self) -> None:
        self.change_request_page.refresh()
        self.stack.setCurrentWidget(self.change_request_page)

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

    def start_change_request(self, xlsx_path: str, pdf_path: str) -> None:
        """Append a revised PDF's new line items to an existing schedule."""
        if self._worker is not None:
            return
        self._cancel_requested = False
        self.change_xlsx_path = xlsx_path
        self.pdf_path = pdf_path
        self.change_progress_page.begin(xlsx_path, pdf_path)
        self.stack.setCurrentWidget(self.change_progress_page)

        self._worker = ChangeRequestWorker(
            xlsx_path, pdf_path, self.staging_dir(), self.config, parent=self
        )
        self._worker.progress.connect(self.change_progress_page.on_progress)
        self._worker.finished_result.connect(self._on_change_finished)
        self._worker.start()

    def _on_change_finished(self, result) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.wait()

        self.result = result
        if result.ok:
            self.change_progress_page.update_summary(result.stats)
            self.change_review_page.show_result(result, self.change_xlsx_path)
            self.stack.setCurrentWidget(self.change_review_page)
        else:
            self.failure_page.show_result(result, self.pdf_path or "", self.pdf_size)
            self.stack.setCurrentWidget(self.failure_page)

    def cancel_conversion(self) -> None:
        if self._worker is not None:
            self._cancel_requested = True
            self._worker.cancel()

    def _on_finished(self, result: Result) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.wait()

        self.result = result
        cancelled = self._cancel_requested or any(
            issue.field == "cancelled" for issue in result.issues
        )
        if not cancelled:  # cancelled runs are not history
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

        if result.ok:
            self.result_page.show_result(result, self.pdf_path or "")
            self.stack.setCurrentWidget(self.result_page)
        else:
            self.failure_page.show_result(result, self.pdf_path or "", self.pdf_size)
            self.stack.setCurrentWidget(self.failure_page)

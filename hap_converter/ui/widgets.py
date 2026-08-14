"""Shared UI building blocks used by the four pages."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .recents import RecentEntry, RecentStore


def card(object_name: str = "Card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    return frame


def label(text: str, object_name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    return lbl


def pdf_badge(size: int = 40) -> QLabel:
    badge = QLabel("PDF")
    badge.setObjectName("PdfBadge")
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(size, size)
    return badge


class InfoCard(QFrame):
    """Small static marketing card (Fast & Accurate / Secure / …)."""

    def __init__(self, title: str, body: str):
        super().__init__()
        self.setObjectName("InfoCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        lay.addWidget(label(title, "InfoCardTitle"))
        lay.addWidget(label(body, "InfoCardBody", wrap=True))


class DropZone(QFrame):
    """Dashed drag-and-drop area with a Browse button.

    Emits file_selected(path) for a dropped/browsed .pdf; shows an inline
    red hint for anything that is not a .pdf.
    """

    file_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumSize(300, 240)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 18)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        self._badge = pdf_badge(52)
        lay.addWidget(self._badge, 0, Qt.AlignHCenter)
        self._title = label("Drop your PDF here", "H2")
        self._title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title)
        self._sub = label("or", "Muted")
        self._sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._sub)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("Secondary")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.browse_btn, 0, Qt.AlignHCenter)

        self._hint = label("*Upload only .pdf", "Small")
        self._hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._hint)

    # -- states -----------------------------------------------------------
    def _set_state(self, active: bool = False, error: bool = False) -> None:
        self.setProperty("dropActive", "true" if active else "false")
        self.setProperty("dropError", "true" if error else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def show_file(self, path: str, pages: int, size_bytes: int) -> None:
        mb = size_bytes / (1024 * 1024)
        self._title.setText(Path(path).name)
        self._sub.setText(f"{mb:.1f} MB • {pages} pages")
        self._hint.setText("Drop another PDF to replace")
        self._set_state()

    def show_error(self, message: str) -> None:
        self._hint.setText(message)
        self._set_state(error=True)

    def reset(self) -> None:
        self._title.setText("Drop your PDF here")
        self._sub.setText("or")
        self._hint.setText("*Upload only .pdf")
        self._set_state()

    # -- drag & drop ------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(".pdf"):
            self._set_state(active=True)
            event.acceptProposedAction()
        else:
            self._set_state(error=True)

    def dragLeaveEvent(self, event) -> None:
        self._set_state()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_state()
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.lower().endswith(".pdf"):
            self.file_selected.emit(path)
        else:
            self.show_error("Only .pdf files are accepted")


class StepTimeline(QWidget):
    """Vertical 3-step timeline for the Conversion Status panel.

    Supports a failure state: the failed step gets a red ✕ dot and a red
    "Failed – …" caption beneath its label (per the Figma failure design).
    """

    def __init__(self, steps: list[str]):
        super().__init__()
        self._dots: list[QLabel] = []
        self._captions: list[QLabel] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        for i, text in enumerate(steps):
            if i:  # connector line between stages (centered under the dots)
                conn_row = QHBoxLayout()
                conn_row.setContentsMargins(10, 0, 0, 0)
                connector = QFrame()
                connector.setObjectName("StepConnector")
                conn_row.addWidget(connector)
                conn_row.addStretch(1)
                lay.addLayout(conn_row)
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = QLabel(str(i + 1))
            dot.setObjectName("StepDotPending")
            dot.setAlignment(Qt.AlignCenter)
            self._dots.append(dot)
            row.addWidget(dot, 0, Qt.AlignTop)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.addWidget(label(text, "H2"))
            caption = label("", "StepCaption")
            caption.hide()
            self._captions.append(caption)
            text_col.addWidget(caption)
            row.addLayout(text_col, 1)
            lay.addLayout(row)

    def _apply(self, dot: QLabel, name: str, text: str) -> None:
        dot.setObjectName(name)
        dot.setText(text)
        dot.style().unpolish(dot)
        dot.style().polish(dot)

    def set_step(self, current: int) -> None:
        """Steps below `current` are done, `current` is active (1-based)."""
        for i, dot in enumerate(self._dots, start=1):
            done = i < current
            active = i == current
            self._apply(
                dot,
                "StepDotDone" if (done or active) else "StepDotPending",
                "✓" if done else str(i),
            )
            self._captions[i - 1].hide()

    def set_failed(self, failed_step: int, caption: str) -> None:
        """Steps before `failed_step` are done; `failed_step` shows a red ✕
        with a caption; later steps stay pending (1-based)."""
        for i, dot in enumerate(self._dots, start=1):
            if i < failed_step:
                self._apply(dot, "StepDotDone", "✓")
            elif i == failed_step:
                self._apply(dot, "StepDotFail", "✕")
            else:
                self._apply(dot, "StepDotPending", str(i))
            self._captions[i - 1].setVisible(i == failed_step and bool(caption))
        self._captions[failed_step - 1].setText(caption)


class RecentProjectsPanel(QFrame):
    """Recent Projects list; shared by Home and Upload pages."""

    open_requested = Signal(object)  # RecentEntry

    def __init__(self, store: RecentStore, title: str = "Recent Projects"):
        super().__init__()
        self.setObjectName("PanelCard")
        self._store = store
        self._expanded = False

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(18, 16, 18, 16)
        self._lay.setSpacing(6)

        head = QHBoxLayout()
        head.addWidget(label(title, "H2"))
        head.addStretch(1)
        self._view_all = QPushButton("View All")
        self._view_all.setObjectName("Ghost")
        self._view_all.setCursor(Qt.PointingHandCursor)
        self._view_all.clicked.connect(self._toggle_expand)
        head.addWidget(self._view_all)
        self._lay.addLayout(head)

        self._items_box = QVBoxLayout()
        self._items_box.setSpacing(2)
        self._lay.addLayout(self._items_box)
        self._lay.addStretch(1)
        self.refresh()

    def _toggle_expand(self) -> None:
        self._expanded = not self._expanded
        self._view_all.setText("Show Less" if self._expanded else "View All")
        self.refresh()

    def refresh(self) -> None:
        while self._items_box.count():
            item = self._items_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = self._store.entries if self._expanded else self._store.top(5)
        if not entries:
            empty = label("No recent projects yet", "Muted")
            empty.setAlignment(Qt.AlignCenter)
            self._items_box.addWidget(empty)
            return
        for entry in entries:
            self._items_box.addWidget(self._make_item(entry))

    def _make_item(self, entry: RecentEntry) -> QWidget:
        row = QFrame()
        row.setObjectName("RecentItem")
        row.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 8, 4, 8)
        lay.setSpacing(10)
        lay.addWidget(pdf_badge(34))

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(label(Path(entry.pdf_path).name, "RecentName"))
        when = entry.timestamp.replace("T", " • ") if entry.timestamp else ""
        text_col.addWidget(label(when, "Small"))
        lay.addLayout(text_col, 1)

        kebab = QToolButton()
        kebab.setText("⋯")
        kebab.setCursor(Qt.PointingHandCursor)
        kebab.setStyleSheet("QToolButton { border: none; font-weight: 800; }")
        kebab.clicked.connect(lambda: self._show_menu(kebab, entry))
        lay.addWidget(kebab)

        row.mousePressEvent = lambda e, en=entry: self.open_requested.emit(en)
        return row

    def _show_menu(self, anchor: QWidget, entry: RecentEntry) -> None:
        menu = QMenu(self)
        act_open = menu.addAction("Open CSV")
        act_open.setEnabled(bool(entry.output_path) and Path(entry.output_path).is_file())
        act_show = menu.addAction("Show in folder")
        menu.addSeparator()
        act_remove = menu.addAction("Remove from list")
        chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        if chosen is act_open:
            os.startfile(entry.output_path)  # noqa: S606 - local file open
        elif chosen is act_show:
            target = entry.output_path or entry.pdf_path
            if Path(target).exists():
                subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
        elif chosen is act_remove:
            self._store.remove(entry.pdf_path)
            self.refresh()


class PreviewTable(QTableWidget):
    """Read-only preview of the first CSV records; blanks shown as em-dash."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.verticalHeader().setVisible(False)
        self.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def load(self, header: list[str], rows: list[list[str]]) -> None:
        self.clear()
        self.setColumnCount(len(header))
        self.setHorizontalHeaderLabels(header)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value if value else "—")
                if not value:
                    item.setForeground(Qt.gray)
                self.setItem(r, c, item)
        self.resizeColumnsToContents()

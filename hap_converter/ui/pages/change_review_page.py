"""Change Request — review screen
(mockup: HAP_change_request/final updated excel.png).

Shows the updated schedule with newly appended rows highlighted, a
before/after summary strip, and Approve & Download.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import openpyxl
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...engine.change_request import FIRST_DATA_ROW, HEADER_ROW
from ..widgets import PreviewTable, card, label

NEW_ROW_TINT = QColor("#E9F3DA")
PREVIEW_LIMIT = 40
CONTEXT_ROWS = 6   # existing rows shown above the first appended row


class ChangeReviewPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        body = card()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 18, 24, 18)
        body_lay.setSpacing(12)

        # radios sit inside the card on every page
        radios = QHBoxLayout()
        new_project = QRadioButton("New Project")
        new_project.setCursor(Qt.PointingHandCursor)
        new_project.clicked.connect(self._ctx.go_upload)
        self.change_request_radio = QRadioButton("Change Request")
        self.change_request_radio.setCursor(Qt.PointingHandCursor)
        self.change_request_radio.setChecked(True)
        radios.addWidget(new_project)
        radios.addSpacing(30)
        radios.addWidget(self.change_request_radio)
        radios.addStretch(1)
        body_lay.addLayout(radios)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(label("Review Changes", "FailTitle"))
        self.pill = QLabel("")
        self.pill.setObjectName("Chip")
        head.addWidget(self.pill)
        head.addStretch(1)
        reprocess = QPushButton("Re-process")
        reprocess.setObjectName("Secondary")
        reprocess.setCursor(Qt.PointingHandCursor)
        reprocess.clicked.connect(self._ctx.go_change_request)
        head.addWidget(reprocess)
        self.download_btn = QPushButton("Approve && Download")  # && renders one literal &
        self.download_btn.setObjectName("Primary")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self._download)
        head.addWidget(self.download_btn)
        body_lay.addLayout(head)

        self.subtitle = label("", "Small")
        body_lay.addWidget(self.subtitle)

        strip = QFrame()
        strip.setObjectName("SummaryStrip")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(18, 10, 18, 10)
        strip_lay.setSpacing(34)
        self._summary: dict[str, QLabel] = {}
        for key in ("PREVIOUS", "NEW", "UPDATED FILE", "CHANGE RULE"):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(key, "SummaryKey"))
            value = label("—", "SummaryVal")
            self._summary[key] = value
            col.addWidget(value)
            strip_lay.addLayout(col)
        strip_lay.addStretch(1)
        body_lay.addWidget(strip)

        self.sheet_tab = label("HAP Zone Sizing Summary", "SheetTab")
        body_lay.addWidget(self.sheet_tab, 0, Qt.AlignLeft)

        self.preview = PreviewTable()
        body_lay.addWidget(self.preview, 1)

        foot = QHBoxLayout()
        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(
            f"background: {NEW_ROW_TINT.name()}; border: 1px solid #C9D9AE; border-radius: 3px;"
        )
        foot.addWidget(swatch)
        self.foot_note = label("Highlighted rows = newly appended line items", "Small")
        foot.addWidget(self.foot_note)
        foot.addStretch(1)
        self.download_btn2 = QPushButton("Approve && Download")  # && renders one literal &
        self.download_btn2.setObjectName("Primary")
        self.download_btn2.setCursor(Qt.PointingHandCursor)
        self.download_btn2.clicked.connect(self._download)
        foot.addWidget(self.download_btn2)
        body_lay.addLayout(foot)

        root.addWidget(body, 1)

    # -------------------------------------------------------------- state
    def show_result(self, result, xlsx_path: str) -> None:
        self._result = result
        stats = result.stats
        existing = stats.get("existing_rows", 0)
        new_rows = stats.get("new_rows", 0)
        total = stats.get("total_rows", 0)
        columns = stats.get("columns", 14)

        self.pill.setText(f"{new_rows} NEW ITEMS")
        self.subtitle.setText(
            f"{Path(xlsx_path).name} • New line items are appended to the end and highlighted"
        )
        self._summary["PREVIOUS"].setText(f"{existing} rows")
        self._summary["NEW"].setText(f"{new_rows} rows")
        self._summary["UPDATED FILE"].setText(f"{total} rows • {columns} columns")
        self._summary["CHANGE RULE"].setText("Append only • No existing rows changed")

        header, rows, first_new = self._read_workbook(result.output_path, existing)
        self.preview.load(header, rows)
        self._tint_new_rows(len(rows), first_new)
        shown = len(rows)
        self.foot_note.setText(
            f"Highlighted rows = newly appended line items    "
            f"(showing {shown} of {total} rows)"
        )

    @staticmethod
    def _read_workbook(path: Path, existing_rows: int) -> tuple[list[str], list[list[str]], int]:
        """Header + a window of rows ending with the appended ones."""
        sheet = openpyxl.load_workbook(path, data_only=True).active
        header = [
            "" if c.value is None else str(c.value)
            for c in sheet[HEADER_ROW][:14]
        ]
        all_rows = []
        for row in sheet.iter_rows(min_row=FIRST_DATA_ROW, max_col=14):
            values = ["" if c.value is None else str(c.value) for c in row]
            if any(v.strip() for v in values):
                all_rows.append(values)
        # window the preview on the boundary: a few existing rows for context,
        # then the appended ones, so the change is visible at a glance
        start = max(0, existing_rows - CONTEXT_ROWS)
        window = all_rows[start : start + PREVIEW_LIMIT]
        return header, window, max(0, existing_rows - start)

    def _tint_new_rows(self, row_count: int, first_new: int) -> None:
        for r in range(first_new, row_count):
            for c in range(self.preview.columnCount()):
                item = self.preview.item(r, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.preview.setItem(r, c, item)
                item.setBackground(NEW_ROW_TINT)

    def _download(self) -> None:
        if not (self._result and self._result.output_path):
            return
        src = Path(self._result.output_path)
        downloads = Path.home() / "Downloads"
        start_dir = downloads if downloads.is_dir() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "Save updated schedule as", str(start_dir / src.name),
            "Excel Workbook (*.xlsx)",
        )
        if not target:
            return
        if not target.lower().endswith(".xlsx"):
            target += ".xlsx"
        try:
            shutil.copyfile(src, target)
            QMessageBox.information(self, "Saved", f"Updated schedule saved to:\n{target}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

"""Page 4 — Result: CSV preview on success, issue list on validation
failure — same page, two states
(mockup: normal scenario/final output screen.png).
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...engine.pipeline import Result
from ..widgets import PreviewTable, card, label

PREVIEW_ROWS = 4


class ResultPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._result: Result | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)

        body_card = card()
        body = QVBoxLayout(body_card)
        body.setContentsMargins(24, 18, 24, 18)
        body.setSpacing(12)

        # ---------------- header row
        head = QHBoxLayout()
        head.setSpacing(12)
        self.title_label = label("CSV Preview", "H2")
        head.addWidget(self.title_label)
        self.pill = QLabel("COMPLETED")
        self.pill.setObjectName("PillOk")
        head.addWidget(self.pill)
        head.addStretch(1)
        self.home_btn = QPushButton("Home")
        self.home_btn.setObjectName("Secondary")
        self.home_btn.setCursor(Qt.PointingHandCursor)
        self.home_btn.clicked.connect(self._ctx.go_home)
        head.addWidget(self.home_btn)
        self.try_another_btn = QPushButton("Convert another PDF")
        self.try_another_btn.setObjectName("Secondary")
        self.try_another_btn.setCursor(Qt.PointingHandCursor)
        self.try_another_btn.clicked.connect(self._ctx.go_upload)
        head.addWidget(self.try_another_btn)
        self.reprocess_btn = QPushButton("Re-process")
        self.reprocess_btn.setObjectName("Secondary")
        self.reprocess_btn.setCursor(Qt.PointingHandCursor)
        self.reprocess_btn.clicked.connect(self._ctx.start_conversion)
        head.addWidget(self.reprocess_btn)
        self.download_btn = QPushButton("Download CSV")
        self.download_btn.setObjectName("Primary")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self._download)
        head.addWidget(self.download_btn)
        body.addLayout(head)

        self.breadcrumb = label("", "Small")
        body.addWidget(self.breadcrumb)

        # ---------------- summary strip
        strip = QFrame()
        strip.setObjectName("SummaryStrip")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(18, 10, 18, 10)
        strip_lay.setSpacing(30)
        self._summary_values: dict[str, QLabel] = {}
        self._summary_keys: dict[str, QLabel] = {}
        for key in ("FILE", "ROWS", "COLUMNS", "SOURCE", "STATUS"):
            col = QVBoxLayout()
            col.setSpacing(2)
            key_lbl = label(key, "SummaryKey")
            self._summary_keys[key] = key_lbl
            col.addWidget(key_lbl)
            value = label("—", "SummaryVal")
            self._summary_values[key] = value
            col.addWidget(value)
            strip_lay.addLayout(col)
        strip_lay.addStretch(1)
        body.addWidget(strip)

        # ---------------- sheet tab + preview / issues
        self.sheet_tab = label("HAP Zone Sizing Summary", "SheetTab")
        body.addWidget(self.sheet_tab, 0, Qt.AlignLeft)

        self.preview = PreviewTable()
        body.addWidget(self.preview, 1)

        # failure state: headline + scrollable rich issue rows
        self.issues_panel = QWidget()
        issues_lay = QVBoxLayout(self.issues_panel)
        issues_lay.setContentsMargins(0, 0, 0, 0)
        issues_lay.setSpacing(8)
        self.issues_headline = label("", "H2")
        issues_lay.addWidget(self.issues_headline)
        self.issues_scroll = QScrollArea()
        self.issues_scroll.setWidgetResizable(True)
        self.issues_rows_host = QWidget()
        self.issues_rows_lay = QVBoxLayout(self.issues_rows_host)
        self.issues_rows_lay.setContentsMargins(0, 0, 8, 0)
        self.issues_rows_lay.setSpacing(6)
        self.issues_rows_lay.addStretch(1)
        self.issues_scroll.setWidget(self.issues_rows_host)
        issues_lay.addWidget(self.issues_scroll, 1)
        self.issues_panel.hide()
        body.addWidget(self.issues_panel, 1)

        # ---------------- footer
        foot = QHBoxLayout()
        foot_col = QVBoxLayout()
        foot_col.setSpacing(2)
        self.foot_line1 = label("", "Small")
        self.foot_line2 = label("", "Small")
        foot_col.addWidget(self.foot_line1)
        foot_col.addWidget(self.foot_line2)
        foot.addLayout(foot_col)
        foot.addStretch(1)
        self.download_btn2 = QPushButton("Download CSV")
        self.download_btn2.setObjectName("Primary")
        self.download_btn2.setCursor(Qt.PointingHandCursor)
        self.download_btn2.clicked.connect(self._download)
        foot.addWidget(self.download_btn2)
        body.addLayout(foot)

        root.addWidget(body_card, 1)

    # ------------------------------------------------------------- states
    def show_result(self, result: Result, pdf_path: str) -> None:
        self._result = result
        if result.ok:
            self._show_success(result, pdf_path)
        else:
            self._show_failure(result, pdf_path)

    def _show_success(self, result: Result, pdf_path: str) -> None:
        self.title_label.setText("CSV Preview")
        self.pill.setText("COMPLETED")
        self.pill.setObjectName("PillOk")
        self._repolish(self.pill)
        self.try_another_btn.setText("Convert another PDF")
        self.download_btn.show()
        self.download_btn2.show()
        self.sheet_tab.show()
        self.issues_panel.hide()
        self.preview.show()

        out = result.output_path
        self.breadcrumb.setText(f"{Path(pdf_path).name}  →  {out.name}")

        header, rows = self._read_csv_head(out, PREVIEW_ROWS)
        self.preview.load(header, rows)

        total_rows = result.stats.get("rows", 0)
        self._summary_keys["COLUMNS"].setText("COLUMNS")
        self._set_summary(
            FILE=out.name,
            ROWS=str(total_rows),
            COLUMNS=str(len(header)),
            SOURCE=Path(pdf_path).name,
            STATUS=("Ready for review", "StatusOk"),
        )
        self.foot_line1.setText(
            f"Previewing the first {min(PREVIEW_ROWS, total_rows)} records from the converted schedule."
        )
        self.foot_line2.setText(
            f"{len(header)} extracted columns • {total_rows} records • "
            "Review the extracted HAP schedule before downloading."
        )

    def _show_failure(self, result: Result, pdf_path: str) -> None:
        self.title_label.setText("Export blocked")
        self.pill.setText("FAILED")
        self.pill.setObjectName("PillFail")
        self._repolish(self.pill)
        self.try_another_btn.setText("Try another PDF")
        self.download_btn.hide()
        self.download_btn2.hide()
        self.sheet_tab.hide()
        self.preview.hide()
        self.issues_panel.show()

        self.breadcrumb.setText(f"{Path(pdf_path).name}  →  nothing exported")

        issues = sorted(result.issues, key=lambda i: i.page)
        n = len(issues)
        self.issues_headline.setText(
            f"{n} problem{'s' if n != 1 else ''} found — fix the HAP report and re-process:"
        )
        # rebuild the rich rows (badge: page, bold field, wrapped description)
        while self.issues_rows_lay.count() > 1:  # keep the trailing stretch
            item = self.issues_rows_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for issue in issues:
            self.issues_rows_lay.insertWidget(
                self.issues_rows_lay.count() - 1, self._issue_row(issue)
            )
        self._summary_keys["COLUMNS"].setText("ISSUES")
        self._set_summary(
            FILE="—",
            ROWS="—",
            COLUMNS=str(len(result.issues)),
            SOURCE=Path(pdf_path).name,
            STATUS=("Validation failed — nothing exported", "StatusFail"),
        )
        self.foot_line1.setText(
            "The PDF is missing mandatory values (all-or-nothing validation)."
        )
        self.foot_line2.setText(
            "Fix the HAP report and re-process, or try another PDF."
        )

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _issue_row(issue) -> QFrame:
        row = QFrame()
        row.setObjectName("IssueRowFrame")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)
        badge_text = f"Page {issue.page}" if issue.page else "File"
        badge = QLabel(badge_text)
        badge.setObjectName("IssueBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(70)
        lay.addWidget(badge, 0, Qt.AlignTop)
        text = QLabel(f"<b>{issue.field}</b> — {issue.description}")
        text.setObjectName("IssueText")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        lay.addWidget(text, 1)
        return row

    def _set_summary(self, **values) -> None:
        for key, value in values.items():
            lbl = self._summary_values[key]
            if isinstance(value, tuple):
                text, style = value
                lbl.setText(text)
                lbl.setObjectName(style)
                self._repolish(lbl)
            else:
                lbl.setText(value)
                lbl.setObjectName("SummaryVal")
                self._repolish(lbl)

    @staticmethod
    def _repolish(widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    @staticmethod
    def _read_csv_head(path: Path, n: int) -> tuple[list[str], list[list[str]]]:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) >= n:
                    break
        return header, rows

    def _download(self) -> None:
        if not (self._result and self._result.ok and self._result.output_path):
            return
        src = self._result.output_path
        target, _ = QFileDialog.getSaveFileName(
            self, "Save CSV as", str(Path.home() / src.name), "CSV files (*.csv)"
        )
        if not target:
            return
        try:
            shutil.copyfile(src, target)
            QMessageBox.information(self, "Saved", f"CSV saved to:\n{target}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

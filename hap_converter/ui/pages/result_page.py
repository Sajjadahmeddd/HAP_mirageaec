"""Page 4 — Result: CSV preview on success, issue list on validation
failure — same page, two states
(mockup: normal scenario/final output screen.png).
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...engine.pipeline import Result
from ...engine.synthesizer import build_project_header
from ...engine.xlsx_exporter import write_fcu_xlsx
from ..project_details_dialog import ProjectDetailsDialog
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
        self.details_btn = QPushButton("Project Details")
        self.details_btn.setObjectName("Secondary")
        self.details_btn.setCursor(Qt.PointingHandCursor)
        self.details_btn.setToolTip(
            "Enter the 8 project details that head the downloaded CSV (mandatory)"
        )
        self.details_btn.clicked.connect(self._edit_details)
        head.addWidget(self.details_btn)
        self.download_btn = QPushButton("Download")
        self.download_btn.setObjectName("Primary")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setToolTip("Save as Excel (.xlsx, template layout) or CSV")
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
        self.download_btn2 = QPushButton("Download")
        self.download_btn2.setObjectName("Primary")
        self.download_btn2.setCursor(Qt.PointingHandCursor)
        self.download_btn2.clicked.connect(self._download)
        foot.addWidget(self.download_btn2)
        body.addLayout(foot)

        root.addWidget(body_card, 1)

    # ------------------------------------------------------------- states
    def show_result(self, result: Result, pdf_path: str) -> None:
        """Success only — failures are routed to FailurePage by the shell."""
        self._result = result
        self._show_success(result, pdf_path)

    def _show_success(self, result: Result, pdf_path: str) -> None:
        self.title_label.setText("CSV Preview")
        self.pill.setText("COMPLETED")
        self.pill.setObjectName("PillOk")
        self._repolish(self.pill)
        self.try_another_btn.setText("Convert another PDF")
        self._refresh_details_btn()

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

    # ------------------------------------------------------------- helpers
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

    def _refresh_details_btn(self) -> None:
        filled = bool(getattr(self._ctx, "project_details", None))
        self.details_btn.setText("Project Details ✓" if filled else "Project Details")

    def _edit_details(self) -> bool:
        dialog = ProjectDetailsDialog(
            self, initial=getattr(self._ctx, "project_details", None)
        )
        if dialog.exec() != ProjectDetailsDialog.Accepted:
            return False
        self._ctx.project_details = dialog.details()
        self._refresh_details_btn()
        return True

    def _download(self) -> None:
        if not (self._result and self._result.ok and self._result.output_path):
            return
        # the 8 project details are mandatory before download
        if not getattr(self._ctx, "project_details", None) and not self._edit_details():
            return
        src = self._result.output_path
        downloads = Path.home() / "Downloads"
        start_dir = downloads if downloads.is_dir() else Path.home()
        target, chosen_filter = QFileDialog.getSaveFileName(
            self,
            "Save as",
            str(start_dir / (src.stem + ".xlsx")),
            "Excel Workbook (*.xlsx);;CSV file (*.csv)",
        )
        if not target:
            return
        as_csv = target.lower().endswith(".csv") or (
            "CSV" in chosen_filter and not target.lower().endswith(".xlsx")
        )
        try:
            details = self._ctx.project_details
            with open(src, encoding="utf-8-sig", newline="") as handle:
                all_rows = list(csv.reader(handle))
            column_header, data_rows = all_rows[0], all_rows[1:]
            if as_csv:
                if not target.lower().endswith(".csv"):
                    target += ".csv"
                header_rows = build_project_header(details)
                with open(target, "w", encoding="utf-8-sig", newline="") as handle:
                    csv.writer(handle).writerows(header_rows + all_rows)
            else:
                if not target.lower().endswith(".xlsx"):
                    target += ".xlsx"
                write_fcu_xlsx(details, column_header, data_rows, target)
            QMessageBox.information(self, "Saved", f"Saved to:\n{target}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

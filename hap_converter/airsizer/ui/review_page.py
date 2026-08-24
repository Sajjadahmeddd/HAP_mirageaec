"""Steps 3-4 — Review Results and Project Summary
(Figma: "review results, new output LSM column and air outlet length column",
"project summary page").

One page, two stages. Stage 3 is the roll-up the engineer checks, with a
column picker over the preview and a Preview button back into each sizing.
Generate Excel writes the file (auto-versioned, visible columns only) and
moves to stage 4, where Download Excel saves it wherever they want.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine import export, pipeline
from .widgets import ColumnPicker, StepChips, card, label
from .wizard_page import FAILED_TINT, INTERPOLATED_TINT, SIZED_TINT, STEPS


class ReviewPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._stage = 3
        self._generated: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)

        root.addWidget(label("Air Diffuser Sizing", "H2"))
        root.addWidget(
            label(
                "Select a diffuser from the catalog. Available sizing options will "
                "update automatically.",
                "Small",
            )
        )
        self.steps = StepChips(STEPS)
        root.addWidget(self.steps)

        body = card()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(18, 16, 18, 16)
        body_lay.setSpacing(10)

        self.summary = QFrame()
        self.summary.setObjectName("SummaryStrip")
        summary_lay = QHBoxLayout(self.summary)
        summary_lay.setContentsMargins(18, 10, 18, 10)
        summary_lay.setSpacing(30)
        self._summary_values: dict[str, QLabel] = {}
        for key in ("FILE", "ROWS", "COLUMNS", "SIZED", "STATUS"):
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(label(key, "SummaryKey"))
            value = label("—", "SummaryVal")
            self._summary_values[key] = value
            column.addWidget(value)
            summary_lay.addLayout(column)
        summary_lay.addStretch(1)
        self.summary.hide()
        body_lay.addWidget(self.summary)

        picker_row = QHBoxLayout()
        picker_row.addWidget(label("HAP Air Diffuser Schedule", "SheetTab"))
        picker_row.addStretch(1)
        self.picker: ColumnPicker | None = None
        self._picker_row = picker_row
        body_lay.addLayout(picker_row)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.verticalHeader().setVisible(False)
        body_lay.addWidget(self.table, 1)

        self.note = label("", "Small")
        body_lay.addWidget(self.note)
        root.addWidget(body, 1)

        footer = QHBoxLayout()
        self.back_btn = QPushButton("Back to sizing")
        self.back_btn.setObjectName("Secondary")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._ctx.go_air_wizard)
        footer.addWidget(self.back_btn)
        footer.addStretch(1)
        self.action_btn = QPushButton("Generate Excel")
        self.action_btn.setObjectName("Primary")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action)
        footer.addWidget(self.action_btn)
        root.addLayout(footer)

    # --------------------------------------------------------------- staging
    def set_stage(self, stage: int) -> None:
        self._stage = stage
        self.steps.set_step(stage)
        self.action_btn.setText("Generate Excel" if stage == 3 else "Download Excel")
        self.summary.setVisible(stage == 4)
        self.refresh()

    def _ensure_picker(self) -> ColumnPicker:
        if self.picker is None:
            self.picker = ColumnPicker(
                self._ctx.air_config.result_columns, self._ctx.air_visible_columns
            )
            self.picker.changed.connect(self._on_columns_changed)
            self._picker_row.addWidget(self.picker)
        return self.picker

    def _on_columns_changed(self, keys: list[str]) -> None:
        self._ctx.air_visible_columns = keys
        self.refresh()

    # ------------------------------------------------------------- rendering
    def refresh(self) -> None:
        config = self._ctx.air_config
        if config is None:
            return
        self._ensure_picker()

        columns = export.visible_columns(config, self._ctx.air_visible_columns)
        spaces = self._ctx.air_spaces
        header, rows = export.build_rows(
            spaces, self._ctx.air_inputs, self._ctx.air_results, config, columns
        )

        show_actions = self._stage == 3
        total_columns = len(header) + (1 if show_actions else 0)
        self.table.setColumnCount(total_columns)
        self.table.setHorizontalHeaderLabels(header + (["Sizing"] if show_actions else []))
        self.table.setRowCount(len(rows))

        bold = QFont()
        bold.setBold(True)
        for index, (space, values) in enumerate(zip(spaces, rows)):
            state = export.row_state(space, self._ctx.air_results.get(space.row))
            tint = {
                "ok": SIZED_TINT,
                "interpolated": INTERPOLATED_TINT,
                "failed": FAILED_TINT,
            }.get(state)

            for column, value in enumerate(values):
                shown = value if value else ("" if space.is_unit else "—")
                if column == 0 and not space.is_unit:
                    shown = "      " + value
                item = QTableWidgetItem(shown)
                if space.is_unit:
                    item.setFont(bold)
                elif not value:
                    item.setForeground(Qt.gray)
                if tint is not None:
                    item.setBackground(tint)
                self.table.setItem(index, column, item)

            if show_actions:
                self.table.removeCellWidget(index, len(header))
                if pipeline.sizable(space):
                    self.table.setCellWidget(index, len(header), self._preview_cell(space.row))
                else:
                    blank = QTableWidgetItem("")
                    if tint is not None:
                        blank.setBackground(tint)
                    self.table.setItem(index, len(header), blank)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        if show_actions:
            self.table.setColumnWidth(len(header), 120)

        sized = sum(1 for r in self._ctx.air_results.values() if r.ok)
        failed = sum(1 for r in self._ctx.air_results.values() if not r.ok)
        interpolated = sum(1 for r in self._ctx.air_results.values() if r.ok and r.interpolated)
        self.action_btn.setEnabled(sized > 0)

        notes = [f"{len(rows)} rows • {len(header)} columns • {sized} sized"]
        if interpolated:
            notes.append(f"{interpolated} interpolated (amber)")
        if failed:
            notes.append(f"{failed} with no valid selection (red)")
        self.note.setText("    ".join(notes))

        self._summary_values["ROWS"].setText(str(len(rows)))
        self._summary_values["COLUMNS"].setText(str(len(header)))
        self._summary_values["SIZED"].setText(str(sized))
        if self._generated:
            self._summary_values["FILE"].setText(self._generated.name)
            self._summary_values["STATUS"].setText("Ready to download")

    def _preview_cell(self, row: int) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(6, 3, 6, 3)
        button = QPushButton("Preview")
        button.setObjectName("RowAction")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, r=row: self._ctx.open_air_sizing(r))
        lay.addWidget(button)
        return holder

    # --------------------------------------------------------------- actions
    def _on_action(self) -> None:
        if self._stage == 3:
            self._generate()
        else:
            self._download()

    def _generate(self) -> None:
        config = self._ctx.air_config
        columns = export.visible_columns(config, self._ctx.air_visible_columns)
        base = Path(self._ctx.air_source_path).stem or "air_diffuser_sizing"
        try:
            self._generated = export.write_xlsx(
                self._ctx.air_spaces,
                self._ctx.air_inputs,
                self._ctx.air_results,
                config,
                columns,
                self._ctx.air_staging_dir(),
                f"{base} - sized",
                self._ctx.air_project.name,
            )
        except OSError as exc:
            QMessageBox.critical(self, "Could not generate", str(exc))
            return
        self.set_stage(4)

    def _download(self) -> None:
        if not self._generated or not self._generated.is_file():
            self._generate()
            if not self._generated:
                return
        downloads = Path.home() / "Downloads"
        start = downloads if downloads.is_dir() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save sized schedule as",
            str(start / self._generated.name),
            "Excel Workbook (*.xlsx)",
        )
        if not target:
            return
        if not target.lower().endswith(".xlsx"):
            target += ".xlsx"
        try:
            shutil.copyfile(self._generated, target)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Saved", f"Sized schedule saved to:\n{target}")

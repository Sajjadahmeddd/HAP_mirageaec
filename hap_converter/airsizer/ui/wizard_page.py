"""Steps 1-2 — the schedule table with a Sizing action per subspace
(Figma: "after loading the excel sheet", "after calculating the sizing for
subspace, preview button page").

Unit header rows are shown for context but are not sized; every subspace row
gets a button that opens the sizing panel. Once a subspace has been sized the
button reads Preview and re-opens the panel with its saved inputs.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine import pipeline
from .sizing_dialog import SizingDialog
from .widgets import StepChips, card, label

STEPS = ["Select Diffuser Type", "Configure Parameters", "Review Results", "Project Summary"]

COLUMNS = [
    ("name", "Zone Name / Space Name", 300),
    ("floor_area", "Floor Area (m²)", 120),
    ("total_coil", "Total Coil Load (KW)", 150),
    ("sens_coil", "Sens Coil Load (KW)", 150),
    ("air_flow", "Air Flow (L/s)", 120),
]

SIZED_TINT = QColor("#EDF2DC")
FAILED_TINT = QColor("#FDEDED")
INTERPOLATED_TINT = QColor("#FBEFD3")


class WizardPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

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

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnCount(len(COLUMNS) + 1)
        self.table.setHorizontalHeaderLabels([c[1] for c in COLUMNS] + ["Sizing"])
        body_lay.addWidget(self.table, 1)

        self.tip = label(
            "Tip: Select the exact catalog type first to unlock its controls.", "Small"
        )
        body_lay.addWidget(self.tip)
        root.addWidget(body, 1)

        footer = QHBoxLayout()
        self.source_label = label("", "Small")
        footer.addWidget(self.source_label)
        footer.addStretch(1)
        self.save_project_btn = QPushButton("Save Project")
        self.save_project_btn.setObjectName("Secondary")
        self.save_project_btn.setCursor(Qt.PointingHandCursor)
        self.save_project_btn.clicked.connect(self._ctx.save_air_project)
        footer.addWidget(self.save_project_btn)
        self.generate_btn = QPushButton("Generate Excel")
        self.generate_btn.setObjectName("Primary")
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.setToolTip("Review the sized schedule before exporting")
        self.generate_btn.clicked.connect(self._ctx.go_air_review)
        footer.addWidget(self.generate_btn)
        root.addLayout(footer)

    # ------------------------------------------------------------- rendering
    def refresh(self) -> None:
        spaces = self._ctx.air_spaces
        results = self._ctx.air_results
        self.table.setRowCount(len(spaces))

        bold = QFont()
        bold.setBold(True)
        for index, space in enumerate(spaces):
            values = [
                space.name, space.floor_area, space.total_coil,
                space.sens_coil, space.air_flow,
            ]
            result = results.get(space.row)
            tint = None
            if not space.is_unit and result is not None:
                if not result.ok:
                    tint = FAILED_TINT
                elif result.interpolated:
                    tint = INTERPOLATED_TINT
                else:
                    tint = SIZED_TINT

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

            self.table.removeCellWidget(index, len(COLUMNS))
            if pipeline.sizable(space):
                self.table.setCellWidget(
                    index, len(COLUMNS), self._action_cell(space.row, result)
                )
            else:
                blank = QTableWidgetItem("")
                if tint is not None:
                    blank.setBackground(tint)
                self.table.setItem(index, len(COLUMNS), blank)

        # size to content first so no header is clipped, then let the name
        # column absorb the remaining width
        self.table.resizeColumnsToContents()
        for column, (_key, _title, minimum) in enumerate(COLUMNS):
            if self.table.columnWidth(column) < minimum:
                self.table.setColumnWidth(column, minimum)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(len(COLUMNS), 130)

        sized = sum(1 for r in results.values() if r.ok)
        self.steps.set_step(2 if sized else 1)
        self.generate_btn.setEnabled(sized > 0)
        source = Path(self._ctx.air_source_path).name if self._ctx.air_source_path else ""
        total = sum(1 for s in spaces if pipeline.sizable(s))
        self.source_label.setText(
            f"{source} • {sized} of {total} subspaces sized" if source else ""
        )

    def _action_cell(self, row: int, result) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(6, 3, 6, 3)
        button = QPushButton("Preview" if result is not None else "Click Here")
        button.setObjectName("RowAction")
        button.setProperty("rowDone", "true" if result is not None else "false")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, r=row: self.open_sizing(r))
        lay.addWidget(button)
        return holder

    # --------------------------------------------------------------- actions
    def open_sizing(self, row: int) -> None:
        dialog = SizingDialog(
            self._ctx.air_config, self._ctx.air_spaces, row, self._ctx.air_inputs, self
        )
        dialog.saved.connect(self._ctx.record_sizing)
        dialog.exec()
        self.refresh()

"""Change Request — progress screen
(mockup: HAP_change_request/excel loading + pdf parsing.png).

Overall progress bar, a four-step timeline, and a live Change Summary
(existing records / new records / resulting size).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets import StepTimeline, card, label

STEPS = [
    "Previous Excel loaded",
    "Revised PDF extracted",
    "Comparing line items",
    "Generate updated Excel",
]
STEP_CAPTIONS = [
    "Reading existing records",
    "Extracting the new FCU schedule data",
    "Identifying new records to append",
    "Appending and highlighting new records",
]


class ChangeProgressPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        body = card()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 18, 24, 18)
        body_lay.setSpacing(12)

        # radios sit inside the card on every page; locked while running
        radios = QHBoxLayout()
        new_project = QRadioButton("New Project")
        new_project.setEnabled(False)
        self.change_request_radio = QRadioButton("Change Request")
        self.change_request_radio.setChecked(True)
        self.change_request_radio.setEnabled(False)
        radios.addWidget(new_project)
        radios.addSpacing(30)
        radios.addWidget(self.change_request_radio)
        radios.addStretch(1)
        body_lay.addLayout(radios)

        body_lay.addWidget(label("Generating Change Request", "H2"))
        body_lay.addWidget(
            label(
                "Comparing the previous Excel with the revised PDF and "
                "preparing the updated schedule.",
                "Small",
            )
        )

        bar_head = QHBoxLayout()
        bar_head.addWidget(label("Overall progress", "Small"))
        bar_head.addStretch(1)
        self.percent = label("0%", "StatusOk")
        bar_head.addWidget(self.percent)
        body_lay.addLayout(bar_head)
        self.progress = QProgressBar()
        self.progress.setRange(0, 4)
        body_lay.addWidget(self.progress)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        self.timeline = StepTimeline(STEPS)
        columns.addWidget(self.timeline, 11, Qt.AlignTop)

        summary = card("PanelCard")
        summary_lay = QVBoxLayout(summary)
        summary_lay.setContentsMargins(20, 16, 20, 16)
        summary_lay.setSpacing(10)
        summary_lay.addWidget(label("Change Summary", "H2"))
        self._rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key, caption in (
            ("existing", "EXISTING RECORDS"),
            ("new", "NEW RECORDS"),
            ("output", "OUTPUT"),
        ):
            row = QFrame()
            row.setObjectName("EtaBox" if key == "new" else "InfoCard")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(14, 10, 14, 10)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(label(caption, "SummaryKey"))
            value = label("—", "SummaryVal")
            col.addWidget(value)
            row_lay.addLayout(col, 1)
            note = label("", "Small")
            row_lay.addWidget(note)
            self._rows[key] = (value, note)
            summary_lay.addWidget(row)
        summary_lay.addStretch(1)
        summary_lay.addWidget(
            label("Please keep this window open while the new Excel is generated.", "Small")
        )
        columns.addWidget(summary, 9)
        body_lay.addLayout(columns, 1)
        root.addWidget(body, 1)

    # -------------------------------------------------------------- state
    def begin(self, xlsx_path: str, pdf_path: str) -> None:
        self.progress.setValue(0)
        self.percent.setText("0%")
        self.timeline.set_step(1)
        for value, note in self._rows.values():
            value.setText("—")
            note.setText("")

    def on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.percent.setText(f"{int(done / max(total, 1) * 100)}%")
        self.timeline.set_step(min(done + 1, len(STEPS)))

    def update_summary(self, stats: dict) -> None:
        existing = stats.get("existing_rows")
        new_rows = stats.get("new_rows")
        total = stats.get("total_rows")
        columns = stats.get("columns", 14)
        if existing is not None:
            self._rows["existing"][0].setText(str(existing))
            self._rows["existing"][1].setText("unchanged")
        if new_rows is not None:
            self._rows["new"][0].setText(str(new_rows))
            self._rows["new"][1].setText("will be appended")
        if total is not None:
            self._rows["output"][0].setText(f"{total} rows • {columns} columns")

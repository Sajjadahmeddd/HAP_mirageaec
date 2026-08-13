"""Modal form for the 8 mandatory project details that head the downloaded
CSV (Project / Project No / Stage / Discipline / Author / Checked /
Revision / Date). Date uses a calendar popup so the format stays uniform
(dd.MM.yyyy, matching the FCU schedule template).
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from hap_converter.engine.synthesizer import PROJECT_FIELDS

DATE_FORMAT = "dd.MM.yyyy"


class ProjectDetailsDialog(QDialog):
    def __init__(self, parent=None, initial: dict[str, str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Project details")
        self.setModal(True)
        self.setMinimumWidth(420)
        initial = initial or {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        intro = QLabel(
            "These details head the downloaded CSV (FCU schedule format).\n"
            "All fields are mandatory."
        )
        intro.setObjectName("Muted")
        lay.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)
        self._edits: dict[str, QLineEdit] = {}
        for key, form_label in PROJECT_FIELDS:
            if key == "date":
                continue
            edit = QLineEdit(initial.get(key, ""))
            edit.setPlaceholderText(form_label.rstrip(":"))
            self._edits[key] = edit
            form.addRow(form_label, edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat(DATE_FORMAT)
        prior = QDate.fromString(initial.get("date", ""), DATE_FORMAT)
        self.date_edit.setDate(prior if prior.isValid() else QDate.currentDate())
        form.addRow("Date:", self.date_edit)
        lay.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("StatusFail")
        self.error_label.hide()
        lay.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("Secondary")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        lay.addLayout(buttons)

    def _save(self) -> None:
        empty = [
            form_label.rstrip(":")
            for key, form_label in PROJECT_FIELDS
            if key != "date" and not self._edits[key].text().strip()
        ]
        if empty:
            self.error_label.setText("Please fill: " + ", ".join(empty))
            self.error_label.show()
            return
        self.accept()

    def details(self) -> dict[str, str]:
        result = {key: edit.text().strip() for key, edit in self._edits.items()}
        result["date"] = self.date_edit.date().toString(DATE_FORMAT)
        return result

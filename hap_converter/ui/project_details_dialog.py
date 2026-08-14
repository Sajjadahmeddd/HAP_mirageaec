"""Modal form for the 8 mandatory project details that head the downloaded
CSV (Project / Project No / Stage / Discipline / Author / Checked /
Revision / Date). Date uses a calendar popup so the format stays uniform
(dd.MM.yyyy, matching the FCU schedule template).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hap_converter.engine.synthesizer import LOGO_KEY, LOGO_SUFFIXES, PROJECT_FIELDS

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
            "These details head the downloaded schedule (FCU schedule format).\n"
            "All fields are mandatory. The logo is placed in the sheet header."
        )
        intro.setObjectName("Muted")
        lay.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)

        # -- company logo (image file only; heads the Excel G1:N1 zone)
        self._logo_path: str = initial.get(LOGO_KEY, "")
        logo_row = QWidget()
        logo_lay = QHBoxLayout(logo_row)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_lay.setSpacing(8)
        self.logo_preview = QLabel()
        self.logo_preview.setFixedSize(90, 34)
        self.logo_preview.setAlignment(Qt.AlignCenter)
        self.logo_preview.setObjectName("LogoPreview")
        logo_lay.addWidget(self.logo_preview)
        self.logo_name = QLabel("No image selected")
        self.logo_name.setObjectName("Small")
        logo_lay.addWidget(self.logo_name, 1)
        browse = QPushButton("Browse…")
        browse.setObjectName("Secondary")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._pick_logo)
        logo_lay.addWidget(browse)
        form.addRow("Company Logo:", logo_row)
        self._refresh_logo()

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

    # ------------------------------------------------------------ logo
    def _pick_logo(self) -> None:
        start = str(Path(self._logo_path).parent) if self._logo_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select company logo", start, "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        if Path(path).suffix.lower() not in LOGO_SUFFIXES:
            self.error_label.setText("Logo must be a PNG, JPG or JPEG image.")
            self.error_label.show()
            return
        self._logo_path = path
        self.error_label.hide()
        self._refresh_logo()

    def _refresh_logo(self) -> None:
        if not self._logo_path or not Path(self._logo_path).is_file():
            self.logo_preview.clear()
            self.logo_name.setText("No image selected  (PNG / JPG / JPEG)")
            return
        pixmap = QPixmap(self._logo_path)
        if pixmap.isNull():
            self.logo_preview.clear()
            self.logo_name.setText("Selected file is not a readable image")
            return
        self.logo_preview.setPixmap(
            pixmap.scaled(88, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.logo_name.setText(Path(self._logo_path).name)

    # ------------------------------------------------------------ save
    def _save(self) -> None:
        empty = [
            form_label.rstrip(":")
            for key, form_label in PROJECT_FIELDS
            if key != "date" and not self._edits[key].text().strip()
        ]
        if not self._logo_path or not Path(self._logo_path).is_file():
            empty.insert(0, "Company Logo")
        if empty:
            self.error_label.setText("Please fill: " + ", ".join(empty))
            self.error_label.show()
            return
        self.accept()

    def details(self) -> dict[str, str]:
        result = {key: edit.text().strip() for key, edit in self._edits.items()}
        result["date"] = self.date_edit.date().toString(DATE_FORMAT)
        result[LOGO_KEY] = self._logo_path
        return result

"""Page 2 — Upload (New Project): drop zone, Upload / Convert CSV actions,
output-folder line, info cards, Recent Projects side panel
(mockup: normal scenario/uploading screen.png).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets import DropZone, InfoCard, RecentProjectsPanel, card, label

SUPPORT_EMAIL = "support@mirageinc.example"


class UploadPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._picked_path: str | None = None  # picked but not yet "uploaded"

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        # ---------------- left card: radios + dropzone + actions + info
        left_card = card()
        left = QVBoxLayout(left_card)
        left.setContentsMargins(24, 18, 24, 18)
        left.setSpacing(14)

        radios = QHBoxLayout()
        self.new_project_radio = QRadioButton("New Project")
        self.new_project_radio.setChecked(True)
        change_request = QRadioButton("Change Request")
        change_request.setEnabled(False)
        change_request.setToolTip("Coming soon")
        radios.addWidget(self.new_project_radio)
        radios.addSpacing(30)
        radios.addWidget(change_request)
        radios.addStretch(1)
        left.addLayout(radios)

        middle = QHBoxLayout()
        middle.setSpacing(22)
        self.drop_zone = DropZone()
        self.drop_zone.browse_btn.clicked.connect(self._browse)
        self.drop_zone.file_selected.connect(self._on_picked)
        middle.addWidget(self.drop_zone, 11)

        actions = QVBoxLayout()
        actions.setSpacing(12)
        actions.addStretch(1)
        self.upload_btn = QPushButton("Upload")
        self.upload_btn.setObjectName("Primary")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self._upload)
        actions.addWidget(self.upload_btn)

        self.convert_btn = QPushButton("⊞  Convert CSV")
        self.convert_btn.setObjectName("Secondary")
        self.convert_btn.setCursor(Qt.PointingHandCursor)
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._ctx.start_conversion)
        actions.addWidget(self.convert_btn)

        out_row = QHBoxLayout()
        out_row.setSpacing(4)
        self.output_label = label("Output: —", "Small")
        self.output_label.setMaximumWidth(230)
        out_row.addWidget(self.output_label)
        change_out = QPushButton("Change…")
        change_out.setObjectName("Ghost")
        change_out.setCursor(Qt.PointingHandCursor)
        change_out.clicked.connect(self._pick_output_dir)
        out_row.addWidget(change_out)
        out_row.addStretch(1)
        actions.addLayout(out_row)
        actions.addStretch(2)
        middle.addLayout(actions, 8)
        left.addLayout(middle, 1)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        cards_row.addWidget(InfoCard("Fast & Accurate", "Extract data with high precision"))
        cards_row.addWidget(InfoCard("Secure", "Your data is safe with us"))
        cards_row.addWidget(InfoCard("Smart Workflow", "Streamline your AEC process"))
        left.addLayout(cards_row)
        root.addWidget(left_card, 13)

        # ---------------- right: recents + support
        right = QVBoxLayout()
        right.setSpacing(10)
        self.recents_panel = RecentProjectsPanel(ctx.recents)
        self.recents_panel.open_requested.connect(ctx.open_recent)
        right.addWidget(self.recents_panel, 1)

        support_row = QHBoxLayout()
        support_row.addWidget(label("Need help?", "Small"))
        support_btn = QPushButton("Contact Support")
        support_btn.setObjectName("Ghost")
        support_btn.setCursor(Qt.PointingHandCursor)
        support_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"mailto:{SUPPORT_EMAIL}"))
        )
        support_row.addWidget(support_btn)
        support_row.addStretch(1)
        right.addLayout(support_row)
        root.addLayout(right, 7)

    # ------------------------------------------------------------- actions
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select HAP System Design PDF", "", "PDF files (*.pdf)"
        )
        if path:
            self._on_picked(path)

    def _on_picked(self, path: str) -> None:
        self._picked_path = path
        self._ctx.set_pdf(None)  # invalidate any previously uploaded file
        self.drop_zone.show_file(path, pages=0, size_bytes=Path(path).stat().st_size)
        self.upload_btn.setEnabled(True)
        self.convert_btn.setEnabled(False)
        self._refresh_output_label()

    def _upload(self) -> None:
        """Register the picked file: verify it opens as a PDF, show stats."""
        path = self._picked_path
        if not path:
            return
        try:
            with pymupdf.open(path) as doc:
                pages = doc.page_count
        except Exception:
            self.drop_zone.show_error("This file could not be opened as a PDF")
            self.upload_btn.setEnabled(False)
            return
        size = Path(path).stat().st_size
        self.drop_zone.show_file(path, pages=pages, size_bytes=size)
        self._ctx.set_pdf(path, pages=pages, size_bytes=size)
        self.convert_btn.setEnabled(True)

    def _pick_output_dir(self) -> None:
        start = self._ctx.output_dir or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if path:
            self._ctx.output_dir = path
            self._ctx.output_dir_overridden = True
            self._refresh_output_label()

    def _refresh_output_label(self) -> None:
        if self._ctx.output_dir_overridden and self._ctx.output_dir:
            self.output_label.setText(f"Output: {self._ctx.output_dir}")
        else:
            self.output_label.setText("Output: chosen when you download")

    # ------------------------------------------------------------- external
    def preselect(self, path: str) -> None:
        """Open with a PDF preselected (from a Recent Projects click)."""
        if Path(path).is_file():
            self._on_picked(path)
            self._upload()
        else:
            self.drop_zone.show_error("File no longer exists at its original location")

    def refresh(self) -> None:
        self.recents_panel.refresh()
        self._refresh_output_label()

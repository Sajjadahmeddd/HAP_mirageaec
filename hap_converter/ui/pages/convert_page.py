"""Page 3 — Converting: file card, progress bar, cancel, and the
Conversion Status side panel with step timeline and ETA
(mockup: normal scenario/pdf conversion screen.png).
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets import InfoCard, StepTimeline, card, label, pdf_badge


class ConvertPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._started_at = 0.0

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        # ---------------- left card
        left_card = card()
        left = QVBoxLayout(left_card)
        left.setContentsMargins(24, 20, 24, 18)
        left.setSpacing(14)

        file_row = QHBoxLayout()
        file_row.setSpacing(16)
        file_row.addWidget(pdf_badge(56))
        file_col = QVBoxLayout()
        file_col.setSpacing(2)
        self.file_name = label("—", "H2")
        self.file_meta = label("", "Small")
        file_col.addWidget(self.file_name)
        file_col.addWidget(self.file_meta)
        file_col.addStretch(1)
        file_row.addLayout(file_col, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(10)
        self.processing_btn = QPushButton("Processing…")
        self.processing_btn.setObjectName("Processing")
        self.processing_btn.setEnabled(False)
        btn_col.addWidget(self.processing_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Secondary")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._ctx.cancel_conversion)
        btn_col.addWidget(self.cancel_btn)
        file_row.addLayout(btn_col)
        left.addLayout(file_row)

        prog_head = QHBoxLayout()
        prog_head.addWidget(label("Converting PDF to CSV", "H2"))
        prog_head.addStretch(1)
        self.percent_label = label("0%", "StatusOk")
        prog_head.addWidget(self.percent_label)
        left.addLayout(prog_head)

        self.progress = QProgressBar()
        left.addWidget(self.progress)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_label = label("Preparing…", "Muted")
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        chip = label("OUTPUT: CSV", "Chip")
        status_row.addWidget(chip)
        left.addLayout(status_row)
        left.addStretch(1)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        cards_row.addWidget(InfoCard("Fast & Accurate", "Extract data with high precision"))
        cards_row.addWidget(InfoCard("Secure", "Your data is safe with us"))
        cards_row.addWidget(InfoCard("Smart Workflow", "Streamline your AEC process"))
        left.addLayout(cards_row)
        root.addWidget(left_card, 13)

        # ---------------- right: conversion status panel
        panel = card("PanelCard")
        right = QVBoxLayout(panel)
        right.setContentsMargins(20, 18, 20, 18)
        right.setSpacing(16)
        right.addWidget(label("Conversion Status", "H2"))
        right.addWidget(label("Current file", "Small"))

        mini = card()
        mini_lay = QHBoxLayout(mini)
        mini_lay.setContentsMargins(14, 12, 14, 12)
        mini_lay.setSpacing(12)
        mini_lay.addWidget(pdf_badge(38))
        mini_col = QVBoxLayout()
        mini_col.setSpacing(1)
        self.mini_name = label("—", "RecentName")
        mini_col.addWidget(self.mini_name)
        mini_col.addWidget(label("Converting to .csv", "Small"))
        mini_lay.addLayout(mini_col, 1)
        right.addWidget(mini)

        self.timeline = StepTimeline(["File uploaded", "Extracting data", "Generate CSV"])
        right.addWidget(self.timeline)
        right.addStretch(1)

        eta_box = card("EtaBox")
        eta_lay = QVBoxLayout(eta_box)
        eta_lay.setContentsMargins(16, 10, 16, 10)
        eta_lay.setSpacing(2)
        eta_lay.addWidget(label("Estimated remaining", "Small"))
        self.eta_label = QLabel("~ …")
        self.eta_label.setObjectName("EtaValue")
        eta_lay.addWidget(self.eta_label)
        right.addWidget(eta_box)
        right.addWidget(label("You can continue working while we process.", "Small"))
        root.addWidget(panel, 7)

    # ------------------------------------------------------------- external
    def begin(self, pdf_path: str, size_bytes: int) -> None:
        self._started_at = time.monotonic()
        name = Path(pdf_path).name
        self.file_name.setText(name)
        self.file_meta.setText(f"{size_bytes / (1024 * 1024):.1f} MB • Uploaded just now")
        self.mini_name.setText(name)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.percent_label.setText("0%")
        self.status_label.setText("Preparing…")
        self.eta_label.setText("~ …")
        self.timeline.set_step(2)  # step 1 (file uploaded) done, extracting active

    def on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        pct = int(done / max(total, 1) * 100)
        self.percent_label.setText(f"{pct}%")
        self.status_label.setText(message)
        if message.startswith("Writing"):
            self.timeline.set_step(3)
        elapsed = time.monotonic() - self._started_at
        if done > 0 and total > 0 and done < total:
            remaining = elapsed / done * (total - done)
            self.eta_label.setText(f"~ {max(1, round(remaining))} seconds")
        elif done >= total:
            self.eta_label.setText("~ finishing…")

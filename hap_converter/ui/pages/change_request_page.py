"""Change Request — upload screen
(mockup: HAP_change_request/uploading previous excel + new pdf.png).

Two upload cards: the previously generated Excel and the revised PDF.
No project details are collected here — the existing workbook's header
block and embedded logo are carried over untouched.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...engine import change_request
from .. import theme
from ..widgets import card, label


class _FileDrop(QFrame):
    """Dashed drop area used by both upload cards."""

    file_selected = Signal(str)

    def __init__(self, prompt: str, button_text: str, suffixes: tuple[str, ...]):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)
        self._suffixes = suffixes

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        self.prompt = label(prompt, "Muted")
        self.prompt.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.prompt)
        self.sub = label("or", "Small")
        self.sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.sub)
        self.button = QPushButton(button_text)
        self.button.setObjectName("Secondary")
        self.button.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.button, 0, Qt.AlignHCenter)

    def _accepts(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._suffixes

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and self._accepts(urls[0].toLocalFile()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and self._accepts(urls[0].toLocalFile()):
            self.file_selected.emit(urls[0].toLocalFile())


class _UploadCard(QFrame):
    """One of the two side-by-side cards (Previous Excel / New PDF)."""

    file_selected = Signal(str)
    cleared = Signal()

    def __init__(self, icon: str, icon_color: str, title: str, subtitle: str,
                 prompt: str, button_text: str, suffixes: tuple[str, ...]):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        badge = QLabel(icon)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(40, 40)
        badge.setStyleSheet(
            f"background: {icon_color}; color: white; border-radius: 10px;"
            "font-size: 16px; font-weight: 800;"
        )
        head.addWidget(badge)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title, "H2"))
        text.addWidget(label(subtitle, "Small"))
        head.addLayout(text, 1)
        lay.addLayout(head)

        self.drop = _FileDrop(prompt, button_text, suffixes)
        self.drop.button.clicked.connect(self._browse)
        self.drop.file_selected.connect(self._accept)
        lay.addWidget(self.drop)

        # shown once a file is loaded
        self.loaded = QFrame()
        self.loaded.setObjectName("InfoCard")
        loaded_lay = QHBoxLayout(self.loaded)
        loaded_lay.setContentsMargins(14, 10, 14, 10)
        info = QVBoxLayout()
        info.setSpacing(1)
        self.file_name = label("", "RecentName")
        self.file_meta = label("", "Small")
        info.addWidget(self.file_name)
        info.addWidget(self.file_meta)
        loaded_lay.addLayout(info, 1)
        self.status_pill = QLabel("READY")
        self.status_pill.setObjectName("PillOk")
        loaded_lay.addWidget(self.status_pill)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("Ghost")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.setToolTip("Remove this file, then browse for another one")
        self.remove_btn.clicked.connect(self._clear)
        loaded_lay.addWidget(self.remove_btn)
        self.loaded.hide()
        lay.addWidget(self.loaded)

        self._filter = f"Files ({' '.join('*' + s for s in suffixes)})"

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "", self._filter)
        if path:
            self._accept(path)

    def _accept(self, path: str) -> None:
        self.file_selected.emit(path)

    def show_loaded(self, name: str, meta: str, ok: bool = True) -> None:
        self.file_name.setText(name)
        self.file_meta.setText(meta)
        self.status_pill.setText("READY" if ok else "PROBLEM")
        self.status_pill.setObjectName("PillOk" if ok else "PillFail")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.loaded.show()
        self.drop.setVisible(False)

    def _clear(self) -> None:
        self.reset()
        self.cleared.emit()

    def reset(self) -> None:
        self.loaded.hide()
        self.drop.setVisible(True)


class ChangeRequestPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._xlsx: str | None = None
        self._pdf: str | None = None

        # margins match the New Project page exactly so the white card does
        # not shift when switching modes
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        body = card()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 18, 24, 18)
        body_lay.setSpacing(14)

        # -- mode radios: inside the card, same as the New Project page
        radios = QHBoxLayout()
        self.new_project_radio = QRadioButton("New Project")
        self.new_project_radio.setCursor(Qt.PointingHandCursor)
        self.new_project_radio.clicked.connect(self._ctx.go_upload)
        self.change_request_radio = QRadioButton("Change Request")
        self.change_request_radio.setCursor(Qt.PointingHandCursor)
        self.change_request_radio.setChecked(True)
        radios.addWidget(self.new_project_radio)
        radios.addSpacing(30)
        radios.addWidget(self.change_request_radio)
        radios.addStretch(1)
        body_lay.addLayout(radios)

        body_lay.addWidget(label("Create Change Request", "H2"))
        body_lay.addWidget(
            label(
                "Upload the previous Excel and the revised PDF. "
                "Mirage AEC will append the new line items.",
                "Small",
            )
        )

        cards = QHBoxLayout()
        cards.setSpacing(18)
        self.excel_card = _UploadCard(
            "▤", "#4E8A3A", "Previous Excel",
            "Upload the latest approved .xlsx file",
            "Drop the previous Excel here", "Browse Excel", (".xlsx",),
        )
        self.excel_card.file_selected.connect(self._load_excel)
        self.excel_card.cleared.connect(self._clear_excel)
        cards.addWidget(self.excel_card)

        self.pdf_card = _UploadCard(
            "▦", theme.RED, "New PDF",
            "Upload the revised HAP schedule",
            "Drop revised PDF here", "Browse PDF", (".pdf",),
        )
        self.pdf_card.file_selected.connect(self._load_pdf)
        self.pdf_card.cleared.connect(self._clear_pdf)
        cards.addWidget(self.pdf_card)
        body_lay.addLayout(cards)

        body_lay.addWidget(label("Change Request Settings", "H2"))
        settings = QHBoxLayout()
        settings.setSpacing(18)
        for title, sub in (
            ("Append new line items", "Existing records remain unchanged"),
            ("Highlight new records", "New rows highlighted in the preview"),
        ):
            item = QFrame()
            item.setObjectName("InfoCard")
            item_lay = QHBoxLayout(item)
            item_lay.setContentsMargins(14, 10, 14, 10)
            item_lay.setSpacing(10)
            tick = QLabel("✓")
            tick.setObjectName("StepDotDone")
            tick.setAlignment(Qt.AlignCenter)
            item_lay.addWidget(tick)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(label(title, "InfoCardTitle"))
            col.addWidget(label(sub, "Small"))
            item_lay.addLayout(col, 1)
            settings.addWidget(item)
        body_lay.addLayout(settings)
        body_lay.addStretch(1)

        # -- how it works + action
        footer = QFrame()
        footer.setObjectName("EtaBox")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(18, 12, 18, 12)
        how = QVBoxLayout()
        how.setSpacing(1)
        how.addWidget(label("How it works", "InfoCardTitle"))
        how.addWidget(
            label(
                "Compare previous Excel → extract revised PDF → "
                "append new line items → highlight changes",
                "Small",
            )
        )
        footer_lay.addLayout(how, 1)
        self.generate_btn = QPushButton("Generate New Excel")
        self.generate_btn.setObjectName("Primary")
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._generate)
        footer_lay.addWidget(self.generate_btn)
        body_lay.addWidget(footer)

        self.error_label = label("", "StatusFail")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        body_lay.addWidget(self.error_label)

        root.addWidget(body, 1)

    # -------------------------------------------------------------- loading
    def _load_excel(self, path: str) -> None:
        self.error_label.hide()
        try:
            schedule = change_request.load_schedule(path, self._ctx.config)
        except change_request.ScheduleFormatError as exc:
            self._xlsx = None
            self.excel_card.show_loaded(Path(path).name, str(exc), ok=False)
            self._refresh_button()
            return
        self._xlsx = path
        self.excel_card.show_loaded(
            Path(path).name,
            f"{schedule.row_count} rows • {len(schedule.column_header)} columns",
        )
        self._refresh_button()

    def _load_pdf(self, path: str) -> None:
        self.error_label.hide()
        self._pdf = path
        size_mb = Path(path).stat().st_size / (1024 * 1024)
        self.pdf_card.show_loaded(Path(path).name, f"{size_mb:.1f} MB • revised report")
        self._refresh_button()

    def _clear_excel(self) -> None:
        self._xlsx = None
        self.error_label.hide()
        self._refresh_button()

    def _clear_pdf(self) -> None:
        self._pdf = None
        self.error_label.hide()
        self._refresh_button()

    def _refresh_button(self) -> None:
        self.generate_btn.setEnabled(bool(self._xlsx and self._pdf))

    def _generate(self) -> None:
        if self._xlsx and self._pdf:
            self._ctx.start_change_request(self._xlsx, self._pdf)

    def reset(self) -> None:
        self._xlsx = self._pdf = None
        self.excel_card.reset()
        self.pdf_card.reset()
        self.error_label.hide()
        self._refresh_button()

    def refresh(self) -> None:
        # the mode radio must reflect the page you are actually on
        self.change_request_radio.setChecked(True)

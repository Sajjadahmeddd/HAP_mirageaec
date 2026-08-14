"""Failure page (mockup: normal scenario/failure page.png).

Left card: broken-file icon, "Unable to Generate Excel", a two-line summary,
then a "Failure Reasons" list where each detected reason has a bold title
and a two-line explanation. Right panel: Conversion Status with the failed
step marked ✕ and a red "Failed" box.

Reasons are dynamic — only the causes that actually occurred are shown,
derived from the engine's Issue list. For missing/unreadable-value failures
a scrollable per-page detail list follows the reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...engine.pipeline import Result
from ..widgets import card, label, pdf_badge


@dataclass
class _Reason:
    icon: str
    title: str
    desc: str          # the two-line explanation
    step: int          # which timeline step failed (1..3)
    caption: str       # red caption under the failed step


def _categorize(result: Result) -> tuple[list[_Reason], list, str]:
    """Map engine issues -> (reason cards, detail issues, summary text)."""
    issues = result.issues
    fields = {i.field for i in issues}
    reasons: list[_Reason] = []
    details = []

    if "file" in fields:
        desc = next(i.description for i in issues if i.field == "file")
        reasons.append(_Reason(
            "✕", "File Could Not Be Read",
            "The file could not be opened as a PDF.\nIt may be corrupted or not a PDF document.",
            1, "Failed – File could not be read",
        ))
        summary = "The uploaded file could not be opened as a PDF document."
        return reasons, details, summary

    if "protected" in fields:
        reasons.append(_Reason(
            "🔒", "Content Protected",
            "This PDF is password protected or\nrestricted from data extraction.",
            1, "Failed – PDF is protected",
        ))
        return reasons, details, "The uploaded PDF is protected and cannot be read for data extraction."

    if "scanned" in fields:
        reasons.append(_Reason(
            "T", "Scanned Document",
            "The PDF appears to be scanned.\nText cannot be extracted.",
            2, "Failed – Unable to extract data",
        ))
        return reasons, details, (
            "The uploaded PDF does not contain extractable text\nto generate an Excel file."
        )

    if "document" in fields:
        reasons.append(_Reason(
            "▦", "No HAP Data Detected",
            "No HAP Zone Sizing Summary pages were found.\nCheck that the correct report was exported from HAP.",
            2, "Failed – Unable to extract data",
        ))
        return reasons, details, (
            "The uploaded PDF does not contain enough structured or tabular data\n"
            "to generate an Excel file."
        )

    if "cancelled" in fields:
        reasons.append(_Reason(
            "◼", "Conversion Stopped",
            "The conversion was cancelled before it completed.\nNo file was generated.",
            2, "Stopped – Cancelled by user",
        ))
        return reasons, details, "The conversion was stopped before it could complete."

    if "error" in fields:
        desc = next(i.description for i in issues if i.field == "error")
        reasons.append(_Reason(
            "!", "Output Could Not Be Written",
            "The converted file could not be saved.\nThe folder may be locked, full, or read-only.",
            3, "Failed – Could not write file",
        ))
        details = [i for i in issues if i.field == "error"]
        return reasons, details, "The conversion failed while writing the output file."

    # otherwise: validation issues (missing / unreadable mandatory values)
    unreadable = [i for i in issues if "Unreadable" in i.description or "zero" in i.description.lower()]
    missing = [i for i in issues if i not in unreadable]
    pages = {i.page for i in issues}
    if missing:
        reasons.append(_Reason(
            "!", "Missing Mandatory Values",
            f"{len(missing)} required value(s) are missing across "
            f"{len({i.page for i in missing})} page(s).\nThe full list is shown below.",
            2, "Failed – Missing mandatory data",
        ))
    if unreadable:
        reasons.append(_Reason(
            "≠", "Unreadable Values",
            f"{len(unreadable)} value(s) could not be read as numbers.\n"
            "They are listed below with their page numbers.",
            2, "Failed – Unreadable data",
        ))
    summary = (
        "The uploaded PDF is missing mandatory values, so the Excel file\n"
        "was not generated (all-or-nothing validation)."
    )
    return reasons, sorted(issues, key=lambda i: i.page), summary


class FailurePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        # ---------------- left card
        left_card = card()
        left = QVBoxLayout(left_card)
        left.setContentsMargins(28, 18, 28, 18)
        left.setSpacing(10)

        radios = QHBoxLayout()
        new_project = QRadioButton("New Project")
        new_project.setChecked(True)
        change_request = QRadioButton("Change Request")
        change_request.setEnabled(False)
        change_request.setToolTip("Coming soon")
        radios.addWidget(new_project)
        radios.addSpacing(30)
        radios.addWidget(change_request)
        radios.addStretch(1)
        left.addLayout(radios)

        # broken-file icon: PDF badge with a red "!" badge overlapping
        icon_host = QWidget()
        icon_host.setFixedSize(76, 64)
        icon_grid = QGridLayout(icon_host)
        icon_grid.setContentsMargins(0, 0, 0, 0)
        badge = pdf_badge(52)
        icon_grid.addWidget(badge, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        bang = QLabel("!")
        bang.setObjectName("FailBadge")
        bang.setAlignment(Qt.AlignCenter)
        icon_grid.addWidget(bang, 0, 0, Qt.AlignRight | Qt.AlignTop)
        left.addWidget(icon_host, 0, Qt.AlignHCenter)

        title = label("Unable to Generate Excel", "FailTitle")
        title.setAlignment(Qt.AlignCenter)
        left.addWidget(title)
        self.summary_label = label("", "Muted")
        self.summary_label.setAlignment(Qt.AlignCenter)
        left.addWidget(self.summary_label)
        left.addSpacing(6)

        left.addWidget(label("Failure Reasons", "H2"))
        self.reasons_frame = QFrame()
        self.reasons_frame.setObjectName("ReasonFrame")
        self.reasons_lay = QVBoxLayout(self.reasons_frame)
        self.reasons_lay.setContentsMargins(16, 6, 16, 6)
        self.reasons_lay.setSpacing(0)
        left.addWidget(self.reasons_frame)

        # per-page details (missing/unreadable values)
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_host = QWidget()
        self.details_lay = QVBoxLayout(self.details_host)
        self.details_lay.setContentsMargins(0, 4, 8, 0)
        self.details_lay.setSpacing(4)
        self.details_lay.addStretch(1)
        self.details_scroll.setWidget(self.details_host)
        left.addWidget(self.details_scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        upload_btn = QPushButton("⬆  Upload Another File")
        upload_btn.setObjectName("Secondary")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._ctx.go_upload)
        buttons.addWidget(upload_btn)
        dashboard_btn = QPushButton("Go to Dashboard")
        dashboard_btn.setObjectName("Primary")
        dashboard_btn.setCursor(Qt.PointingHandCursor)
        dashboard_btn.clicked.connect(self._ctx.go_home)
        buttons.addWidget(dashboard_btn)
        buttons.addStretch(1)
        left.addLayout(buttons)
        root.addWidget(left_card, 13)

        # ---------------- right: conversion status (failed)
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
        self.mini_meta = label("", "Small")
        mini_col.addWidget(self.mini_meta)
        mini_lay.addLayout(mini_col, 1)
        right.addWidget(mini)

        from ..widgets import StepTimeline  # local import to avoid cycle noise

        self.timeline = StepTimeline(["File uploaded", "Extracting data", "Generate Excel"])
        right.addWidget(self.timeline)
        right.addStretch(1)

        fail_box = card("EtaBoxFail")
        fail_lay = QVBoxLayout(fail_box)
        fail_lay.setContentsMargins(16, 10, 16, 10)
        fail_lay.setSpacing(2)
        fail_lay.addWidget(label("Estimated remaining", "Small"))
        failed_value = QLabel("Failed")
        failed_value.setObjectName("EtaValue")
        fail_lay.addWidget(failed_value)
        right.addWidget(fail_box)
        right.addWidget(label("Please resolve the issues above and try again.", "Small"))
        root.addWidget(panel, 7)

    # ------------------------------------------------------------- state
    def show_result(self, result: Result, pdf_path: str, size_bytes: int) -> None:
        name = Path(pdf_path).name if pdf_path else "—"
        self.mini_name.setText(name)
        mb = size_bytes / (1024 * 1024) if size_bytes else 0
        self.mini_meta.setText(f"{mb:.1f} MB • Conversion failed" if mb else "Conversion failed")

        reasons, details, summary = _categorize(result)
        self.summary_label.setText(summary)

        # timeline: mark the earliest failed step
        first = reasons[0] if reasons else None
        self.timeline.set_failed(first.step if first else 2, first.caption if first else "Failed")

        # rebuild reasons list
        while self.reasons_lay.count():
            item = self.reasons_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for idx, reason in enumerate(reasons):
            if idx:
                sep = QFrame()
                sep.setObjectName("ReasonSep")
                self.reasons_lay.addWidget(sep)
            self.reasons_lay.addWidget(self._reason_row(reason))

        # rebuild per-page details
        while self.details_lay.count() > 1:
            item = self.details_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for issue in details:
            where = f"Page {issue.page}" if issue.page else "File"
            row = label(f"{where} — {issue.field}: {issue.description}", "ReasonDesc")
            row.setWordWrap(True)
            self.details_lay.insertWidget(self.details_lay.count() - 1, row)

    @staticmethod
    def _reason_row(reason: _Reason) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(14)
        icon = QLabel(reason.icon)
        icon.setObjectName("ReasonIcon")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon, 0, Qt.AlignTop)
        title = label(reason.title, "ReasonTitle")
        title.setFixedWidth(180)
        lay.addWidget(title, 0, Qt.AlignVCenter)
        desc = label(reason.desc, "ReasonDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc, 1, Qt.AlignVCenter)
        return row

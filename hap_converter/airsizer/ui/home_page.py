"""AirSizer Pro home (Figma: "main screen").

Hero on the left, Quick Start / Recent Projects / Help on the right. Size
Diffusers asks for the schedule HAPExt produced; Review Results jumps
straight to the roll-up when a session is already open.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hap_converter.ui import theme

from ..engine.project import RecentProjects
from .widgets import card, label


class DuctArt(QWidget):
    """The light ceiling-grid motif behind the hero text."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(180)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        line = QColor("#B7C79A")

        ceiling = QPolygonF([
            QPointF(width * 0.06, height * 0.55),
            QPointF(width * 0.42, height * 0.12),
            QPointF(width * 0.94, height * 0.42),
            QPointF(width * 0.52, height * 0.88),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#F1F6E6"))
        painter.drawPolygon(ceiling)

        painter.setPen(QPen(line, 1))
        for step in range(1, 6):
            fraction = step / 6
            painter.drawLine(
                QPointF(
                    width * (0.06 + (0.42 - 0.06) * fraction),
                    height * (0.55 - (0.55 - 0.12) * fraction),
                ),
                QPointF(
                    width * (0.52 + (0.94 - 0.52) * fraction),
                    height * (0.88 - (0.88 - 0.42) * fraction),
                ),
            )

        # the diffuser at the centre, throwing air both ways
        painter.setPen(QPen(QColor(theme.GREEN), 2))
        painter.setBrush(QColor("white"))
        box = QPolygonF([
            QPointF(width * 0.42, height * 0.46),
            QPointF(width * 0.58, height * 0.46),
            QPointF(width * 0.58, height * 0.60),
            QPointF(width * 0.42, height * 0.60),
        ])
        painter.drawPolygon(box)
        for offset in (-1, 1):
            painter.drawLine(
                QPointF(width * 0.50, height * 0.60),
                QPointF(width * (0.50 + offset * 0.13), height * 0.82),
            )


class _QuickCard(QFrame):
    """One Quick Start tile."""

    def __init__(self, glyph: str, title: str, body: str, on_click):
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self._on_click = on_click

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 16)
        lay.setSpacing(10)
        icon = QLabel(glyph)
        icon.setObjectName("QuickIcon")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(label(title, "H2"))

        bottom = QHBoxLayout()
        bottom.addWidget(label(body, "Small", wrap=True), 1)
        arrow = label("→", "H2")
        arrow.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        bottom.addWidget(arrow)
        lay.addLayout(bottom)

    def mousePressEvent(self, event) -> None:
        if self.isEnabled():
            self._on_click()


class AirHomePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._recents = RecentProjects()

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        # ---------------- left: hero
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addSpacing(10)
        left.addWidget(label("Welcome to", "Muted"))
        title = QLabel(
            f'<span style="color:{theme.TEXT}">AirSizer </span>'
            f'<span style="color:{theme.GREEN}">Pro</span>'
        )
        title.setObjectName("H1")
        left.addWidget(title)
        rule = label("▬ ▪", "Muted")
        rule.setStyleSheet(f"color: {theme.GREEN}; font-size: 10px;")
        left.addWidget(rule)
        left.addWidget(
            label(
                "Design and size air distribution systems\n"
                "with catalog-based diffuser selection,\n"
                "performance checks and clear project results.",
                "Muted",
            )
        )
        left.addWidget(DuctArt(), 1)

        band = QFrame()
        band.setObjectName("FeatureBand")
        band_lay = QHBoxLayout(band)
        band_lay.setContentsMargins(18, 12, 18, 12)
        for feature in ("Accurate\nSizing", "Smart\nSelection", "Clear\nValidation", "Reliable\nResults"):
            chip = QLabel(feature)
            chip.setObjectName("FeatureChipTitle")
            chip.setAlignment(Qt.AlignCenter)
            band_lay.addWidget(chip)
        left.addWidget(band)
        root.addLayout(left, 11)

        # ---------------- right: quick start, recents, help
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(label("Quick Start", "H2"))

        cards = QGridLayout()
        cards.setSpacing(12)
        cards.addWidget(
            _QuickCard("▦", "Size Diffusers",
                       "Select catalog products and check performance.",
                       self._ctx.open_air_schedule), 0, 0)
        self.review_card = _QuickCard(
            "◷", "Review Results", "Compare throw, pressure, airflow and noise limits.",
            self._ctx.go_air_review,
        )
        cards.addWidget(self.review_card, 0, 1)
        right.addLayout(cards)

        head = QHBoxLayout()
        head.addWidget(label("Recent Projects", "H2"))
        head.addStretch(1)
        right.addLayout(head)

        self.recents_panel = QFrame()
        self.recents_panel.setObjectName("PanelCard")
        self._recents_lay = QVBoxLayout(self.recents_panel)
        self._recents_lay.setContentsMargins(14, 12, 14, 12)
        self._recents_lay.setSpacing(2)
        right.addWidget(self.recents_panel, 1)

        help_card = QFrame()
        help_card.setObjectName("HelpCard")
        help_lay = QHBoxLayout(help_card)
        help_lay.setContentsMargins(16, 12, 16, 12)
        help_lay.addWidget(label("AirSizer Pro — how sizing works", "InfoCardTitle"), 1)
        how = QPushButton("Open →")
        how.setObjectName("Ghost")
        how.setCursor(Qt.PointingHandCursor)
        how.clicked.connect(self._show_help)
        help_lay.addWidget(how)
        right.addWidget(help_card)
        root.addLayout(right, 9)

    # ------------------------------------------------------------- rendering
    def refresh(self) -> None:
        self._recents = RecentProjects()
        while self._recents_lay.count():
            item = self._recents_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries = self._recents.top(5)
        if not entries:
            empty = label("No saved sizing projects yet", "Muted")
            empty.setAlignment(Qt.AlignCenter)
            self._recents_lay.addWidget(empty)
        else:
            for entry in entries:
                self._recents_lay.addWidget(self._recent_row(entry))
        self._recents_lay.addStretch(1)
        self.review_card.setEnabled(bool(self._ctx.air_spaces))

    def _recent_row(self, entry) -> QWidget:
        row = QFrame()
        row.setObjectName("RecentItem")
        row.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 8, 4, 8)
        lay.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(entry.name or Path(entry.path).stem, "RecentName"))
        when = entry.updated.replace("T", " • ") if entry.updated else ""
        text.addWidget(label(f"{entry.sized} sized • {when}", "Small"))
        lay.addLayout(text, 1)

        kebab = QToolButton()
        kebab.setText("⋮")
        kebab.setCursor(Qt.PointingHandCursor)
        kebab.setStyleSheet("QToolButton { border: none; font-weight: 800; }")
        kebab.clicked.connect(lambda _checked=False, e=entry, a=kebab: self._menu(a, e))
        lay.addWidget(kebab)

        row.mousePressEvent = lambda _event, e=entry: self._ctx.open_air_project(e.path)
        return row

    def _menu(self, anchor: QWidget, entry) -> None:
        menu = QMenu(self)
        open_action = menu.addAction("Open project")
        menu.addSeparator()
        remove_action = menu.addAction("Remove from list")
        chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        if chosen is open_action:
            self._ctx.open_air_project(entry.path)
        elif chosen is remove_action:
            self._recents.remove(entry.path)
            self.refresh()

    def _show_help(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "How AirSizer Pro sizes",
            "1. Load the schedule HAPExt produced (.xlsx or .csv).\n"
            "2. For each subspace, pick a diffuser type — only the inputs that "
            "type takes stay enabled.\n"
            "3. Sizing reads the TECNALCO catalog. A value read between two "
            "catalog entries is flagged as interpolated; inputs no cell can "
            "satisfy report no valid selection rather than a guess.\n"
            "4. Review the roll-up, choose the columns you want, and export — "
            "the file auto-versions so nothing is overwritten.",
        )

"""Page 1 — Home: hero + feature band on the left, Quick Start and Recent
Projects on the right (mockup: normal scenario/main screen.png).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..widgets import RecentProjectsPanel, card, label


class HeroArt(QWidget):
    """Abstract light-blue building silhouette echoing the mockup artwork."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        fill = QColor("#DCE8F8")
        line = QColor("#9DB8DE")

        roof = QPolygonF(
            [QPointF(0, h * 0.85), QPointF(w * 0.98, h * 0.15),
             QPointF(w * 0.98, h * 0.85)]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawPolygon(roof)

        painter.setPen(QPen(line, 1))
        body_top, body_bot = h * 0.45, h * 0.85
        painter.drawRect(int(w * 0.12), int(body_top), int(w * 0.72), int(body_bot - body_top))
        for i in range(1, 8):  # column lines
            x = w * 0.12 + (w * 0.72) * i / 8
            painter.drawLine(int(x), int(body_top), int(x), int(body_bot))
        painter.drawLine(int(w * 0.12), int(h * 0.65), int(w * 0.84), int(h * 0.65))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#7FA86B"))
        painter.drawEllipse(QPointF(w * 0.06, h * 0.93), 7, 7)


class _QuickStartCard(QFrame):
    def __init__(self, icon_color: str, title: str, body: str, enabled: bool):
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        self.setEnabled(enabled)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(8)

        icon = QLabel("≋" if enabled else "▦")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"background: {icon_color}; color: white; border-radius: 10px;"
            "font-size: 20px; font-weight: 800;"
        )
        lay.addWidget(icon)
        lay.addWidget(label(title, "H2"))
        body_lbl = label(body if enabled else body + "  (coming soon)", "Small", wrap=True)
        lay.addWidget(body_lbl)
        arrow = label("→", "H2")
        arrow.setAlignment(Qt.AlignRight)
        lay.addWidget(arrow)


class _FeatureChip(QWidget):
    def __init__(self, title: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        ring = QLabel()
        ring.setFixedSize(34, 34)
        ring.setStyleSheet(
            "border: 2px solid rgba(255,255,255,0.85); border-radius: 17px;"
        )
        lay.addWidget(ring, 0, Qt.AlignHCenter)
        chip_label = QLabel(title)
        chip_label.setObjectName("FeatureChipTitle")
        chip_label.setAlignment(Qt.AlignCenter)
        chip_label.setWordWrap(True)
        lay.addWidget(chip_label)


class HomePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(24)

        # ---------------- left: hero + feature band
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addSpacing(14)
        left.addWidget(label("Welcome to", "Muted"))
        title = QLabel(
            f'<span style="color:{theme.TEXT}">Mirage </span>'
            f'<span style="color:{theme.BLUE}">AEC</span>'
        )
        title.setObjectName("H1")
        left.addWidget(title)
        dots = label("▬ ▪", "Muted")
        dots.setStyleSheet(f"color: {theme.BLUE}; font-size: 10px;")
        left.addWidget(dots)
        left.addWidget(
            label(
                "Powerful tools for HVAC design and analysis.\n"
                "Simplify your workflow with intelligent\n"
                "automation and precise calculations.",
                "Muted",
            )
        )
        left.addWidget(HeroArt(), 1)

        band = QFrame()
        band.setObjectName("FeatureBand")
        band_lay = QHBoxLayout(band)
        band_lay.setContentsMargins(18, 4, 18, 4)
        for feature in (
            "Accurate\nCalculations",
            "Smart\nAutomation",
            "Seamless\nIntegration",
            "Reliable\nResults",
        ):
            band_lay.addWidget(_FeatureChip(feature))
        left.addWidget(band)
        root.addLayout(left, 11)

        # ---------------- right: quick start + recents
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(label("Quick Start", "H2"))

        cards_row = QGridLayout()
        cards_row.setSpacing(12)
        hapext_card = _QuickStartCard(
            theme.BLUE, "HAPExt", "Load, analyze and optimize HAP models with ease.", True
        )
        hapext_card.mousePressEvent = lambda e: self._ctx.go_upload()
        airsizer_card = _QuickStartCard(
            "#3AA655", "AirSizer Pro", "Design and analyze duct systems efficiently.", False
        )
        cards_row.addWidget(hapext_card, 0, 0)
        cards_row.addWidget(airsizer_card, 0, 1)
        right.addLayout(cards_row)

        self.recents_panel = RecentProjectsPanel(ctx.recents)
        self.recents_panel.open_requested.connect(ctx.open_recent)
        right.addWidget(self.recents_panel, 1)
        root.addLayout(right, 9)

    def refresh(self) -> None:
        self.recents_panel.refresh()

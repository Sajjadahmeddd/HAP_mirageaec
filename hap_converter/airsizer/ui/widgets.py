"""Shared building blocks for the AirSizer screens.

Reuses the HAPExt `card`/`label` helpers so both modules render from one set
of design tokens.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hap_converter.ui.widgets import card, label  # noqa: F401  (re-exported)

from ..engine.config import ResultColumn


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def read_only_field(text: str = "", object_name: str = "ReadOnlyField") -> QLabel:
    field = QLabel(text)
    field.setObjectName(object_name)
    field.setAlignment(Qt.AlignCenter)
    return field


class StepChips(QWidget):
    """The four-step wizard bar: pills joined by a hairline connector."""

    def __init__(self, steps: list[str]):
        super().__init__()
        self._chips: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for index, text in enumerate(steps):
            if index:
                line = QFrame()
                line.setObjectName("StepLine")
                lay.addWidget(line, 1)
            chip = QLabel(f"{index + 1} {text}")
            chip.setObjectName("WizardStep")
            chip.setAlignment(Qt.AlignCenter)
            chip.setProperty("stepState", "pending")
            self._chips.append(chip)
            lay.addWidget(chip, 6)
        self.set_step(1)

    def set_step(self, current: int) -> None:
        """Steps before `current` read as done, `current` as active (1-based)."""
        for index, chip in enumerate(self._chips, start=1):
            if index < current:
                state = "done"
            elif index == current:
                state = "active"
            else:
                state = "pending"
            chip.setProperty("stepState", state)
            repolish(chip)


class ColumnPicker(QToolButton):
    """Jira-style show/hide toggles over the results table."""

    changed = Signal(list)   # the visible column keys, in config order

    def __init__(self, columns: tuple[ResultColumn, ...], visible: list[str]):
        super().__init__()
        self.setObjectName("ColumnPicker")
        self.setText("‖‖")
        self.setToolTip("Show or hide columns")
        self.setCursor(Qt.PointingHandCursor)
        self.setPopupMode(QToolButton.InstantPopup)
        self._columns = columns
        self._visible = list(visible)

        self._menu = QMenu(self)
        self._menu.setToolTipsVisible(True)
        self._actions = {}
        for column in columns:
            action = self._menu.addAction(column.label)
            action.setCheckable(True)
            action.setChecked(column.key in self._visible or column.locked)
            if column.locked:
                action.setEnabled(False)
                action.setToolTip("Always shown")
            action.toggled.connect(lambda _checked, key=column.key: self._toggle(key))
            self._actions[column.key] = action
        self.setMenu(self._menu)

    def _toggle(self, key: str) -> None:
        checked = self._actions[key].isChecked()
        if checked and key not in self._visible:
            self._visible.append(key)
        elif not checked and key in self._visible:
            self._visible.remove(key)
        self.changed.emit(self.visible())

    def visible(self) -> list[str]:
        """Visible keys in config order, so the table never reshuffles."""
        chosen = set(self._visible)
        return [c.key for c in self._columns if c.key in chosen or c.locked]

    def set_visible(self, keys: list[str]) -> None:
        self._visible = list(keys)
        for key, action in self._actions.items():
            action.blockSignals(True)
            action.setChecked(key in self._visible or self._columns_locked(key))
            action.blockSignals(False)

    def _columns_locked(self, key: str) -> bool:
        return any(c.key == key and c.locked for c in self._columns)


class Banner(QFrame):
    """One-line notice above the outputs (interpolation / no valid selection)."""

    def __init__(self, object_name: str, text_object_name: str):
        super().__init__()
        self.setObjectName(object_name)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        self._text = QLabel("")
        self._text.setObjectName(text_object_name)
        self._text.setWordWrap(True)
        lay.addWidget(self._text, 1)
        self.hide()

    def show_text(self, text: str) -> None:
        self._text.setText(text)
        self.setVisible(bool(text))


def field_column(caption: str, value: str = "") -> tuple[QVBoxLayout, QLabel]:
    """A caption above a read-only value box (the schedule values panel)."""
    column = QVBoxLayout()
    column.setSpacing(4)
    title = QLabel(caption)
    title.setObjectName("FieldCaption")
    title.setAlignment(Qt.AlignCenter)
    column.addWidget(title)
    field = read_only_field(value)
    column.addWidget(field)
    return column, field

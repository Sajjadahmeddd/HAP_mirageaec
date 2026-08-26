"""Per-subspace sizing panel (Figma: "sizing calculation input page",
"after entering input", "deriving output").

The schedule's values for the chosen subspace sit read-only across the top.
Picking a diffuser type enables exactly the inputs that type takes and greys
the rest to NA — the input matrix decides, not this file. Sizing reads the
catalogue and fills the three outputs, flagging a value that had to be
interpolated between two catalogue entries.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..engine import pipeline
from ..engine.config import Config
from ..engine.models import SizingInput, SizingResult, Space
from .widgets import Banner, field_column, label, repolish

# The form's fixed running order (Figma). A type that does not take an input
# still shows its row, greyed to NA, so the form never jumps about.
INPUT_ORDER = (
    "no_of_outlets",
    "velocity",
    "nc",
    "slot_width",
    "no_of_slots",
    "grille_height",
    "bar_pitch",
    "deflection",
)

BLANK = "--"
NOT_APPLICABLE = "NA"
PENDING = "Yet to Calculate"


class SizingDialog(QDialog):
    """Size one subspace. `saved` fires when the engineer commits."""

    saved = Signal(int, object, object)   # row, SizingInput, SizingResult

    def __init__(
        self,
        config: Config,
        spaces: list[Space],
        row: int,
        saved_inputs: dict[int, SizingInput],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Air diffuser sizing")
        self.setModal(True)
        self.setMinimumSize(1040, 620)

        self._config = config
        self._saved = saved_inputs if saved_inputs is not None else {}
        self._spaces = [s for s in spaces if pipeline.sizable(s)]
        self._names = {s.row: s.name for s in self._spaces}
        self._result: SizingResult | None = None
        self._loading = False
        self._current_row = self._spaces[0].row if self._spaces else 0

        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(lambda: self.saved_hint.setText(""))

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)
        root.addWidget(self._build_form(), 11)
        root.addWidget(self._build_side(), 9)

        self._select_row(row)

    # ------------------------------------------------------------ left panel
    def _build_form(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SizingPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(12)

        picker = QHBoxLayout()
        picker.setSpacing(8)
        title = QLabel("Zone Name / Space Name")
        title.setObjectName("SizingLabel")
        picker.addWidget(title)
        self.space_combo = QComboBox()
        self.space_combo.setCursor(Qt.PointingHandCursor)
        for space in self._spaces:
            self.space_combo.addItem(space.name, space.row)
        self.space_combo.currentIndexChanged.connect(self._on_space_changed)
        picker.addWidget(self.space_combo, 1)
        picker.addWidget(self._build_stepper())
        self.position_label = QLabel("")
        self.position_label.setObjectName("SpacePosition")
        picker.addWidget(self.position_label)
        bolt = QLabel("⚡")
        bolt.setToolTip("Values below come from the HAPExt schedule")
        picker.addWidget(bolt)
        lay.addLayout(picker)

        values = QHBoxLayout()
        values.setSpacing(12)
        self._value_fields = {}
        for key, caption in (
            ("floor_area", "Floor Area (m²)"),
            ("total_coil", "Total Coil Load (KW)"),
            ("sens_coil", "Sens Coil Load (KW)"),
            ("air_flow", "Air Flow (L/s)"),
        ):
            column, field = field_column(caption)
            self._value_fields[key] = field
            values.addLayout(column)
        lay.addLayout(values)

        lay.addSpacing(4)
        self.type_combo = QComboBox()
        self.type_combo.setCursor(Qt.PointingHandCursor)
        self.type_combo.addItem(BLANK, "")
        for spec in self._config.diffusers.values():
            self.type_combo.addItem(spec.label, spec.key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        lay.addLayout(self._form_row("Diffuser Type", self.type_combo))

        self._controls: dict[str, QWidget] = {}
        for key in INPUT_ORDER:
            spec = self._config.inputs[key]
            control = self._make_control(spec.kind)
            self._controls[key] = control
            lay.addLayout(self._form_row(spec.title(), control))
        lay.addStretch(1)
        return panel

    def _build_stepper(self) -> QWidget:
        """The up/down pair that walks the subspaces without leaving the panel."""
        box = QFrame()
        box.setObjectName("SpinnerBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.prev_btn = QToolButton()
        self.prev_btn.setObjectName("SpinBtn")
        self.prev_btn.setText("▲")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setToolTip("Previous subspace (Alt+Up)")
        self.prev_btn.setShortcut("Alt+Up")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        lay.addWidget(self.prev_btn)

        self.next_btn = QToolButton()
        self.next_btn.setObjectName("SpinBtn")
        self.next_btn.setText("▼")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setToolTip("Next subspace (Alt+Down)")
        self.next_btn.setShortcut("Alt+Down")
        self.next_btn.clicked.connect(lambda: self._step(1))
        lay.addWidget(self.next_btn)
        return box

    @staticmethod
    def _form_row(caption: str, control: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        text = QLabel(caption)
        text.setObjectName("SizingLabel")
        text.setMinimumWidth(190)
        row.addWidget(text)
        row.addWidget(control, 1)
        return row

    def _make_control(self, kind: str) -> QWidget:
        if kind == "count":
            control = QLineEdit()
            control.setValidator(QIntValidator(1, 999, self))
            control.setPlaceholderText(NOT_APPLICABLE)
            control.textChanged.connect(self._on_input_changed)
        else:
            control = QComboBox()
            control.setCursor(Qt.PointingHandCursor)
            control.currentIndexChanged.connect(self._on_input_changed)
        return control

    # ----------------------------------------------------------- right panel
    def _build_side(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SizingSide")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        self.diagram_frame = QFrame()
        self.diagram_frame.setObjectName("DiagramFrame")
        diagram_lay = QVBoxLayout(self.diagram_frame)
        diagram_lay.setContentsMargins(10, 10, 10, 10)
        self.diagram = QLabel("Select a diffuser type")
        self.diagram.setObjectName("Small")
        self.diagram.setAlignment(Qt.AlignCenter)
        self.diagram.setMinimumHeight(170)
        diagram_lay.addWidget(self.diagram)
        lay.addWidget(self.diagram_frame)

        self.sizing_btn = QPushButton("Sizing")
        self.sizing_btn.setObjectName("SizingAction")
        self.sizing_btn.setCursor(Qt.PointingHandCursor)
        self.sizing_btn.setEnabled(False)
        self.sizing_btn.clicked.connect(self._run_sizing)
        lay.addWidget(self.sizing_btn, 0, Qt.AlignHCenter)

        self.interp_banner = Banner("InterpBanner", "InterpBannerText")
        lay.addWidget(self.interp_banner)
        self.fail_banner = Banner("FailBanner", "FailBannerText")
        lay.addWidget(self.fail_banner)

        self._outputs: dict[str, QLabel] = {}
        for key, caption in (
            ("lsm", "Output (l/s/m)"),
            ("throw", "Flow Throw (m)"),
            ("size", "Output (mmxmm)"),
        ):
            row = QHBoxLayout()
            row.setSpacing(12)
            text = QLabel(caption)
            text.setObjectName("SizingLabel")
            text.setMinimumWidth(140)
            row.addWidget(text)
            field = QLabel(PENDING)
            field.setObjectName("OutputField")
            field.setAlignment(Qt.AlignCenter)
            field.setProperty("outputState", "pending")
            field.setMinimumWidth(150)
            self._outputs[key] = field
            row.addWidget(field, 1)
            lay.addLayout(row)

        self.derived_label = QLabel("")
        self.derived_label.setObjectName("Small")
        self.derived_label.setAlignment(Qt.AlignRight)
        lay.addWidget(self.derived_label)
        lay.addStretch(1)

        self.saved_hint = QLabel("")
        self.saved_hint.setObjectName("SavedHint")
        self.saved_hint.setAlignment(Qt.AlignRight)
        lay.addWidget(self.saved_hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.save_btn = QPushButton("SAVE")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        buttons.addWidget(self.save_btn, 1)
        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("CloseAction")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn, 1)
        lay.addLayout(buttons)
        return panel

    # ---------------------------------------------------------------- state
    @property
    def row(self) -> int:
        return int(self.space_combo.currentData())

    def _space(self) -> Space:
        return next(s for s in self._spaces if s.row == self.row)

    def _select_row(self, row: int) -> None:
        index = self.space_combo.findData(row)
        self._loading = True
        self.space_combo.setCurrentIndex(max(0, index))
        self._loading = False
        self._load_space()

    def _step(self, delta: int) -> None:
        """Walk to the neighbouring subspace, keeping the panel open."""
        index = self.space_combo.currentIndex() + delta
        if 0 <= index < self.space_combo.count():
            self.space_combo.setCurrentIndex(index)

    def _on_space_changed(self, index: int) -> None:
        if self._loading:
            return
        target = self.space_combo.itemData(index)
        if target is None or int(target) == self._current_row:
            return
        if not self._confirm_leave():
            self._loading = True          # bounce back without reloading
            self.space_combo.setCurrentIndex(self.space_combo.findData(self._current_row))
            self._loading = False
            return
        self._load_space()

    def _is_dirty(self) -> bool:
        """A valid result is on screen that differs from what is stored."""
        if not (self._result and self._result.ok):
            return False
        stored = self._saved.get(self._current_row)
        current = self.sizing_input()
        return (
            stored is None
            or stored.diffuser != current.diffuser
            or stored.values != current.values
        )

    def _confirm_leave(self) -> bool:
        """Ask before dropping a sized-but-unsaved subspace. True = go ahead."""
        if not self._is_dirty():
            return True
        answer = QMessageBox.question(
            self,
            "Save this sizing?",
            f"{self._names.get(self._current_row, 'This subspace')} has been sized "
            "but not saved.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            self._commit()
        return True

    def _refresh_nav(self) -> None:
        """Arrow availability, the position readout, and a tick per saved space."""
        index = self.space_combo.currentIndex()
        count = self.space_combo.count()
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < count - 1)
        self.position_label.setText(f"{index + 1} of {count}")

        was_loading, self._loading = self._loading, True
        for position in range(count):
            row = int(self.space_combo.itemData(position))
            name = self._names[row]
            self.space_combo.setItemText(position, f"✓  {name}" if row in self._saved else name)
        self._loading = was_loading

    def _load_space(self) -> None:
        """Show the schedule values and any sizing already saved for this row."""
        self._loading = True
        space = self._space()
        self._current_row = space.row
        self._value_fields["floor_area"].setText(space.floor_area or "—")
        self._value_fields["total_coil"].setText(space.total_coil or "—")
        self._value_fields["sens_coil"].setText(space.sens_coil or "—")
        self._value_fields["air_flow"].setText(space.air_flow or "—")

        saved = self._saved.get(space.row)
        index = self.type_combo.findData(saved.diffuser if saved else "")
        self.type_combo.setCurrentIndex(max(0, index))
        self._apply_type(saved)
        self._loading = False
        self._clear_outputs()
        if saved:
            self._run_sizing()
        self._refresh_buttons()
        self._refresh_nav()

    def _on_type_changed(self, _index: int) -> None:
        if self._loading:
            return
        self._apply_type(None)
        self._clear_outputs()
        self._refresh_buttons()

    def _apply_type(self, saved: SizingInput | None) -> None:
        """Enable the inputs this diffuser takes; grey the rest to NA."""
        key = self.type_combo.currentData() or ""
        spec = self._config.diffusers.get(key)
        self._load_diagram(key)

        for input_key in INPUT_ORDER:
            control = self._controls[input_key]
            takes = bool(spec and spec.takes(input_key))
            previous = saved.get(input_key) if saved else ""
            control.blockSignals(True)
            if isinstance(control, QComboBox):
                control.clear()
                if takes:
                    control.addItem(BLANK, "")
                    for option in self._config.input_spec(input_key, spec).options:
                        control.addItem(option, option)
                    if previous:
                        position = control.findData(previous)
                        control.setCurrentIndex(position if position >= 0 else 0)
                else:
                    control.addItem(NOT_APPLICABLE, "")
            else:
                control.setText(previous if takes else "")
            control.setEnabled(takes)
            control.blockSignals(False)

    def _load_diagram(self, key: str) -> None:
        if not key:
            self.diagram.setPixmap(QPixmap())
            self.diagram.setText("Select a diffuser type")
            return
        path = self._config.diagram_path(key)
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        if pixmap.isNull():
            self.diagram.setPixmap(QPixmap())
            self.diagram.setText(self._config.diffuser(key).label)
            return
        self.diagram.setText("")
        self.diagram.setPixmap(
            pixmap.scaled(360, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _on_input_changed(self, *_args) -> None:
        if self._loading:
            return
        self._clear_outputs()
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.sizing_btn.setEnabled(bool(self.type_combo.currentData()))
        self.save_btn.setEnabled(bool(self._result and self._result.ok))

    # -------------------------------------------------------------- sizing
    def sizing_input(self) -> SizingInput:
        values = {}
        for input_key, control in self._controls.items():
            if not control.isEnabled():
                continue
            if isinstance(control, QComboBox):
                values[input_key] = str(control.currentData() or "")
            else:
                values[input_key] = control.text().strip()
        return SizingInput(diffuser=str(self.type_combo.currentData() or ""), values=values)

    def _set_output(self, key: str, text: str, state: str) -> None:
        field = self._outputs[key]
        field.setText(text)
        field.setProperty("outputState", state)
        repolish(field)

    def _clear_outputs(self) -> None:
        self._result = None
        for key in self._outputs:
            self._set_output(key, PENDING, "pending")
        self.derived_label.setText("")
        self.interp_banner.hide()
        self.fail_banner.hide()

    def _run_sizing(self) -> None:
        result = pipeline.size_space(self._space(), self.sizing_input(), self._config)
        self._result = result

        if not result.ok:
            for key in self._outputs:
                self._set_output(key, NOT_APPLICABLE, "na")
            self.derived_label.setText("")
            self.interp_banner.hide()
            self.fail_banner.show_text(result.message)
            self._refresh_buttons()
            return

        self.fail_banner.hide()
        state = "interpolated" if result.interpolated else "value"
        if result.group == "A":
            self._set_output("lsm", result.lsm, state)
            self._set_output("throw", result.throw, state)
            self._set_output("size", NOT_APPLICABLE, "na")
            self.derived_label.setText(
                f"Air outlet length {result.length_m} m  •  {result.pieces} pcs  •  NC {result.nc}"
            )
        else:
            self._set_output("lsm", NOT_APPLICABLE, "na")
            self._set_output("throw", result.throw, state)
            self._set_output("size", result.size, state)
            alternatives = f"  •  also {', '.join(result.alt_sizes)}" if result.alt_sizes else ""
            self.derived_label.setText(
                f"{result.outlets} outlet(s)  •  {result.velocity} m/s  •  NC {result.nc}{alternatives}"
            )

        if result.interpolated:
            self.interp_banner.show_text(
                "No exact match — interpolated value. Read between the two nearest "
                "catalogue entries."
            )
        else:
            self.interp_banner.hide()
        self._refresh_buttons()

    def _commit(self) -> None:
        """Hand the sizing to the app and remember it locally."""
        if not (self._result and self._result.ok):
            return
        sizing_input = self.sizing_input()
        self.saved.emit(self._current_row, sizing_input, self._result)
        self._saved[self._current_row] = sizing_input

    def _save(self) -> None:
        """SAVE keeps the panel open so the arrows can walk to the next subspace."""
        if not (self._result and self._result.ok):
            return
        self._commit()
        self._refresh_nav()
        self.saved_hint.setText("Saved ✓")
        self._hint_timer.start(2500)

    def reject(self) -> None:
        if self._confirm_leave():
            super().reject()

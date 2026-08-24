"""Per-subspace sizing panel (Figma: "sizing calculation input page",
"after entering input", "deriving output").

The schedule's values for the chosen subspace sit read-only across the top.
Picking a diffuser type enables exactly the inputs that type takes and greys
the rest to NA — the input matrix decides, not this file. Sizing reads the
catalogue and fills the three outputs, flagging a value that had to be
interpolated between two catalogue entries.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
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
        self._saved = saved_inputs or {}
        self._spaces = [s for s in spaces if pipeline.sizable(s)]
        self._result: SizingResult | None = None
        self._loading = False

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
        picker.setSpacing(10)
        title = QLabel("Zone Name / Space Name")
        title.setObjectName("SizingLabel")
        picker.addWidget(title)
        self.space_combo = QComboBox()
        self.space_combo.setCursor(Qt.PointingHandCursor)
        for space in self._spaces:
            self.space_combo.addItem(space.name, space.row)
        self.space_combo.currentIndexChanged.connect(self._on_space_changed)
        picker.addWidget(self.space_combo, 1)
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
        self.space_combo.setCurrentIndex(max(0, index))
        self._load_space()

    def _on_space_changed(self, _index: int) -> None:
        if not self._loading:
            self._load_space()

    def _load_space(self) -> None:
        """Show the schedule values and any sizing already saved for this row."""
        self._loading = True
        space = self._space()
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

    def _save(self) -> None:
        if self._result and self._result.ok:
            self.saved.emit(self.row, self.sizing_input(), self._result)
            self.accept()

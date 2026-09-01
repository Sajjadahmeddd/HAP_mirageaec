"""UI integration: load a schedule, size a subspace through the panel, and
carry it to the export — the path a user actually walks.

Runs on Qt's offscreen platform so it works in CI and on a headless build
machine.
"""

import csv
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from hap_converter.airsizer.ui.sizing_dialog import (  # noqa: E402
    NOT_APPLICABLE,
    PENDING,
    SizingDialog,
)
from hap_converter.engine import config as hapext_config  # noqa: E402
from hap_converter.ui.app_window import AppWindow  # noqa: E402

MAPPING_PATH = Path(__file__).resolve().parents[1] / "config" / "mapping.json"

HEADER = [
    "Zone Name / Space Name", "Floor Area (m²)", "Total Coil Load (KW)",
    "Sens Coil Load (KW)", "Air Flow (L/s)", "Coil Entering DB / WB (°C)",
    "Coil Leaving DB / WB (°C)", "Water Flow @9.0 K (L/s)", "W/m2", "Qty",
    "Total KW", "ESP", "FCU Types", "Remarks",
]
ROWS = [
    ["#01-9F-Corridor1", "172.3", "13.2", "12.6", "", "", "", "", "", "", "", "", "", ""],
    ["#01A-9FCorridor1", "154.4", "", "", "868", "", "", "", "", "", "", "", "", ""],
    ["#01D-9F-Lift Lobby", "23.9", "2.8", "2.7", "", "", "", "", "", "", "", "", "", ""],
    ["#01D-9F-Lift Lobby", "23.9", "", "", "218", "", "", "", "", "", "", "", "", ""],
]

LINEAR_BAR = {"velocity": "2.5", "nc": "15", "grille_height": "150", "bar_pitch": "6"}


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def schedule(tmp_path):
    path = tmp_path / "System Design.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(ROWS)
    return path


@pytest.fixture
def window(qt_app, air_config, schedule, tmp_path, monkeypatch):
    monkeypatch.setattr(AppWindow, "air_staging_dir", staticmethod(lambda: str(tmp_path)))
    app_window = AppWindow(hapext_config.load(MAPPING_PATH), air_config=air_config)
    assert app_window.load_air_schedule(str(schedule))
    return app_window


def size_last_subspace(window, values=LINEAR_BAR, diffuser="linear_bar"):
    row = window.air_spaces[-1].row
    dialog = SizingDialog(window.air_config, window.air_spaces, row, window.air_inputs)
    dialog.saved.connect(window.record_sizing)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(diffuser))
    for key, value in values.items():
        control = dialog._controls[key]
        control.setCurrentIndex(control.findData(value))
    dialog._run_sizing()
    return dialog, row


# ------------------------------------------------------------------ loading
def test_the_wizard_shows_every_schedule_row(window):
    assert window.air_wizard_page.table.rowCount() == len(ROWS)
    window.air_wizard_page.refresh()
    assert window.air_wizard_page.table.item(0, 0).text() == "#01-9F-Corridor1"
    # subspace names are stepped in under their unit header
    assert window.air_wizard_page.table.item(1, 0).text().startswith("      ")


def test_only_subspaces_offer_a_sizing_button(window):
    table = window.air_wizard_page.table
    action_column = table.columnCount() - 1
    assert table.cellWidget(0, action_column) is None      # unit header row
    assert table.cellWidget(1, action_column) is not None  # subspace


def test_the_space_picker_lists_only_sizable_rows(window):
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[-1].row, {}
    )
    names = [dialog.space_combo.itemText(i) for i in range(dialog.space_combo.count())]
    assert names == ["#01A-9FCorridor1", "#01D-9F-Lift Lobby"]


# ------------------------------------------------------------- the input matrix
def test_choosing_a_type_enables_only_its_inputs(window):
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[-1].row, {}
    )
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("linear_bar"))
    enabled = {key: control.isEnabled() for key, control in dialog._controls.items()}
    assert enabled == {
        "no_of_outlets": False, "velocity": True, "nc": True, "slot_width": False,
        "no_of_slots": False, "grille_height": True, "bar_pitch": True,
        "deflection": False,
    }
    assert dialog._controls["slot_width"].currentText() == NOT_APPLICABLE


def test_switching_type_reshapes_the_form(window):
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[-1].row, {}
    )
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("linear_slot"))
    assert dialog._controls["slot_width"].isEnabled() is True
    assert dialog._controls["velocity"].isEnabled() is False   # slot takes no velocity

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("grille"))
    assert dialog._controls["deflection"].isEnabled() is True
    assert dialog._controls["slot_width"].isEnabled() is False


def test_outputs_start_pending_and_fill_after_sizing(window):
    dialog, _row = size_last_subspace(window)
    assert dialog._outputs["lsm"].text() == "100"
    assert dialog._outputs["throw"].text() == "4.4"
    assert dialog._outputs["size"].text() == NOT_APPLICABLE   # linear: no mm x mm
    assert "2.18 m" in dialog.derived_label.text()


def test_changing_an_input_clears_a_stale_result(window):
    dialog, _row = size_last_subspace(window)
    control = dialog._controls["nc"]
    control.setCurrentIndex(control.findData("25"))
    assert dialog._outputs["lsm"].text() == PENDING
    assert dialog.save_btn.isEnabled() is False


def test_interpolated_result_raises_the_banner(window):
    dialog, _row = size_last_subspace(
        window,
        {"nc": "20", "slot_width": "20", "no_of_slots": "3"},
        diffuser="linear_slot",
    )
    assert dialog._outputs["lsm"].text() == "81.25"
    assert dialog.interp_banner.isHidden() is False
    assert dialog.fail_banner.isHidden() is True


def test_no_valid_selection_blocks_save_and_explains(window):
    dialog, _row = size_last_subspace(
        window,
        {"nc": "15", "slot_width": "16", "no_of_slots": "2"},
        diffuser="linear_slot",
    )
    assert dialog.fail_banner.isHidden() is False
    assert dialog.save_btn.isEnabled() is False
    assert dialog._outputs["lsm"].text() == NOT_APPLICABLE


# ------------------------------------------------------------ carrying through
def test_saving_records_the_sizing_and_marks_the_row(window):
    dialog, row = size_last_subspace(window)
    dialog._save()
    assert window.air_results[row].ok is True
    assert window.air_inputs[row].diffuser == "linear_bar"

    window.air_wizard_page.refresh()
    action_column = window.air_wizard_page.table.columnCount() - 1
    holder = window.air_wizard_page.table.cellWidget(3, action_column)
    assert holder.findChild(QPushButton).text() == "Preview"


def test_review_then_generate_writes_the_visible_columns(window, tmp_path):
    dialog, _row = size_last_subspace(window)
    dialog._save()

    window.go_air_review()
    review = window.air_review_page
    headers = [review.table.horizontalHeaderItem(i).text()
               for i in range(review.table.columnCount())]
    assert headers[:2] == ["Zone Name / Space Name", "Floor Area (m²)"]
    assert "Air Outlet Length (m) / Nos" in headers
    assert headers[-1] == "Sizing"          # preview column, stage 3 only

    review._generate()
    assert review._stage == 4
    assert review._generated.name == "System Design - sized.xlsx"
    assert review._generated.is_file()

    import openpyxl

    sheet = openpyxl.load_workbook(review._generated).active
    assert sheet["A1"].value == "AIR DIFFUSER SIZING"
    assert sheet.cell(row=4, column=1).value == "Zone Name / Space Name"


def test_hiding_a_column_removes_it_from_the_table(window):
    window.go_air_review()
    review = window.air_review_page
    review._on_columns_changed(["air_flow"])
    headers = [review.table.horizontalHeaderItem(i).text()
               for i in range(review.table.columnCount())]
    assert headers == ["Zone Name / Space Name", "Air Flow (L/s)", "Sizing"]


def test_review_is_unreachable_without_a_schedule(qt_app, air_config):
    empty = AppWindow(hapext_config.load(MAPPING_PATH), air_config=air_config)
    empty.go_air_review()
    assert empty.stack.currentWidget() is not empty.air_review_page


def test_the_airsizer_tab_is_disabled_when_its_config_is_missing(qt_app):
    disabled = AppWindow(
        hapext_config.load(MAPPING_PATH), air_config=None, air_error="catalogs missing"
    )
    button = disabled.tab_bar._buttons["AirSizer Pro"]
    assert button.isEnabled() is False
    assert button.toolTip() == "catalogs missing"


# ------------------------------------------------------- subspace stepper
def test_arrows_walk_the_subspaces_without_leaving_the_panel(window):
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[1].row, {}
    )
    assert dialog.position_label.text() == "1 of 2"
    assert dialog.prev_btn.isEnabled() is False    # already at the first
    assert dialog.next_btn.isEnabled() is True

    dialog._step(1)
    assert dialog.position_label.text() == "2 of 2"
    assert dialog._value_fields["air_flow"].text() == "218"
    assert dialog.prev_btn.isEnabled() is True
    assert dialog.next_btn.isEnabled() is False    # last one

    dialog._step(-1)
    assert dialog.position_label.text() == "1 of 2"
    assert dialog._value_fields["air_flow"].text() == "868"


def test_stepping_past_either_end_does_nothing(window):
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[1].row, {}
    )
    dialog._step(-1)
    assert dialog.position_label.text() == "1 of 2"
    dialog._step(1)
    dialog._step(1)
    assert dialog.position_label.text() == "2 of 2"


def test_save_keeps_the_panel_open_so_the_arrows_stay_usable(window):
    dialog, row = size_last_subspace(window)
    dialog._save()
    assert dialog.result() != SizingDialog.Accepted   # not closed
    assert dialog.saved_hint.text() == "Saved ✓"
    assert window.air_results[row].ok is True

    dialog._step(-1)                                 # still navigable
    assert dialog.position_label.text() == "1 of 2"


def test_a_saved_subspace_is_ticked_in_the_picker(window):
    dialog, _row = size_last_subspace(window)
    dialog._save()
    names = [dialog.space_combo.itemText(i) for i in range(dialog.space_combo.count())]
    assert names == ["#01A-9FCorridor1", "✓  #01D-9F-Lift Lobby"]


def test_stepping_back_restores_the_saved_sizing(window):
    dialog, _row = size_last_subspace(window)
    dialog._save()
    dialog._step(-1)
    assert dialog._outputs["lsm"].text() == PENDING   # the other space is untouched
    dialog._step(1)
    assert dialog._outputs["lsm"].text() == "100"     # comes back sized
    assert dialog.type_combo.currentText() == "Linear Bar Grille"


def test_leaving_an_unsaved_sizing_asks_first(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog, _row = size_last_subspace(window)         # sized, deliberately not saved
    assert dialog._is_dirty() is True

    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: (asked.append(1), QMessageBox.Cancel)[1],
    )
    dialog._step(-1)
    assert asked, "stepping away from unsaved work must prompt"
    assert dialog.position_label.text() == "2 of 2"   # Cancel stayed put


def test_choosing_save_in_the_prompt_commits_then_moves(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog, row = size_last_subspace(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Save)
    dialog._step(-1)
    assert window.air_results[row].ok is True
    assert dialog.position_label.text() == "1 of 2"


def test_discarding_moves_on_without_recording(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog, row = size_last_subspace(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    dialog._step(-1)
    assert row not in window.air_results
    assert dialog.position_label.text() == "1 of 2"


def test_a_clean_panel_steps_without_asking(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def refuse(*args, **kwargs):
        raise AssertionError("must not prompt when nothing is unsaved")

    monkeypatch.setattr(QMessageBox, "question", refuse)
    dialog = SizingDialog(
        window.air_config, window.air_spaces, window.air_spaces[1].row, {}
    )
    dialog._step(1)
    assert dialog.position_label.text() == "2 of 2"

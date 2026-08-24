"""End to end: read a HAPExt schedule, size a subspace, and check that a
selection which cannot be made comes back as a result rather than an
exception.
"""

import csv

import pytest

from hap_converter.airsizer.engine import pipeline
from hap_converter.airsizer.engine.models import SizingInput, Space
from hap_converter.airsizer.engine.pipeline import SourceError

HAPEXT_HEADER = [
    "Zone Name / Space Name", "Floor Area (m²)", "Total Coil Load (KW)",
    "Sens Coil Load (KW)", "Air Flow (L/s)", "Coil Entering DB / WB (°C)",
    "Coil Leaving DB / WB (°C)", "Water Flow @9.0 K (L/s)", "W/m2", "Qty",
    "Total KW", "ESP", "FCU Types", "Remarks",
]

HAPEXT_ROWS = [
    ["#01-9F-Corridor1(LIFT)", "172.3", "13.2", "12.6", "", "23.5 / 16.7",
     "13.2 / 12.5", "0.24", "76.61", "", "13.2", "", "", ""],
    ["#01A-9FCorridor1(LIFT)", "154.4", "", "", "868", "", "", "", "", "", "", "", "", ""],
    ["#01B-9FElec. Room", "6.1", "", "", "115", "", "", "", "", "", "", "", "", ""],
    ["#01C-9FService Corr", "11.8", "", "", "48", "", "", "", "", "", "", "", "", ""],
    ["#01D-9F-Lift Lobby", "23.9", "2.8", "2.7", "", "23.8 / 17.1",
     "13.7 / 12.7", "0.13", "117.15", "", "2.8", "", "", ""],
    ["#01D-9F-Lift Lobby", "23.9", "", "", "218", "", "", "", "", "", "", "", "", ""],
]


@pytest.fixture
def schedule_csv(tmp_path):
    """A HAPExt CSV: unit header rows followed by their subspace rows."""
    path = tmp_path / "System Design.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HAPEXT_HEADER)
        writer.writerows(HAPEXT_ROWS)
    return path


@pytest.fixture
def schedule_xlsx(tmp_path, air_config):
    """The same schedule as the downloaded workbook: header block, then row 6."""
    from hap_converter.engine.synthesizer import LOGO_KEY
    from hap_converter.engine.xlsx_exporter import write_fcu_xlsx

    details = {
        "project": "Sample Tower", "project_no": "P-01", "stage": "IFC",
        "discipline": "MEP", "author": "AB", "checked": "CD",
        "revision": "A", "date": "24.08.2026", LOGO_KEY: "",
    }
    target = tmp_path / "schedule.xlsx"
    write_fcu_xlsx(details, HAPEXT_HEADER, HAPEXT_ROWS, target)
    return target


# --------------------------------------------------------------- reading input
def test_loads_every_schedule_row_from_csv(schedule_csv, air_config):
    spaces = pipeline.load_spaces(schedule_csv, air_config)
    assert len(spaces) == 6
    assert spaces[0].name == "#01-9F-Corridor1(LIFT)"
    assert spaces[0].is_unit is True         # carries the coil load
    assert spaces[1].is_unit is False
    assert spaces[1].air_flow == "868"
    assert spaces[-1].air_flow == "218"


def test_loads_the_downloaded_workbook_past_its_header_block(schedule_xlsx, air_config):
    spaces = pipeline.load_spaces(schedule_xlsx, air_config)
    assert [s.name for s in spaces] == [r[0] for r in HAPEXT_ROWS]
    assert spaces[1].air_flow == "868"


def test_only_subspace_rows_are_sizable(schedule_csv, air_config):
    spaces = pipeline.load_spaces(schedule_csv, air_config)
    assert [s.name for s in spaces if pipeline.sizable(s)] == [
        "#01A-9FCorridor1(LIFT)", "#01B-9FElec. Room",
        "#01C-9FService Corr", "#01D-9F-Lift Lobby",
    ]


def test_a_file_that_is_not_a_schedule_is_rejected(tmp_path, air_config):
    stray = tmp_path / "notes.csv"
    stray.write_text("hello,world\n1,2\n", encoding="utf-8")
    with pytest.raises(SourceError, match="No column header row"):
        pipeline.load_spaces(stray, air_config)


def test_an_unsupported_file_type_is_rejected(tmp_path, air_config):
    stray = tmp_path / "report.pdf"
    stray.write_bytes(b"%PDF-1.4")
    with pytest.raises(SourceError, match="expected the HAPExt"):
        pipeline.load_spaces(stray, air_config)


# ------------------------------------------------------------------- sizing
def test_group_a_sizing_derives_length_and_pieces(space, air_config):
    # 218 L/s. Bar grille p.14, Bp 6 mm, width 150, NC 15 -> 100 L/s/m exactly.
    # 218 / 100 = 2.18 m -> 3 one-metre pieces. 2.18 m falls in the 3-5 m
    # correction band: throw x1.1 (4.0 -> 4.4) and NC +4 (15 -> 19).
    result = pipeline.size_space(
        space,
        SizingInput("linear_bar", {"velocity": "2.5", "nc": "15",
                                   "grille_height": "150", "bar_pitch": "6"}),
        air_config,
    )
    assert result.ok is True
    assert result.group == "A"
    assert result.interpolated is False
    assert result.lsm == "100"
    assert result.length_m == "2.18"
    assert result.pieces == 3
    assert result.throw == "4.4"
    assert result.nc == "19"
    assert result.status == "Read"


def test_group_b_sizing_reports_the_selected_size(space, air_config):
    result = pipeline.size_space(
        space,
        SizingInput("square", {"no_of_outlets": "1", "velocity": "2.5", "nc": "25"}),
        air_config,
    )
    assert result.ok is True
    assert result.group == "B"
    assert result.size == "375 x 375"
    assert result.outlets == 1
    assert result.length_m == ""      # area diffusers have no run length


def test_splitting_across_outlets_selects_a_smaller_size(space, air_config):
    single = pipeline.size_space(
        space, SizingInput("square", {"no_of_outlets": "1", "velocity": "2.5", "nc": "25"}),
        air_config,
    )
    paired = pipeline.size_space(
        space, SizingInput("square", {"no_of_outlets": "2", "velocity": "2.5", "nc": "25"}),
        air_config,
    )
    assert paired.size == "225 x 225"
    assert paired.outlets == 2
    assert single.size != paired.size


def test_flow_bar_slots_share_the_airflow(space, air_config):
    one = pipeline.size_space(
        space,
        SizingInput("flow_bar", {"velocity": "2.5", "nc": "45",
                                 "slot_width": "76", "no_of_slots": "1"}),
        air_config,
    )
    two = pipeline.size_space(
        space,
        SizingInput("flow_bar", {"velocity": "2.5", "nc": "45",
                                 "slot_width": "76", "no_of_slots": "2"}),
        air_config,
    )
    # 302 l/s-m per slot; two slots carry 604, halving the run
    assert one.lsm == "302"
    assert two.lsm == "604"
    assert one.length_m == "0.72"
    assert two.length_m == "0.36"


def test_interpolated_result_is_flagged_for_the_banner(space, air_config):
    result = pipeline.size_space(
        space,
        SizingInput("linear_slot", {"nc": "20", "slot_width": "20", "no_of_slots": "3"}),
        air_config,
    )
    assert result.ok is True
    assert result.interpolated is True
    assert result.status == "Interpolated"
    assert result.lsm == "81.25"


# --------------------------------------------------------- failures are results
def test_no_valid_selection_is_a_result_not_an_exception(space, air_config):
    result = pipeline.size_space(
        space,
        SizingInput("linear_slot", {"nc": "15", "slot_width": "16", "no_of_slots": "2"}),
        air_config,
    )
    assert result.ok is False
    assert result.status == "No valid selection"
    assert "below the quietest" in result.message


def test_missing_inputs_name_the_fields_still_to_fill(space, air_config):
    result = pipeline.size_space(
        space, SizingInput("linear_slot", {"nc": "20"}), air_config
    )
    assert result.ok is False
    assert "Slot Width" in result.message
    assert "Number of Slot" in result.message


def test_a_subspace_without_air_flow_cannot_be_sized(air_config):
    result = pipeline.size_space(
        Space(name="#Empty", air_flow=""),
        SizingInput("square", {"no_of_outlets": "1", "velocity": "2.5", "nc": "25"}),
        air_config,
    )
    assert result.ok is False
    assert "not a number" in result.message


def test_unreadable_air_flow_is_reported_not_raised(air_config):
    result = pipeline.size_space(
        Space(name="#Odd", air_flow="n/a"),
        SizingInput("square", {"no_of_outlets": "1", "velocity": "2.5", "nc": "25"}),
        air_config,
    )
    assert result.ok is False
    assert "n/a" in result.message

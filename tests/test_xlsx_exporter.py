import openpyxl

from hap_converter.engine.xlsx_exporter import write_fcu_xlsx

DETAILS = {
    "project": "Avarra by Palace",
    "project_no": "MLD",
    "stage": "100 % DD",
    "discipline": "MEP",
    "author": "SA",
    "checked": "FA",
    "revision": "2",
    "date": "20.04.2026",
}

HEADER = [f"Col {i}" for i in range(1, 15)]
DATA = [
    ["#01-Corridor", "178.2", "9.2", "8.6", "", "23.5 / 16.7", "13.2 / 12.5",
     "0.24", "51.63", "", "9.2", "", "", ""],
    ["#01-Corridor", "178.2", "", "", "689", "", "", "", "", "", "", "", "", ""],
]


def _load(tmp_path):
    target = tmp_path / "schedule.xlsx"
    write_fcu_xlsx(DETAILS, HEADER, DATA, target)
    return openpyxl.load_workbook(target)["FCU SCHEDULE"]


def test_row1_is_two_merged_zones(tmp_path):
    ws = _load(tmp_path)
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert "A1:F1" in merged  # FCU SCHEDULE, no column lines inside
    assert "G1:N1" in merged  # mirage mark, no column lines inside
    assert ws["A1"].value == "FCU SCHEDULE"
    assert ws["G1"].value == "mirage"


def test_detail_rows_merged_values(tmp_path):
    ws = _load(tmp_path)
    merged = {str(r) for r in ws.merged_cells.ranges}
    for row in range(2, 6):
        assert f"B{row}:F{row}" in merged
        assert f"H{row}:N{row}" in merged
    assert ws["A2"].value == "Project:" and ws["B2"].value == "Avarra by Palace"
    assert ws["G4"].value == "Revision:" and ws["H4"].value == "2"
    assert ws["G5"].value == "Date:" and ws["H5"].value == "20.04.2026"


def test_header_and_data_rows(tmp_path):
    ws = _load(tmp_path)
    assert [ws.cell(row=6, column=c).value for c in range(1, 15)] == HEADER
    assert ws["A7"].value == "#01-Corridor"
    assert ws["B7"].value == "178.2"  # string-exact, zero rounding
    assert ws["E8"].value == "689"
    assert ws.cell(row=7, column=5).value in ("", None)  # blanks stay blank

"""Reading the project block back off a schedule.

AirSizer offers these so an engineer does not retype nine inputs that the
schedule they just loaded already carries.
"""

import openpyxl
import pytest
from PIL import Image

from hap_converter.engine.project_header import has_details, read_project_header
from hap_converter.engine.xlsx_exporter import write_fcu_xlsx

DETAILS = {
    "project": "Avarra by Palace", "project_no": "MLD", "stage": "100 % DD",
    "discipline": "MEP", "author": "SA", "checked": "FA", "revision": "2",
    "date": "20.04.2026",
}
HEADER = [f"Col {i}" for i in range(1, 15)]
DATA = [["#01-Corridor", "178.2", "9.2", "8.6", "689", "", "", "", "", "", "", "", "", ""]]


@pytest.fixture
def logo(tmp_path):
    path = tmp_path / "client logo.png"
    Image.new("RGBA", (600, 200), (20, 90, 60, 255)).save(path)
    return path


@pytest.fixture
def schedule(tmp_path, logo):
    target = tmp_path / "schedule.xlsx"
    write_fcu_xlsx(dict(DETAILS, logo_path=str(logo)), HEADER, DATA, target)
    return target


def test_every_field_comes_back(schedule):
    details, _ = read_project_header(schedule)
    assert details == DETAILS
    assert has_details(details)


def test_the_logo_comes_back_as_an_image(schedule):
    import io
    _, blob = read_project_header(schedule)
    assert blob, "the embedded logo should be recoverable"
    assert Image.open(io.BytesIO(blob)).size == (600, 200)


def test_a_schedule_without_a_logo_reads_its_text_anyway(tmp_path):
    target = tmp_path / "no-logo.xlsx"
    write_fcu_xlsx(dict(DETAILS, logo_path=""), HEADER, DATA, target)
    details, blob = read_project_header(target)
    assert details == DETAILS
    assert blob is None


def test_someone_elses_spreadsheet_reads_as_nothing(tmp_path):
    """An engineer may load any workbook; that is not an error."""
    other = tmp_path / "other.xlsx"
    book = openpyxl.Workbook()
    book.active["A1"] = "Sheet somebody else made"
    book.active["A2"] = "Not a label we write"
    book.save(other)

    details, blob = read_project_header(other)
    assert details == {}
    assert blob is None
    assert not has_details(details)


def test_a_file_that_is_not_a_workbook_is_not_an_error(tmp_path):
    junk = tmp_path / "schedule.csv"
    junk.write_text("Zone Name / Space Name,Floor Area\n#01,10\n", encoding="utf-8")
    assert read_project_header(junk) == ({}, None)


def test_a_partly_filled_block_reports_what_it_has(tmp_path, logo):
    target = tmp_path / "partial.xlsx"
    write_fcu_xlsx(dict(DETAILS, logo_path=str(logo)), HEADER, DATA, target)
    book = openpyxl.load_workbook(target)
    book.active["B2"] = None          # clear Project
    book.save(target)

    details, _ = read_project_header(target)
    assert "project" not in details
    assert details["author"] == "SA"
    assert not has_details(details)   # so the form still asks for the gap

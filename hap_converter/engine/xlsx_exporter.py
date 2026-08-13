"""Excel (.xlsx) writer for the FCU schedule download.

Produces the template structure that CSV cannot express: row 1 is exactly
two merged cells — "FCU SCHEDULE" spanning A1:F1 and the mirage mark
spanning G1:N1 (no column lines in between) — followed by the four
label/value detail rows (values merged B:F and H:N), a styled column-header
row, and the data.

Every data value is written as the exact extracted string (zero rounding),
same guarantee as the CSV path.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .synthesizer import PROJECT_FIELDS

NAVY = "141B4D"
LOGO_INK = "1F3B57"
GRID = "9A9A9A"

_NUM_COLS = 14
_COL_WIDTHS = [30, 12, 12, 12, 11, 14, 14, 15, 9, 7, 10, 8, 12, 16]

_thin = Side(style="thin", color=GRID)
_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
_left = Alignment(horizontal="left", vertical="center")


def write_fcu_xlsx(
    details: dict[str, str],
    column_header: list[str],
    data_rows: list[list[str]],
    target: str | Path,
) -> Path:
    target = Path(target)
    wb = Workbook()
    ws = wb.active
    ws.title = "FCU SCHEDULE"

    # ---- rows 1-5: bordered header block ---------------------------------
    for row in range(1, 6):
        for col in range(1, _NUM_COLS + 1):
            ws.cell(row=row, column=col).border = _border

    ws.merge_cells("A1:F1")
    title = ws["A1"]
    title.value = "FCU SCHEDULE"
    title.font = Font(bold=True, size=16)
    title.alignment = _center

    ws.merge_cells("G1:N1")
    logo = ws["G1"]
    logo.value = "mirage"
    logo.font = Font(name="Georgia", bold=True, italic=True, size=22, color=LOGO_INK)
    logo.alignment = _center
    ws.row_dimensions[1].height = 40

    label_font = Font(bold=True, size=10)
    for row, ((l_key, l_label), (r_key, r_label)) in enumerate(
        zip(PROJECT_FIELDS[:4], PROJECT_FIELDS[4:]), start=2
    ):
        left_label = ws.cell(row=row, column=1, value=l_label)
        left_label.font = label_font
        left_label.alignment = _left
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        left_value = ws.cell(row=row, column=2, value=details[l_key].strip())
        left_value.alignment = _left

        right_label = ws.cell(row=row, column=7, value=r_label)
        right_label.font = label_font
        right_label.alignment = _left
        ws.merge_cells(start_row=row, start_column=8, end_row=row, end_column=_NUM_COLS)
        right_value = ws.cell(row=row, column=8, value=details[r_key].strip())
        right_value.alignment = _left

    # ---- row 6: column headers -------------------------------------------
    header_fill = PatternFill("solid", fgColor=NAVY)
    for col, text in enumerate(column_header, start=1):
        cell = ws.cell(row=6, column=col, value=text)
        cell.fill = header_fill
        cell.font = Font(bold=True, size=9, color="FFFFFF")
        cell.alignment = _center
        cell.border = _border
    ws.row_dimensions[6].height = 32

    # ---- data ------------------------------------------------------------
    for r, row_values in enumerate(data_rows, start=7):
        for col, value in enumerate(row_values, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.border = _border
            cell.alignment = _left

    for col, width in enumerate(_COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A7"

    wb.save(target)
    return target

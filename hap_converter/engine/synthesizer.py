"""Row assembly + derived fields.

Row model: one unit header row (name, floor area, coil loads, coil DB/WB,
water flow, W/m², Total kW) followed by one row per space (name, floor area,
air flow). Manual columns (Qty, ESP, FCU Types, Remarks) are emitted blank.

Derived fields use Decimal on the exact extracted strings — extracted values
themselves are never touched:
- W/m²   = Total Coil Load ÷ Floor Area × 1000
- Total kW = Total Coil Load × Qty (Qty is manual/blank at export, so the
  configured qty_default of "1" is used; the engineer edits Qty afterwards)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .config import Config
from .models import Unit

_NUM_COLS = 14


def _to_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _w_per_m2(unit: Unit, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals)
    result = (_to_decimal(unit.total_coil) / _to_decimal(unit.floor_area) * 1000).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    return format(result, "f")


def _total_kw(unit: Unit, qty_default: str) -> str:
    return format(_to_decimal(unit.total_coil) * _to_decimal(qty_default), "f")


# Mandatory project details entered in the UI before download (FR: FCU
# schedule header block). Keys are stable identifiers; labels are printed.
PROJECT_FIELDS = [
    ("project", "Project:"),
    ("project_no", "Project No:"),
    ("stage", "Stage:"),
    ("discipline", "Discipline:"),
    ("author", "Author:"),
    ("checked", "Checked:"),
    ("revision", "Revision:"),
    ("date", "Date:"),
]

# The company logo is a 10th mandatory input, supplied as an image file.
# It is embedded in the merged G1:N1 cell of the XLSX; CSV cannot hold an
# image, so the CSV header falls back to the image's file name.
LOGO_KEY = "logo_path"
LOGO_SUFFIXES = (".png", ".jpg", ".jpeg")


def build_project_header(details: dict[str, str], num_cols: int = _NUM_COLS) -> list[list[str]]:
    """The 5 rows above the column header in the downloaded CSV.

    Layout follows the FCU schedule template: a left zone A-F and a right
    zone G-N. Row 1: A = "FCU SCHEDULE" title, G = "mirage" (logo
    placeholder — CSV cannot embed images or merge cells; the true merged
    look needs XLSX output). Rows 2-5: A=label, B=value (Project /
    Project No / Stage / Discipline); G=label, H=value (Author / Checked /
    Revision / Date).
    """
    missing = [key for key, _ in PROJECT_FIELDS if not details.get(key, "").strip()]
    if missing:
        raise ValueError(f"Missing mandatory project details: {', '.join(missing)}")

    rows = []
    title = [""] * num_cols
    title[0] = "FCU SCHEDULE"
    # CSV cannot embed images: name the supplied logo file instead
    title[6] = Path(details.get(LOGO_KEY, "")).stem
    rows.append(title)

    left = PROJECT_FIELDS[:4]
    right = PROJECT_FIELDS[4:]
    for (l_key, l_label), (r_key, r_label) in zip(left, right):
        row = [""] * num_cols
        row[0] = l_label
        row[1] = details[l_key].strip()
        row[6] = r_label
        row[7] = details[r_key].strip()
        rows.append(row)
    return rows


def build_rows(units: list[Unit], config: Config) -> list[list[str]]:
    rows: list[list[str]] = [list(config.csv_columns)]
    for unit in units:
        unit_row = [""] * _NUM_COLS
        unit_row[0] = unit.name
        unit_row[1] = unit.floor_area
        unit_row[2] = unit.total_coil
        unit_row[3] = unit.sens_coil
        # col 4 (Air Flow) stays blank on the unit header row
        unit_row[5] = unit.coil_entering
        unit_row[6] = unit.coil_leaving
        unit_row[7] = unit.water_flow
        unit_row[8] = _w_per_m2(unit, config.w_per_m2_decimals)
        # col 9 (Qty) is manual/blank
        unit_row[10] = _total_kw(unit, config.qty_default)
        rows.append(unit_row)

        for space in unit.spaces:
            space_row = [""] * _NUM_COLS
            space_row[0] = space.name
            space_row[1] = space.floor_area
            space_row[4] = space.air_flow
            rows.append(space_row)
    return rows

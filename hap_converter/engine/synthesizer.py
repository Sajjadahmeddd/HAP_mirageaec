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

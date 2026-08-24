"""Orchestration: read the HAPExt schedule, size one subspace end to end.

Public surface:

    load_spaces(path, config)                  -> list[Space]
    size_space(space, sizing_input, config)    -> SizingResult

`size_space` never raises for a selection that cannot be made — an air flow
outside the catalogue's band, a noise limit no row can meet, a missing input
all come back as `SizingResult(ok=False, message=...)` so the UI has one code
path, exactly as `pipeline.convert` does in module 1.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import calc, lookup
from .config import Config
from .lookup import NoSelection
from .models import Space, SizingInput, SizingResult

# The HAPExt writer puts the column header on row 6 of the workbook and the
# data from row 7; a raw staged CSV has it on line 1. Both are found by
# looking for the name column rather than by assuming a position.
_MAX_HEADER_SCAN = 40


class SourceError(Exception):
    """The chosen file is not a schedule this app can size."""


def _read_grid(path: str | Path) -> list[list[str]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            with open(path, encoding="utf-8-sig", newline="") as handle:
                return [list(row) for row in csv.reader(handle)]
        except OSError as exc:
            raise SourceError(f"Could not read {path.name}: {exc}") from exc
    if suffix == ".xlsx":
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except Exception as exc:
            raise SourceError(f"Could not open {path.name} as an Excel workbook: {exc}") from exc
        sheet = workbook.active
        grid = [
            ["" if cell is None else str(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        workbook.close()
        return grid
    raise SourceError(f"{path.name}: expected the HAPExt .xlsx or .csv schedule.")


def _find_header(grid: list[list[str]], name_label: str) -> int:
    wanted = name_label.strip().casefold()
    for index, row in enumerate(grid[:_MAX_HEADER_SCAN]):
        for cell in row:
            if str(cell).strip().casefold() == wanted:
                return index
    raise SourceError(
        f"No column header row found — expected a column called {name_label!r}. "
        "Upload the schedule HAPExt generated."
    )


def load_spaces(path: str | Path, config: Config) -> list[Space]:
    """Read the HAPExt schedule into Space rows (unit headers included)."""
    columns = config.input_columns
    grid = _read_grid(path)
    if not grid:
        raise SourceError(f"{Path(path).name} is empty.")

    header_index = _find_header(grid, columns.get("name", "Zone Name / Space Name"))
    header = [str(cell).strip().casefold() for cell in grid[header_index]]

    def column_of(key: str) -> int:
        label = columns.get(key, "").strip().casefold()
        try:
            return header.index(label)
        except ValueError:
            raise SourceError(
                f"The schedule has no {columns.get(key, key)!r} column."
            ) from None

    indexes = {key: column_of(key) for key in ("name", "floor_area", "total_coil", "sens_coil", "air_flow")}

    def value(row: list[str], key: str) -> str:
        index = indexes[key]
        return str(row[index]).strip() if index < len(row) else ""

    spaces: list[Space] = []
    for offset, row in enumerate(grid[header_index + 1 :], start=header_index + 2):
        if not any(str(cell).strip() for cell in row):
            continue
        space = Space(
            name=value(row, "name"),
            floor_area=value(row, "floor_area"),
            total_coil=value(row, "total_coil"),
            sens_coil=value(row, "sens_coil"),
            air_flow=value(row, "air_flow"),
            is_unit=bool(value(row, "total_coil")),
            row=offset,
        )
        if space.name:
            spaces.append(space)

    if not spaces:
        raise SourceError(f"{Path(path).name} has no schedule rows below its column header.")
    return spaces


def sizable(space: Space) -> bool:
    """Subspace rows carry the air flow; unit header rows are not sized."""
    return not space.is_unit and bool(space.air_flow.strip())


def _failure(group: str, message: str) -> SizingResult:
    return SizingResult(ok=False, group=group, message=message)


def size_space(space: Space, sizing_input: SizingInput, config: Config) -> SizingResult:
    """Size one subspace against its diffuser catalogue."""
    try:
        spec = config.diffuser(sizing_input.diffuser)
    except Exception as exc:
        return _failure("", str(exc))
    catalog = config.catalog(spec.key)
    params = config.parameters

    missing = [
        config.input_spec(key, spec).label
        for key in spec.inputs
        if not sizing_input.get(key)
    ]
    if missing:
        return _failure(catalog.group, "Fill in: " + ", ".join(missing) + ".")

    try:
        flow = calc.to_decimal(space.air_flow)
    except (InvalidOperation, ValueError):
        return _failure(
            catalog.group, f"Air flow {space.air_flow!r} is not a number in the schedule."
        )
    if flow <= 0:
        return _failure(catalog.group, "This subspace has no air flow to distribute.")

    try:
        reading = lookup.read(config, catalog, sizing_input.values, flow)
    except NoSelection as exc:
        return _failure(catalog.group, str(exc))

    if catalog.group == "A":
        return _finish_group_a(catalog, config, sizing_input, reading, flow)
    return _finish_group_b(catalog, config, sizing_input, reading, flow)


def _finish_group_a(catalog, config, sizing_input, reading, flow) -> SizingResult:
    params = config.parameters
    lsm = reading.lsm or Decimal(0)

    # FlowBar: parallel slots share the airflow, so N slots carry N x the
    # table's per-metre rate (parameters.flow_bar_slots_multiply_lsm).
    if catalog.lsm_multiplier_input and params.flow_bar_slots_multiply_lsm:
        multiplier = sizing_input.get(catalog.lsm_multiplier_input)
        if multiplier:
            lsm = lsm * Decimal(multiplier)

    if lsm <= 0:
        return _failure(catalog.group, "The catalogue read a zero L/s/m for these inputs.")

    length = calc.air_outlet_length(flow, lsm)
    throw, nc = calc.apply_length_correction(catalog, length, reading.throw, reading.nc, params)
    throw_value = calc.pick_throw(throw, params)

    return SizingResult(
        ok=True,
        group="A",
        interpolated=reading.interpolated,
        table=reading.table_title,
        lsm=calc.fmt(lsm, params.places("lsm")),
        length_m=calc.fmt(length, params.places("length_m")),
        pieces=calc.piece_count(length, catalog.one_piece_length_m),
        throw=calc.fmt(throw_value, params.places("throw_m")),
        throw_range=calc.throw_range(throw, params.places("throw_m")),
        nc=calc.fmt_nc(nc),
        pt=calc.fmt(reading.pt, 1),
    )


def _finish_group_b(catalog, config, sizing_input, reading, flow) -> SizingResult:
    params = config.parameters
    outlets = int(Decimal(sizing_input.get(catalog.outlets_input or "") or "1"))
    throw_value = calc.pick_throw(reading.throw, params)

    return SizingResult(
        ok=True,
        group="B",
        interpolated=reading.interpolated,
        table=reading.table_title,
        size=reading.size,
        alt_sizes=list(reading.alt_sizes),
        outlets=outlets,
        velocity=calc.fmt(reading.velocity, params.places("velocity")),
        throw=calc.fmt(throw_value, params.places("throw_m")),
        throw_range=calc.throw_range(reading.throw, params.places("throw_m")),
        nc=calc.fmt_nc(reading.nc),
        pt=calc.fmt(reading.pt, 1),
    )

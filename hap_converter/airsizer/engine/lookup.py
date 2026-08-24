"""Catalogue lookup: resolve table -> row/column -> cell, with banding and
linear interpolation.

One function per output group, both reading the same `Catalog` objects:

- `read_group_a` — linear diffusers. The Noise Criteria the engineer chose is
  a ceiling on the L/s/m column: the reading is the largest L/s/m whose NC
  stays within the limit. When the limit falls between two published columns
  the reading is interpolated linearly between them and flagged.
- `read_group_b` — area diffusers. The air flow per outlet is looked up in
  each list-size column (interpolating between the bracketing flows) and the
  smallest size whose velocity and NC both stay within the limits wins.

Tables are banded: a row or column publishes cells over part of the range
only. Anything outside raises `NoSelection` — the engine never extrapolates
past the printed data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from . import calc
from .config import Catalog, CellA, CellB, ColumnB, Config, Parameters, RowA, Table
from .models import NoiseCriteria


class NoSelection(Exception):
    """No catalogue cell satisfies the inputs. A normal outcome, not a bug."""


@dataclass
class Reading:
    """One resolved catalogue read, before any derived maths."""

    interpolated: bool = False
    table_title: str = ""
    lsm: Decimal | None = None
    size: str = ""
    alt_sizes: tuple[str, ...] = ()
    velocity: Decimal | None = None
    pt: Decimal | None = None
    throw: tuple[Decimal, ...] = field(default_factory=tuple)
    nc: NoiseCriteria | None = None
    ak: Decimal | None = None


def nc_value(nc: NoiseCriteria, params: Parameters) -> Decimal:
    """The comparable number behind a cell printed as "20" or "<20"."""
    if nc.below and params.nc_less_than_policy != "as_value":
        raise NoSelection(
            f"Unsupported nc_less_than_policy {params.nc_less_than_policy!r}"
        )
    return nc.value


def _lerp(low: Decimal, high: Decimal, fraction: Decimal) -> Decimal:
    return low + (high - low) * fraction


def _lerp_throw(
    low: tuple[Decimal, ...], high: tuple[Decimal, ...], fraction: Decimal
) -> tuple[Decimal, ...]:
    if len(low) != len(high):
        raise NoSelection("Catalogue rows mix 2-value and 3-value throws")
    return tuple(_lerp(a, b, fraction) for a, b in zip(low, high))


def _lerp_nc(low: NoiseCriteria, high: NoiseCriteria, fraction: Decimal) -> NoiseCriteria:
    return NoiseCriteria(
        value=_lerp(low.value, high.value, fraction),
        below=low.below and high.below,
    )


def select_table(catalog: Catalog, values: dict[str, str]) -> Table:
    """First table whose `match` is satisfied by the chosen inputs."""
    for table in catalog.tables:
        if all(values.get(key, "").strip() == want for key, want in table.match.items()):
            return table
    wanted = ", ".join(
        f"{key}={values.get(key, '') or '-'}"
        for key in (catalog.table_inputs or ("deflection",))
    )
    raise NoSelection(
        f"The {catalog.title} catalogue has no selection table for {wanted}."
    )


# ------------------------------------------------------------------- group A
def _find_row(table: Table, key: str, catalog: Catalog) -> RowA:
    for row in table.rows:
        if row.key == key:
            return row
    available = ", ".join(r.key for r in table.rows)
    raise NoSelection(
        f"{catalog.title}: no row for {catalog.row_input} = {key or '-'} "
        f"(the table publishes {available})."
    )


def read_group_a(catalog: Catalog, values: dict[str, str], params: Parameters) -> Reading:
    """Largest L/s/m whose noise criteria stays within the chosen NC limit."""
    table = select_table(catalog, values)
    if not catalog.row_input:
        raise NoSelection(f"{catalog.title}: catalog has no row_input")
    row = _find_row(table, values.get(catalog.row_input, "").strip(), catalog)

    limit_text = values.get("nc", "").strip()
    if not limit_text:
        raise NoSelection("Noise Criteria is required.")
    limit = Decimal(limit_text)

    flows = row.flows
    ncs = [nc_value(row.cells[f].nc, params) for f in flows]

    if limit < ncs[0]:
        raise NoSelection(
            f"NC {limit_text} is below the quietest published selection for this row "
            f"(NC {ncs[0]} at {flows[0]} L/s/m). Raise the noise criteria or pick a "
            "wider outlet."
        )

    index = max(i for i, value in enumerate(ncs) if value <= limit)
    cell: CellA = row.cells[flows[index]]

    if index == len(flows) - 1 or ncs[index] == limit:
        return Reading(
            interpolated=False,
            table_title=table.title,
            lsm=flows[index],
            pt=cell.pt,
            throw=cell.throw,
            nc=cell.nc,
            ak=row.ak,
        )

    upper: CellA = row.cells[flows[index + 1]]
    span = ncs[index + 1] - ncs[index]
    fraction = (limit - ncs[index]) / span if span else Decimal(0)
    return Reading(
        interpolated=True,
        table_title=table.title,
        lsm=_lerp(flows[index], flows[index + 1], fraction),
        pt=_lerp(cell.pt, upper.pt, fraction),
        throw=_lerp_throw(cell.throw, upper.throw, fraction),
        nc=_lerp_nc(cell.nc, upper.nc, fraction),
        ak=row.ak,
    )


def nc_value_of(row: RowA, flow: Decimal, params: Parameters) -> Decimal:
    return nc_value(row.cells[flow].nc, params)


# ------------------------------------------------------------------- group B
def _cell_at_flow(column: ColumnB, flow: Decimal) -> tuple[CellB, bool] | None:
    """The column's cell at `flow`, interpolated inside the published band.

    Returns None when the flow falls outside this column's band — that column
    simply does not serve this air flow.
    """
    flows = column.flows
    if flow < flows[0] or flow > flows[-1]:
        return None
    if flow in column.cells:
        return column.cells[flow], False

    higher = next(i for i, value in enumerate(flows) if value > flow)
    low_key, high_key = flows[higher - 1], flows[higher]
    low, high = column.cells[low_key], column.cells[high_key]
    fraction = (flow - low_key) / (high_key - low_key)
    return (
        CellB(
            velocity=_lerp(low.velocity, high.velocity, fraction),
            throw=_lerp_throw(low.throw, high.throw, fraction),
            nc=_lerp_nc(low.nc, high.nc, fraction),
            pt=_lerp(low.pt, high.pt, fraction) if low.pt is not None and high.pt is not None else None,
        ),
        True,
    )


def read_group_b(
    catalog: Catalog, values: dict[str, str], flow_per_outlet: Decimal, params: Parameters
) -> Reading:
    """Smallest list size whose velocity and NC both stay within the limits."""
    table = select_table(catalog, values)

    velocity_text = values.get("velocity", "").strip()
    nc_text = values.get("nc", "").strip()
    if not velocity_text or not nc_text:
        raise NoSelection("Neck/Face Velocity and Noise Criteria are both required.")
    velocity_limit = Decimal(velocity_text)
    nc_limit = Decimal(nc_text)

    in_band = False
    for column in table.columns:            # ascending area
        found = _cell_at_flow(column, flow_per_outlet)
        if found is None:
            continue
        in_band = True
        cell, interpolated = found
        if cell.velocity <= velocity_limit and nc_value(cell.nc, params) <= nc_limit:
            return Reading(
                interpolated=interpolated,
                table_title=table.title,
                size=column.size,
                alt_sizes=column.sizes[1:],
                velocity=cell.velocity,
                pt=cell.pt,
                throw=cell.throw,
                nc=cell.nc,
            )

    if not in_band:
        low = min(c.flows[0] for c in table.columns)
        high = max(c.flows[-1] for c in table.columns)
        raise NoSelection(
            f"{calc.fmt(flow_per_outlet, 1)} L/s per outlet is outside the published "
            f"range ({calc.fmt(low, 0)}-{calc.fmt(high, 0)} L/s). Change the number of air outlets."
        )
    raise NoSelection(
        f"No list size serves {calc.fmt(flow_per_outlet, 1)} L/s within "
        f"{velocity_text} m/s and NC {nc_text}. Raise a limit or add outlets."
    )


def read(config: Config, catalog: Catalog, values: dict[str, str], flow: Decimal) -> Reading:
    """Group-agnostic entry point used by the pipeline."""
    if catalog.group == "A":
        return read_group_a(catalog, values, config.parameters)
    outlets_text = values.get(catalog.outlets_input or "", "").strip() or "1"
    try:
        outlets = int(Decimal(outlets_text))
    except Exception:
        raise NoSelection(f"Number of Air Outlet must be a whole number, got {outlets_text!r}") from None
    if outlets < 1:
        raise NoSelection("Number of Air Outlet must be at least 1.")
    return read_group_b(catalog, values, flow / outlets, config.parameters)

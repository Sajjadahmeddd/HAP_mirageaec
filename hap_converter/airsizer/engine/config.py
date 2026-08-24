"""Load and validate config/input_matrix.json + config/catalogs/*.json.

One generic engine, five catalog configs. A diffuser type is a small entry in
the input matrix (which inputs it takes, which catalog it reads, which output
group it produces); the catalog file holds the transcribed tables. Adding a
sixth diffuser means adding two JSON entries — no code change.

Two catalog shapes, matching the two output groups:

- group A (linear: slot, bar, flow bar) — `tables[].rows[]`, one row per
  No. of Slots / nominal width, cells keyed by L/s/m:
  `[Pt (Pa), "min-mid-max throw", "NC"]`. Output: L/s/m + throw.
- group B (area: square, grille) — `tables[].columns[]`, one column per list
  size, cells keyed by air flow (L/s):
  `[velocity (m/s), "min-max throw", "NC"]` (+ Pt for square).
  Output: the size in mm x mm.

Cells are banded: a row/column only publishes cells over part of the table's
range. Everything outside is "no valid selection", never an extrapolation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import NoiseCriteria


class ConfigError(Exception):
    pass


_SIZE_RE = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


def _dec(value: Any, where: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ConfigError(f"{where}: {value!r} is not a number") from exc


def _nc(text: Any, where: str) -> NoiseCriteria:
    raw = str(text).strip()
    below = raw.startswith("<")
    return NoiseCriteria(value=_dec(raw.lstrip("<").strip(), where), below=below)


def _throw(text: Any, where: str) -> tuple[Decimal, ...]:
    """Parse "3.6-5.4-7.8" (three terminal velocities) or "1.55-2.2" (two)."""
    parts = [p for p in str(text).replace(" ", "").split("-") if p]
    if len(parts) not in (2, 3):
        raise ConfigError(f"{where}: throw {text!r} must have 2 or 3 values")
    return tuple(_dec(p, where) for p in parts)


# --------------------------------------------------------------- catalog cells
@dataclass(frozen=True)
class CellA:
    pt: Decimal
    throw: tuple[Decimal, ...]
    nc: NoiseCriteria


@dataclass(frozen=True)
class CellB:
    velocity: Decimal
    throw: tuple[Decimal, ...]
    nc: NoiseCriteria
    pt: Decimal | None = None


@dataclass(frozen=True)
class RowA:
    key: str
    ak: Decimal | None
    model: str
    cells: dict[Decimal, CellA]      # keyed by L/s/m

    @property
    def flows(self) -> list[Decimal]:
        return sorted(self.cells)


@dataclass(frozen=True)
class ColumnB:
    sizes: tuple[str, ...]
    area_mm2: int
    cells: dict[Decimal, CellB]      # keyed by air flow (L/s)

    @property
    def size(self) -> str:
        return self.sizes[0]

    @property
    def flows(self) -> list[Decimal]:
        return sorted(self.cells)


@dataclass(frozen=True)
class Table:
    match: dict[str, str]
    title: str
    rows: tuple[RowA, ...] = ()
    columns: tuple[ColumnB, ...] = ()


@dataclass(frozen=True)
class LengthBand:
    max_length_m: Decimal
    throw_factor: Decimal
    nc_add: Decimal


@dataclass(frozen=True)
class Catalog:
    key: str
    group: str
    title: str
    source: str
    notes: tuple[str, ...]
    tables: tuple[Table, ...]
    row_input: str | None = None
    outlets_input: str | None = None
    table_inputs: tuple[str, ...] = ()
    lsm_multiplier_input: str | None = None
    reference_length_m: Decimal = Decimal(1)
    one_piece_length_m: Decimal = Decimal(1)
    length_bands: tuple[LengthBand, ...] = ()

    def row(self, key: str) -> RowA | None:
        for table in self.tables:
            for row in table.rows:
                if row.key == key:
                    return row
        return None


# ---------------------------------------------------------------- input matrix
@dataclass(frozen=True)
class InputSpec:
    key: str
    label: str
    unit: str
    options: tuple[str, ...]
    kind: str = "choice"             # "choice" (dropdown) | "count" (integer)

    def title(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label


@dataclass(frozen=True)
class DiffuserSpec:
    key: str
    label: str
    group: str
    catalog_file: str
    diagram: str
    inputs: tuple[str, ...]
    options: dict[str, tuple[str, ...]]

    def takes(self, input_key: str) -> bool:
        return input_key in self.inputs


@dataclass(frozen=True)
class ResultColumn:
    key: str
    label: str
    default: bool
    locked: bool = False


@dataclass(frozen=True)
class Parameters:
    """The rules the brief left open (section 8), as data rather than code."""

    nc_rule: str
    nc_less_than_policy: str
    throw_output: str
    apply_length_correction: bool
    length_correction_basis: str
    flow_bar_slots_multiply_lsm: bool
    decimals: dict[str, int]

    def places(self, key: str, fallback: int = 2) -> int:
        return int(self.decimals.get(key, fallback))


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    input_columns: dict[str, str]
    inputs: dict[str, InputSpec]
    diffusers: dict[str, DiffuserSpec]
    catalogs: dict[str, Catalog]
    parameters: Parameters
    result_columns: tuple[ResultColumn, ...]
    diagram_dir: Path

    def diffuser(self, key: str) -> DiffuserSpec:
        try:
            return self.diffusers[key]
        except KeyError:
            raise ConfigError(f"Unknown diffuser type: {key!r}") from None

    def catalog(self, key: str) -> Catalog:
        try:
            return self.catalogs[key]
        except KeyError:
            raise ConfigError(f"No catalog loaded for {key!r}") from None

    def input_spec(self, key: str, diffuser: DiffuserSpec | None = None) -> InputSpec:
        """The input, with any per-diffuser option override applied."""
        spec = self.inputs[key]
        if diffuser and key in diffuser.options:
            return InputSpec(spec.key, spec.label, spec.unit, diffuser.options[key], spec.kind)
        return spec

    def diagram_path(self, diffuser_key: str) -> Path:
        return self.diagram_dir / self.diffuser(diffuser_key).diagram


# ------------------------------------------------------------------ catalog IO
def _load_group_a(data: dict, key: str) -> tuple[Table, ...]:
    tables = []
    for t_index, table in enumerate(data.get("tables", [])):
        rows = []
        for row in table.get("rows", []):
            where = f"{key} table {t_index} row {row.get('key')!r}"
            cells = {}
            for flow, cell in row.get("cells", {}).items():
                if len(cell) < 3:
                    raise ConfigError(f"{where}: cell {flow!r} needs [Pt, throw, NC]")
                cells[_dec(flow, where)] = CellA(
                    pt=_dec(cell[0], where),
                    throw=_throw(cell[1], where),
                    nc=_nc(cell[2], where),
                )
            if not cells:
                raise ConfigError(f"{where}: has no cells")
            rows.append(
                RowA(
                    key=str(row["key"]),
                    ak=_dec(row["ak"], where) if row.get("ak") is not None else None,
                    model=str(row.get("model", "")),
                    cells=cells,
                )
            )
        tables.append(
            Table(match=dict(table.get("match", {})), title=str(table.get("title", "")), rows=tuple(rows))
        )
    return tuple(tables)


def _area_of(size: str, where: str) -> int:
    match = _SIZE_RE.match(size)
    if not match:
        raise ConfigError(f"{where}: size {size!r} must read like '600 x 600'")
    return int(match.group(1)) * int(match.group(2))


def _load_group_b(data: dict, key: str) -> tuple[Table, ...]:
    tables = []
    for t_index, table in enumerate(data.get("tables", [])):
        columns = []
        for column in table.get("columns", []):
            sizes = tuple(str(s) for s in column.get("sizes", []))
            if not sizes:
                raise ConfigError(f"{key} table {t_index}: a column has no sizes")
            where = f"{key} table {t_index} column {sizes[0]!r}"
            cells = {}
            for flow, cell in column.get("cells", {}).items():
                if len(cell) < 3:
                    raise ConfigError(f"{where}: cell {flow!r} needs [velocity, throw, NC]")
                cells[_dec(flow, where)] = CellB(
                    velocity=_dec(cell[0], where),
                    throw=_throw(cell[1], where),
                    nc=_nc(cell[2], where),
                    pt=_dec(cell[3], where) if len(cell) > 3 else None,
                )
            if not cells:
                raise ConfigError(f"{where}: has no cells")
            columns.append(
                ColumnB(sizes=sizes, area_mm2=_area_of(sizes[0], where), cells=cells)
            )
        # ascending area: the engine picks the smallest size that satisfies
        columns.sort(key=lambda c: c.area_mm2)
        tables.append(
            Table(
                match=dict(table.get("match", {})),
                title=str(table.get("title", "")),
                columns=tuple(columns),
            )
        )
    return tuple(tables)


def load_catalog(path: str | Path) -> Catalog:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Catalog file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read catalog {path.name}: {exc}") from exc

    key = str(data.get("key") or path.stem)
    group = str(data.get("group", "")).upper()
    if group not in ("A", "B"):
        raise ConfigError(f"{path.name}: 'group' must be 'A' or 'B', got {group!r}")

    tables = _load_group_a(data, key) if group == "A" else _load_group_b(data, key)
    if not tables:
        raise ConfigError(f"{path.name}: has no tables")

    correction = data.get("length_correction", {})
    bands = tuple(
        LengthBand(
            max_length_m=_dec(band["max_length_m"], f"{key} length_correction"),
            throw_factor=_dec(band.get("throw_factor", 1), f"{key} length_correction"),
            nc_add=_dec(band.get("nc_add", 0), f"{key} length_correction"),
        )
        for band in correction.get("bands", [])
    )

    return Catalog(
        key=key,
        group=group,
        title=str(data.get("title", key)),
        source=str(data.get("source", "")),
        notes=tuple(str(n) for n in data.get("notes", [])),
        tables=tables,
        row_input=data.get("row_input"),
        outlets_input=data.get("outlets_input"),
        table_inputs=tuple(data.get("table_inputs", [])),
        lsm_multiplier_input=data.get("lsm_multiplier_input"),
        reference_length_m=_dec(data.get("reference_length_m", 1), f"{key} reference_length_m"),
        one_piece_length_m=_dec(data.get("one_piece_length_m", 1), f"{key} one_piece_length_m"),
        length_bands=tuple(sorted(bands, key=lambda b: b.max_length_m)),
    )


def load(path: str | Path) -> Config:
    """Load input_matrix.json and every catalog it references."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Input matrix not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read {path.name}: {exc}") from exc

    for required in ("inputs", "diffuser_types", "parameters", "result_columns"):
        if required not in raw:
            raise ConfigError(f"{path.name} is missing required key: {required!r}")

    inputs = {
        str(entry["key"]): InputSpec(
            key=str(entry["key"]),
            label=str(entry.get("label", entry["key"])),
            unit=str(entry.get("unit", "")),
            options=tuple(str(o) for o in entry.get("options", [])),
            kind=str(entry.get("kind", "choice")),
        )
        for entry in raw["inputs"]
    }

    catalog_dir = path.parent / "catalogs"
    diffusers: dict[str, DiffuserSpec] = {}
    catalogs: dict[str, Catalog] = {}
    for entry in raw["diffuser_types"]:
        key = str(entry["key"])
        unknown = [i for i in entry.get("inputs", []) if i not in inputs]
        if unknown:
            raise ConfigError(f"diffuser {key!r} lists unknown inputs: {', '.join(unknown)}")
        diffusers[key] = DiffuserSpec(
            key=key,
            label=str(entry.get("label", key)),
            group=str(entry.get("group", "")).upper(),
            catalog_file=str(entry["catalog"]),
            diagram=str(entry.get("diagram", "")),
            inputs=tuple(str(i) for i in entry.get("inputs", [])),
            options={k: tuple(str(v) for v in vs) for k, vs in entry.get("options", {}).items()},
        )
        catalog = load_catalog(catalog_dir / entry["catalog"])
        if catalog.group != diffusers[key].group:
            raise ConfigError(
                f"diffuser {key!r} is group {diffusers[key].group} but its catalog is group {catalog.group}"
            )
        catalogs[key] = catalog

    params = raw["parameters"]
    parameters = Parameters(
        nc_rule=str(params.get("nc_rule", "cap_lsm_by_nc")),
        nc_less_than_policy=str(params.get("nc_less_than_policy", "as_value")),
        throw_output=str(params.get("throw_output", "mid")),
        apply_length_correction=bool(params.get("apply_length_correction", True)),
        length_correction_basis=str(params.get("length_correction_basis", "total")),
        flow_bar_slots_multiply_lsm=bool(params.get("flow_bar_slots_multiply_lsm", True)),
        decimals=dict(params.get("decimals", {})),
    )
    if parameters.throw_output not in ("min", "mid", "max"):
        raise ConfigError(
            f"parameters.throw_output must be min|mid|max, got {parameters.throw_output!r}"
        )
    if parameters.nc_rule != "cap_lsm_by_nc":
        raise ConfigError(
            f"parameters.nc_rule {parameters.nc_rule!r} is not implemented "
            "(only 'cap_lsm_by_nc'); see the TODO in input_matrix.json"
        )

    return Config(
        raw=raw,
        input_columns=dict(raw.get("input_columns", {})),
        inputs=inputs,
        diffusers=diffusers,
        catalogs=catalogs,
        parameters=parameters,
        result_columns=tuple(
            ResultColumn(
                key=str(c["key"]),
                label=str(c.get("label", c["key"])),
                default=bool(c.get("default", False)),
                locked=bool(c.get("locked", False)),
            )
            for c in raw["result_columns"]
        ),
        diagram_dir=path.parent / "diagrams",
    )

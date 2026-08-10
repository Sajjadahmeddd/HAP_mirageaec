"""Load and validate config/mapping.json (FR-09).

The mapping — anchors, section/row specs, offsets, mandatory-field list, CSV
columns — lives in an external JSON file so it can be tuned per HAP report
format without recompiling.

Two kinds of unit-field spec (validated against the real HAP v5.2
"Zone Sizing Summary" report):

- label-anchored: {"anchor": "Air System Name", "offset": 1}
  The value follows the label, either on the same line or `offset` lines
  below it.
- section-row: {"section": "Terminal Unit Sizing Data - Cooling",
                "row_regex": "^Zone \\d+$", "offset": 1}
  The value sits `offset` lines after the first row matching `row_regex`
  inside the named section (HAP emits the sizing table as one positional
  row per zone, with unusable fragmented header labels).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


_REQUIRED_KEYS = (
    "page_signature",
    "csv_columns",
    "unit_fields",
    "space_table",
    "mandatory",
)

_UNIT_FIELD_KEYS = (
    "name",
    "floor_area",
    "total_coil",
    "sens_coil",
    "coil_entering",
    "coil_leaving",
    "water_flow",
)


@dataclass(frozen=True)
class FieldSpec:
    offset: int = 1
    anchor: str | None = None          # label-anchored spec
    allow_same_line: bool = True
    section: str | None = None         # section-row spec
    row_regex: str | None = None


@dataclass(frozen=True)
class SpaceTableSpec:
    section_anchor: str
    zone_row_regex: str
    footer_anchor: str
    merge_time_of_peak: bool
    field_offsets: dict[str, int]


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    page_signature: str
    csv_columns: list[str]
    unit_fields: dict[str, FieldSpec]
    space_table: SpaceTableSpec
    mandatory_unit: list[str]
    mandatory_space: list[str]
    numeric_unit_fields: list[str]
    qty_default: str
    w_per_m2_decimals: int
    csv_encoding: str


def load(path: str | Path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Mapping file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read mapping file {path}: {exc}") from exc

    for key in _REQUIRED_KEYS:
        if key not in raw:
            raise ConfigError(f"mapping.json is missing required key: {key!r}")

    unit_fields: dict[str, FieldSpec] = {}
    for name in _UNIT_FIELD_KEYS:
        spec = raw["unit_fields"].get(name)
        if not spec:
            raise ConfigError(f"mapping.json unit_fields.{name} is missing")
        if "anchor" not in spec and not ("section" in spec and "row_regex" in spec):
            raise ConfigError(
                f"mapping.json unit_fields.{name} needs either 'anchor' "
                "or 'section' + 'row_regex'"
            )
        unit_fields[name] = FieldSpec(
            offset=int(spec.get("offset", 1)),
            anchor=spec.get("anchor"),
            allow_same_line=bool(spec.get("allow_same_line", True)),
            section=spec.get("section"),
            row_regex=spec.get("row_regex"),
        )

    table = raw["space_table"]
    for key in ("section_anchor", "zone_row_regex", "footer_anchor", "fields"):
        if key not in table:
            raise ConfigError(f"mapping.json space_table is missing key: {key!r}")
    for fname in ("floor_area", "air_flow"):
        if fname not in table["fields"]:
            raise ConfigError(f"mapping.json space_table.fields needs {fname!r}")
    space_table = SpaceTableSpec(
        section_anchor=table["section_anchor"],
        zone_row_regex=table["zone_row_regex"],
        footer_anchor=table["footer_anchor"],
        merge_time_of_peak=bool(table.get("merge_time_of_peak", True)),
        field_offsets={k: int(v["offset"]) for k, v in table["fields"].items()},
    )

    mandatory = raw["mandatory"]
    if "unit" not in mandatory or "space" not in mandatory:
        raise ConfigError("mapping.json 'mandatory' needs 'unit' and 'space' lists")

    if len(raw["csv_columns"]) != 14:
        raise ConfigError(
            f"mapping.json csv_columns must have 14 entries, got {len(raw['csv_columns'])}"
        )

    derived = raw.get("derived", {})
    return Config(
        raw=raw,
        page_signature=raw["page_signature"],
        csv_columns=list(raw["csv_columns"]),
        unit_fields=unit_fields,
        space_table=space_table,
        mandatory_unit=list(mandatory["unit"]),
        mandatory_space=list(mandatory["space"]),
        numeric_unit_fields=list(raw.get("numeric_unit_fields", [])),
        qty_default=str(derived.get("qty_default", "1")),
        w_per_m2_decimals=int(derived.get("w_per_m2_decimals", 2)),
        csv_encoding=raw.get("csv_encoding", "utf-8-sig"),
    )

"""All-or-nothing completeness gate.

If any mandatory PDF-sourced value is missing or unreadable for any unit or
space, the whole export is blocked; each problem is reported as an Issue
naming the page and field. Manual columns are never checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .config import Config
from .models import Unit

FIELD_LABELS = {
    "name": "Zone Name / Space Name",
    "floor_area": "Floor Area (m²)",
    "total_coil": "Total Coil Load (KW)",
    "sens_coil": "Sens Coil Load (KW)",
    "air_flow": "Air Flow (L/s)",
    "coil_entering": "Coil Entering DB / WB (°C)",
    "coil_leaving": "Coil Leaving DB / WB (°C)",
    "water_flow": "Water Flow @9.0 K (L/s)",
}


@dataclass
class Issue:
    page: int
    field: str
    description: str


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def _numeric(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def validate(units: list[Unit], config: Config) -> list[Issue]:
    issues: list[Issue] = []

    if not units:
        issues.append(
            Issue(
                page=0,
                field="document",
                description=(
                    "No air-system unit pages were found in this PDF "
                    f"(no page contains the anchor {config.page_signature!r})."
                ),
            )
        )
        return issues

    for unit in units:
        who = f"unit {unit.name!r}" if unit.name else "unnamed unit"

        for fname in config.mandatory_unit:
            if not getattr(unit, fname, "").strip():
                issues.append(
                    Issue(unit.page, _label(fname), f"Missing value for {who}.")
                )
        if not unit.name.strip():
            issues.append(Issue(unit.page, _label("name"), "Missing unit name."))

        # Fields consumed by derived-field math must parse as numbers.
        for fname in config.numeric_unit_fields:
            value = getattr(unit, fname, "").strip()
            if not value:
                continue  # already reported as missing above
            number = _numeric(value)
            if number is None:
                issues.append(
                    Issue(
                        unit.page,
                        _label(fname),
                        f"Unreadable value {value!r} for {who} (not a number).",
                    )
                )
            elif fname == "floor_area" and number == 0:
                issues.append(
                    Issue(
                        unit.page,
                        _label(fname),
                        f"Floor area is zero for {who}; W/m² cannot be computed.",
                    )
                )

        for space in unit.spaces:
            space_who = (
                f"space {space.name!r} in {who}" if space.name else f"unnamed space in {who}"
            )
            for fname in config.mandatory_space:
                if not getattr(space, fname, "").strip():
                    issues.append(
                        Issue(space.page, _label(fname), f"Missing value for {space_who}.")
                    )

    return issues

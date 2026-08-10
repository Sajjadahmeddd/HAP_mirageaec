"""Data model. Every extracted field is a str, carried verbatim from the PDF —
never converted to float — so the CSV reproduces the report with zero rounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Space:
    name: str = ""
    floor_area: str = ""
    air_flow: str = ""
    page: int = 0


@dataclass
class Unit:
    name: str = ""
    floor_area: str = ""
    total_coil: str = ""
    sens_coil: str = ""
    coil_entering: str = ""
    coil_leaving: str = ""
    water_flow: str = ""
    spaces: list[Space] = field(default_factory=list)
    page: int = 0

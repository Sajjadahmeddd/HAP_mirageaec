"""Data model for AirSizer Pro.

Values that come from the HAPExt schedule are carried as the exact strings
that schedule holds — the zero-rounding guarantee of module 1 survives into
module 2. Everything the engine computes uses `Decimal` (never float) and is
formatted once, at the edge, by `calc.fmt`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Space:
    """One row of the HAPExt schedule.

    Unit header rows (`is_unit`) carry the coil loads; the subspace rows under
    them carry the air flow that is actually sized. Both are kept so the
    review table can reproduce the schedule's shape.
    """

    name: str = ""
    floor_area: str = ""
    total_coil: str = ""
    sens_coil: str = ""
    air_flow: str = ""
    is_unit: bool = False
    row: int = 0


@dataclass(frozen=True)
class NoiseCriteria:
    """A catalogue NC cell. `below` records a value printed as "<20"."""

    value: Decimal
    below: bool = False

    def __str__(self) -> str:
        text = format(self.value.normalize(), "f")
        return f"<{text}" if self.below else text


@dataclass
class SizingInput:
    """What the engineer chose for one subspace."""

    diffuser: str = ""
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        return self.values.get(key, "").strip()


@dataclass
class SizingResult:
    """Outcome of sizing one subspace.

    `ok` false with a `message` is the "no valid selection in range" state —
    a normal outcome, not an error. `interpolated` marks a value read between
    two catalogue entries rather than straight off one.
    """

    ok: bool = False
    group: str = ""
    message: str = ""
    interpolated: bool = False

    # group A (linear): L/s/m + throw, and the length it implies
    lsm: str = ""
    length_m: str = ""
    pieces: int = 0

    # group B (area): the selected size, plus the equivalent sizes it stands for
    size: str = ""
    alt_sizes: list[str] = field(default_factory=list)
    outlets: int = 0

    # reported for both groups
    throw: str = ""
    throw_range: str = ""
    nc: str = ""
    velocity: str = ""
    pt: str = ""
    table: str = ""

    @property
    def status(self) -> str:
        if not self.ok:
            return "No valid selection"
        return "Interpolated" if self.interpolated else "Read"

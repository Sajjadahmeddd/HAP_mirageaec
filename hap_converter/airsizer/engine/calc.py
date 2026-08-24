"""Derived quantities and output formatting.

All arithmetic is `Decimal` on the exact catalogue and schedule values — no
float ever touches a number the engineer will read.

    Air Outlet Length (m) = Air Flow (L/s) / Air Flow (L/s/m)
    Number of pieces      = ceil(length / the catalogue's one-piece length)

Catalogue throw and NC are published for a reference length (1 m for the
linear slot and bar grille tables, 1200 mm for FlowBar). `apply_length_
correction` steps them to the length actually derived, using the correction
bands transcribed from each catalogue.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .config import Catalog, LengthBand, Parameters
from .models import NoiseCriteria


def to_decimal(value: str) -> Decimal:
    """Parse a schedule value (kept as a string all the way from the PDF)."""
    return Decimal(str(value).replace(",", "").strip())


def fmt(value: Decimal | None, places: int) -> str:
    """Round half-up to `places`, then drop trailing zeros (21.70 -> 21.7)."""
    if value is None:
        return ""
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def air_outlet_length(air_flow: Decimal, lsm: Decimal) -> Decimal:
    if lsm <= 0:
        raise ValueError("L/s/m must be positive to derive a length")
    return air_flow / lsm


def piece_count(length_m: Decimal, one_piece_m: Decimal) -> int:
    """How many standard pieces the derived length needs (always rounds up)."""
    if one_piece_m <= 0:
        return 1
    whole = int(length_m / one_piece_m)
    if Decimal(whole) * one_piece_m < length_m:
        whole += 1
    return max(1, whole)


def band_for(catalog: Catalog, length_m: Decimal) -> LengthBand | None:
    """The correction band covering `length_m`.

    Bands are ascending by their upper bound. A length past the last band
    keeps the last band's factors — the catalogues stop publishing beyond
    their longest section rather than saying the correction stops applying.
    """
    if not catalog.length_bands:
        return None
    for band in catalog.length_bands:
        if length_m <= band.max_length_m:
            return band
    return catalog.length_bands[-1]


def correction_length(catalog: Catalog, total_length_m: Decimal, params: Parameters) -> Decimal:
    if params.length_correction_basis == "piece":
        return catalog.one_piece_length_m
    return total_length_m


def apply_length_correction(
    catalog: Catalog,
    total_length_m: Decimal,
    throw: tuple[Decimal, ...],
    nc: NoiseCriteria | None,
    params: Parameters,
) -> tuple[tuple[Decimal, ...], NoiseCriteria | None]:
    """Step catalogue throw and NC from the reference length to the real one."""
    if not params.apply_length_correction:
        return throw, nc
    band = band_for(catalog, correction_length(catalog, total_length_m, params))
    if band is None:
        return throw, nc
    corrected = tuple(value * band.throw_factor for value in throw)
    if nc is None:
        return corrected, None
    return corrected, NoiseCriteria(value=nc.value + band.nc_add, below=nc.below)


def pick_throw(throw: tuple[Decimal, ...], params: Parameters) -> Decimal | None:
    """The single Flow Throw value to report, per `parameters.throw_output`.

    Linear tables publish three terminal velocities (0.75 / 0.50 / 0.25 m/s);
    the grille tables publish two. For a two-value cell "mid" is the mean of
    the pair, so the configured choice always yields a number.
    """
    if not throw:
        return None
    choice = params.throw_output
    if len(throw) >= 3:
        return {"min": throw[0], "mid": throw[1], "max": throw[-1]}[choice]
    if choice == "min":
        return throw[0]
    if choice == "max":
        return throw[-1]
    return (throw[0] + throw[-1]) / 2


def throw_range(throw: tuple[Decimal, ...], places: int) -> str:
    return " - ".join(fmt(value, places) for value in throw)


def fmt_nc(nc: NoiseCriteria | None, places: int = 0) -> str:
    """Noise criteria as printed: "24", or "<15" for a below-threshold cell."""
    if nc is None:
        return ""
    text = fmt(nc.value, places)
    return f"<{text}" if nc.below else text

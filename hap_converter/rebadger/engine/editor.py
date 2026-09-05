"""The three edits a rebadge makes, and the checks that they landed.

Removing text means *redaction* — the old string leaves the content stream.
Painting a white box over it would look identical on screen while the old
value stayed selectable, searchable and present in the file, which on a
revision-controlled drawing is worse than not editing it at all. Every
removal here is verified by re-extracting the region afterwards.

New text is Helvetica: Arial's metric twin, and the only honest choice since
the sheet's own fonts are embedded as subsets that cannot be extended with
glyphs they do not already carry. Size and weight are read from the value
being replaced, so a rebadged cell matches its neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from .locator import Cell, TitleBlock
from .models import HISTORY_COLUMNS, RebadgeInputs

# Helvetica's cap height as a fraction of point size — what "vertically
# centred" means for text that is all capitals, as these values are.
_CAP_HEIGHT = 0.717
# Breathing room inside a cell before text is considered to overflow.
_SIDE_PAD = 3.0
# How far a value may be shrunk to fit before we would rather warn than
# quietly print something noticeably smaller than the sheet's other values.
_MIN_SCALE = 0.6


class RedactionError(Exception):
    """Old text survived removal — the sheet must not be emitted."""


class CellOverflowError(Exception):
    """A value will not fit its cell even at the smallest size allowed.

    Drawing it anyway would run the text over the title block rules and into
    the neighbouring cells: a defect an engineer would be blamed for, and one
    the tool can see coming. Better to refuse the sheet and name the field.
    """


@dataclass
class TextStyle:
    size: float
    bold: bool = False

    @property
    def fontname(self) -> str:
        return "hebo" if self.bold else "helv"


@dataclass
class EditReport:
    warnings: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def _width(text: str, style: TextStyle, size: float) -> float:
    return pymupdf.get_text_length(text, fontname=style.fontname, fontsize=size)


def _fit(text: str, style: TextStyle, available: float) -> tuple[float, bool]:
    """The largest size at or below the measured one that fits the cell.

    Helvetica is wider than the Arial Narrow these sheets use for display
    values, so a long replacement can overflow a cell that held the original
    comfortably. Stepping down keeps it inside the rules; the caller warns so
    the engineer can see it happened rather than discovering it in print.
    """
    size = style.size
    floor = style.size * _MIN_SCALE
    while size > floor and _width(text, style, size) > available:
        size -= 0.25
    return size, size < style.size - 1e-6


def draw_centred(page: pymupdf.Page, block: TitleBlock, rect: pymupdf.Rect,
                 text: str, style: TextStyle, *, label: str) -> list[str]:
    """Write `text` centred in a displayed rect. Returns any warnings."""
    warnings: list[str] = []
    if not text:
        return warnings

    available = max(rect.width - 2 * _SIDE_PAD, 1.0)
    size, shrunk = _fit(text, style, available)
    width = _width(text, style, size)
    if width > available:
        raise CellOverflowError(
            f"{label}: {text!r} needs {width:.0f} pt but the cell allows "
            f"{available:.0f} pt, even reduced to {size:.1f} pt. Shorten the value."
        )
    if shrunk:
        warnings.append(
            f"{label}: text reduced from {style.size:.1f} to {size:.1f} pt to fit the cell"
        )
    baseline = pymupdf.Point(
        (rect.x0 + rect.x1) / 2 - width / 2,
        (rect.y0 + rect.y1) / 2 + (_CAP_HEIGHT * size) / 2,
    )
    page.insert_text(baseline * block.derotation, text,
                     fontname=style.fontname, fontsize=size,
                     rotate=block.rotation, color=(0, 0, 0))
    return warnings


def _redact(page: pymupdf.Page, block: TitleBlock, zone: pymupdf.Rect) -> str:
    """Remove every glyph inside a displayed rect. Returns what was removed.

    Images and line art are left alone, and the rect is the value zone rather
    than the whole cell, so the label above it and the rules around it come
    through untouched.
    """
    target = (zone * block.derotation).normalize()
    existing = page.get_text("text", clip=target).strip()
    page.add_redact_annot(target)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)

    remaining = page.get_text("text", clip=target).strip()
    if remaining:
        raise RedactionError(
            f"text survived removal at {tuple(round(v, 1) for v in zone)}: {remaining!r}"
        )
    return existing


def replace_cell(page: pymupdf.Page, block: TitleBlock, cell: Cell,
                 text: str, style: TextStyle | None = None) -> EditReport:
    """Remove a cell's current value and write a new one in its place."""
    report = EditReport()
    removed = _redact(page, block, cell.value_zone)
    if removed:
        report.removed.append(removed)

    if page.search_for(cell.label) == []:
        raise RedactionError(f"the {cell.label!r} label was removed along with its value")

    style = style or TextStyle(size=10.0, bold=True)
    report.warnings += draw_centred(page, block, cell.value_zone, text,
                                    style, label=cell.label.title())
    return report


def overwrite_revision_cell(page: pymupdf.Page, block: TitleBlock,
                            rev: str, style: TextStyle | None = None) -> EditReport:
    """The bottom-right grid cell always shows the current revision."""
    return replace_cell(page, block, block.revision, rev, style)


def append_history_row(page: pymupdf.Page, block: TitleBlock,
                       inputs: RebadgeInputs, row_index: int,
                       style: TextStyle) -> EditReport:
    """Write the four new values into one blank row of the revision table.

    Nothing already in the table is touched: this only ever writes into a row
    the reader found empty, which is what keeps the revision history a
    history. The row is chosen by the caller (`reader.target_row_index`).
    """
    report = EditReport()
    table = block.history
    row = table.rows[row_index]
    values = {
        "rev": inputs.rev,
        "description": inputs.description,
        "date": inputs.date,
        "approved_by": inputs.approved_by,
    }
    for key in HISTORY_COLUMNS:
        cell_rect = table.cell(row, key)
        report.warnings += draw_centred(page, block, cell_rect, values[key],
                                        style, label=f"Revision row / {key}")
    return report

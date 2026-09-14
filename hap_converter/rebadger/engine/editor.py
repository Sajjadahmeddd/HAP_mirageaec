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

from .locator import HISTORY_LABELS, Cell, TitleBlock, forget_spans, search
from .models import HISTORY_COLUMNS, RebadgeInputs

# Helvetica's cap height as a fraction of point size — what "vertically
# centred" means for text that is all capitals, as these values are.
_CAP_HEIGHT = 0.717
# Breathing room inside a cell before text is considered to overflow.
_SIDE_PAD = 3.0
# How far a value may be shrunk to fit before we would rather warn than
# quietly print something noticeably smaller than the sheet's other values.
_MIN_SCALE = 0.6
# How far inside a revision-table cell's rules the old value is cleared, as
# (from the column rules, from the row rules). Rows are 11 pt deep with their
# text set about 2.3 pt clear of the rule on each side, and the header labels
# start 1.5 pt below the bottom row — so this takes the whole value while
# staying off the rows above and below and off the headings.
_TABLE_INSET = (1.0, 0.8)


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
    forget_spans(page)                     # new glyphs on the page
    return warnings


def _redact_all(page: pymupdf.Page, block: TitleBlock,
                zones: list[pymupdf.Rect]) -> list[str]:
    """Remove every glyph inside each displayed rect, in one pass.

    Returns what was removed from each zone, in order. Images and line art
    are left alone, and each rect is a value zone rather than a whole cell, so
    labels and the rules around them come through untouched.

    One `apply_redactions` for all the zones, not one each: on these A1 sheets
    every call rewrites the page's whole content stream, about 23 ms apiece,
    so clearing the four revision-row cells separately cost ~70 ms a sheet
    more than clearing them together — for an identical result.
    """
    targets = [(zone * block.derotation).normalize() for zone in zones]
    existing = [page.get_text("text", clip=target).strip() for target in targets]
    for target in targets:
        page.add_redact_annot(target)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    forget_spans(page)                     # the text page just changed

    for zone, target in zip(zones, targets):
        remaining = page.get_text("text", clip=target).strip()
        if remaining:
            raise RedactionError(
                f"text survived removal at {tuple(round(v, 1) for v in zone)}: {remaining!r}"
            )
    return existing


def _redact(page: pymupdf.Page, block: TitleBlock, zone: pymupdf.Rect) -> str:
    """Remove every glyph inside one displayed rect. Returns what was removed."""
    return _redact_all(page, block, [zone])[0]


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


def _headings_outside(page: pymupdf.Page, row: pymupdf.Rect) -> dict[str, int]:
    """How often each table heading is printed anywhere but inside `row`.

    Counted outside the row because a search is a substring match: an old
    description reading "REVISED LAYOUT" contains REV, and removing it is the
    point, not a lost heading.
    """
    matrix = page.rotation_matrix
    return {name: sum(1 for hit in search(page, name) if not (hit * matrix).intersects(row))
            for name in HISTORY_LABELS}


def overwrite_history_row(page: pymupdf.Page, block: TitleBlock,
                          inputs: RebadgeInputs, row_index: int,
                          style: TextStyle) -> EditReport:
    """Replace the four values in one row of the revision table.

    The row is the sheet's latest entry, chosen by `reader.overwrite_row_index`.
    Each cell is redacted before anything is written, for the same reason the
    stage and status are: the old revision's text has to leave the file, not
    sit selectable underneath the new one. All four cells are cleared in one
    pass before any are written, so no redaction can reach a value just drawn
    beside it.

    Only this row changes. The clearing zone stays inside its rules, and the
    headings directly below the bottom row are counted before and after, so
    a clip that took one would fail the sheet rather than ship it.
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

    headings = _headings_outside(page, row)
    dx, dy = _TABLE_INSET
    zones = []
    for key in HISTORY_COLUMNS:
        cell_rect = table.cell(row, key)
        zones.append(pymupdf.Rect(cell_rect.x0 + dx, cell_rect.y0 + dy,
                                  cell_rect.x1 - dx, cell_rect.y1 - dy))
    report.removed += [text for text in _redact_all(page, block, zones) if text]
    for name, count in _headings_outside(page, row).items():
        if count < headings[name]:
            raise RedactionError(
                f"the {name!r} heading was removed along with the old revision row")

    for key in HISTORY_COLUMNS:
        cell_rect = table.cell(row, key)
        report.warnings += draw_centred(page, block, cell_rect, values[key],
                                        style, label=f"Revision row / {key}")
    return report

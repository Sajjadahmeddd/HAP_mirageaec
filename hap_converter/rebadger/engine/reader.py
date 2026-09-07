"""Read what a sheet currently says, before anything is changed.

Powers three things: validation before a batch runs, the preview the engineer
approves, and the no-op warning when the revision they typed is the one the
sheet already carries.
"""

from __future__ import annotations

import pymupdf

from .locator import Cell, TitleBlock, spans, words
from .models import HistoryRow


def _value_span(page: pymupdf.Page, cell: Cell) -> dict | None:
    """The printed value in a cell: the largest span below its label.

    Largest rather than first because these cells hold one display-size value
    (20 pt) under a 6 pt label, and picking by size is what keeps the two
    apart when a cell is read on a sheet we have never seen.
    """
    inside = [(rect, span) for rect, span in spans(page)
              if cell.rect.contains(rect) and rect.y0 >= cell.label_rect.y1 - 0.6]
    if not inside:
        return None
    rect, span = max(inside, key=lambda pair: pair[1]["size"])
    return {"text": span["text"].strip(), "size": span["size"],
            "font": span["font"], "rect": rect}


def read_cell(page: pymupdf.Page, cell: Cell) -> str:
    """The printed value in a cell.

    The value zone already excludes the label, so every word inside it is part
    of the value — no need for the span dictionary here, which is what keeps
    validation fast.
    """
    inside = [(rect, text) for rect, text in words(page)
              if cell.value_zone.intersects(rect)
              and rect.y0 >= cell.label_rect.y1 - 0.6]
    inside.sort(key=lambda pair: (round(pair[0].y0, 1), pair[0].x0))
    return " ".join(text for _, text in inside).strip()


def value_style(page: pymupdf.Page, cell: Cell) -> tuple[float, bool] | None:
    """`(size, bold)` of the value already in a cell, for matching new text."""
    found = _value_span(page, cell)
    if not found:
        return None
    return found["size"], "bold" in found["font"].lower()


def read_history(page: pymupdf.Page, block: TitleBlock) -> list[HistoryRow]:
    """Every body row of the revision table, topmost first."""
    table = block.history
    found = words(page)
    rows: list[HistoryRow] = []
    for row_rect in table.rows:
        row = HistoryRow()
        for key in table.columns:
            cell_rect = table.cell(row_rect, key)
            inside = [(rect, text) for rect, text in found
                      if cell_rect.intersects(rect)
                      and rect.y0 >= row_rect.y0 - 0.6 and rect.y1 <= row_rect.y1 + 0.6]
            inside.sort(key=lambda pair: pair[0].x0)
            setattr(row, key, " ".join(text for _, text in inside).strip())
        rows.append(row)
    return rows


def topmost_filled(rows: list[HistoryRow]) -> int | None:
    """Index of the highest row carrying text, or None when the table is empty."""
    for index, row in enumerate(rows):
        if row.filled():
            return index
    return None


def target_row_index(rows: list[HistoryRow]) -> int | None:
    """Where the next revision goes: the blank row above the topmost filled one.

    None means the table is full — every row above the newest entry is taken.
    A sheet in that state is reported and skipped rather than guessed at.
    """
    filled = topmost_filled(rows)
    if filled is None:
        return len(rows) - 1        # nothing written yet: start at the bottom
    return filled - 1 if filled > 0 else None


def history_style(page: pymupdf.Page, block: TitleBlock,
                  rows: list[HistoryRow]) -> tuple[float, bool]:
    """Font size and weight of the newest existing row, so a new row matches.

    Falls back to the header labels' own size when the table is empty, which
    keeps a first entry in proportion rather than defaulting to something
    arbitrary.
    """
    table = block.history
    filled = topmost_filled(rows)
    text_spans = spans(page)
    if filled is not None:
        row_rect = table.rows[filled]
        inside = [span for rect, span in text_spans
                  if rect.y0 >= row_rect.y0 - 0.6 and rect.y1 <= row_rect.y1 + 0.6
                  and table.header.x0 - 0.6 <= rect.x0 and rect.x1 <= table.header.x1 + 0.6]
        if inside:
            span = max(inside, key=lambda s: s["size"])
            return span["size"], "bold" in span["font"].lower()

    header = [span for rect, span in text_spans if table.header.contains(rect)]
    if header:
        span = max(header, key=lambda s: s["size"])
        return span["size"], "bold" in span["font"].lower()
    return 7.5, False


def read_current(page: pymupdf.Page, block: TitleBlock) -> dict:
    """Everything the sheet says today, as the UI shows it back."""
    rows = read_history(page, block)
    return {
        "stage": read_cell(page, block.stage),
        "status": read_cell(page, block.status),
        "rev": read_cell(page, block.revision),
        "history_rows": [
            {"rev": r.rev, "description": r.description,
             "date": r.date, "approved_by": r.approved_by}
            for r in rows if r.filled()
        ],
    }

"""Find the title block by its printed labels, never by fixed coordinates.

Every measurement here is derived at run time from two things the sheet
carries itself: the text of the labels, and the ruled lines around them. That
is what lets one implementation handle both coordinate frames the CAD exports
use — a portrait media box displayed rotated 90 degrees, and a native
landscape page — which print identically but whose raw coordinates share
nothing.

Everything is computed in *displayed* space (`page.rect`, rotation applied),
so "above" and "left" mean what they do on the printed sheet. Writing back
needs unrotated coordinates, hence `TitleBlock.derotation`: multiply a
displayed rect or point by it to get the frame PyMuPDF writes in.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

# Labels as printed. REV/DESCRIPTION/DATE/APPROVED BY head the history table;
# PROJECT STAGE and SHEET STATUS head their own full-width cells; REVISION is
# the bottom-right grid cell that always shows the current revision.
STAGE_LABEL = "PROJECT STAGE"
STATUS_LABEL = "SHEET STATUS"
REVISION_LABEL = "REVISION"
HISTORY_LABELS = ("REV", "DESCRIPTION", "DATE", "APPROVED BY")

_COLUMN_KEYS = {"REV": "rev", "DESCRIPTION": "description",
                "DATE": "date", "APPROVED BY": "approved_by"}

# A ruled line is "horizontal" when its ends differ by less than this in y.
_STRAIGHT = 0.5
# How far a label may sit inside its own cell before we stop believing a rule
# bounds it. Labels are printed hard against the cell corner.
_EDGE = 0.6
# A row band shorter than this is a rule drawn twice, not a row.
_MIN_ROW = 3.0


class TitleBlockError(Exception):
    """The sheet does not carry the title block this module knows how to read."""


@dataclass(frozen=True)
class Cell:
    """A ruled cell, its label, and where a value may be written inside it."""
    label: str
    label_rect: pymupdf.Rect      # displayed
    rect: pymupdf.Rect            # displayed, the ruled bounds
    value_zone: pymupdf.Rect      # displayed, clear of the label and the rules


@dataclass(frozen=True)
class HistoryTable:
    """The revision table: fixed columns, rows that fill from the bottom up."""
    columns: dict[str, tuple[float, float]]   # key -> (x0, x1), displayed
    rows: list[pymupdf.Rect]                  # body rows, topmost first
    header: pymupdf.Rect                      # the REV/DESCRIPTION/... row

    def cell(self, row: pymupdf.Rect, key: str) -> pymupdf.Rect:
        x0, x1 = self.columns[key]
        return pymupdf.Rect(x0, row.y0, x1, row.y1)


@dataclass(frozen=True)
class TitleBlock:
    stage: Cell
    status: Cell
    revision: Cell
    history: HistoryTable
    rotation: int
    derotation: pymupdf.Matrix


# ------------------------------------------------------------- ruled lines
def _merge(intervals: list[tuple[float, float]], gap: float = 0.75):
    """Collapse overlapping or touching intervals into the runs they form."""
    merged: list[list[float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]


def _group(segments: list[tuple[float, float, float]], tol: float = 0.25):
    """`(coord, lo, hi)` triples into `{coord: merged runs}`.

    A boundary in these sheets is often drawn once per column rather than as
    one line across the table, so a rule has to be judged on what its pieces
    cover together. Testing single segments silently loses the rule under the
    newest revision row, which is exactly the one the append logic needs.
    """
    grouped: dict[float, list[tuple[float, float]]] = {}
    for coord, low, high in segments:
        grouped.setdefault(round(coord / tol) * tol, []).append((low, high))
    return {coord: _merge(runs) for coord, runs in grouped.items()}


def _covers(runs: list[tuple[float, float]], low: float, high: float,
            tol: float = _EDGE) -> bool:
    return any(a <= low + tol and b >= high - tol for a, b in runs)


def _segments(page: pymupdf.Page) -> tuple[list, list]:
    """Ruled lines in displayed space: (horizontals, verticals).

    Rectangles are unrolled into their four edges — the grid is drawn as a mix
    of both, and a cell boundary is a cell boundary however it was emitted.

    An A1 drawing carries tens of thousands of endpoints, and sending each one
    through `Point * Matrix` costs several times more than reading the drawings
    did — every one of them builds two objects and crosses the binding twice.
    The rotation is a single affine transform, so it is applied here as
    arithmetic on floats: identical result, none of the wrapper cost.
    """
    a, b, c, d, e, f = page.rotation_matrix
    horizontals: list[tuple[float, float, float]] = []
    verticals: list[tuple[float, float, float]] = []

    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                pairs = ((item[1], item[2]),)
            elif item[0] == "re":
                rect = item[1]
                pairs = ((rect.tl, rect.tr), (rect.tr, rect.br),
                         (rect.br, rect.bl), (rect.bl, rect.tl))
            else:
                continue                       # curves are never grid lines
            for start, end in pairs:
                x1 = start.x * a + start.y * c + e
                y1 = start.x * b + start.y * d + f
                x2 = end.x * a + end.y * c + e
                y2 = end.x * b + end.y * d + f
                if abs(y1 - y2) < _STRAIGHT and abs(x1 - x2) >= _STRAIGHT:
                    horizontals.append((y1, min(x1, x2), max(x1, x2)))
                elif abs(x1 - x2) < _STRAIGHT and abs(y1 - y2) >= _STRAIGHT:
                    verticals.append((x1, min(y1, y2), max(y1, y2)))
    return horizontals, verticals


# ------------------------------------------------------------------- text
# Extracting a text page from an A1 CAD drawing costs about a second, and the
# reader asks for spans half a dozen times per sheet. Holding the result on the
# page turns that into one extraction. It is cleared explicitly whenever the
# page is edited — see `forget_spans` — so nothing can read a stale layout.
_SPAN_CACHE = "_maec_rebadge_spans"


def spans(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, dict]]:
    """Every non-blank text span with its displayed bounding box."""
    cached = getattr(page, _SPAN_CACHE, None)
    if cached is not None:
        return cached

    matrix = page.rotation_matrix
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip():
                    out.append((pymupdf.Rect(span["bbox"]) * matrix, span))
    try:
        setattr(page, _SPAN_CACHE, out)
    except AttributeError:
        pass                      # a page that will not hold it just re-reads
    return out


# Building the span dictionary costs about a second and a half on these
# sheets, because it carries font and size for every glyph. `get_text("words")`
# answers "what text is where" in about ten milliseconds. Only style matching
# needs the expensive one, so everything else asks for words.
_WORD_CACHE = "_maec_rebadge_words"


def words(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Every word with its displayed box — the cheap read."""
    cached = getattr(page, _WORD_CACHE, None)
    if cached is not None:
        return cached

    matrix = page.rotation_matrix
    out = [(pymupdf.Rect(x0, y0, x1, y1) * matrix, text)
           for x0, y0, x1, y1, text, *_ in page.get_text("words")
           if text.strip()]
    try:
        setattr(page, _WORD_CACHE, out)
    except AttributeError:
        pass
    return out


# `search_for` builds a text page, uses it for one query and throws it away,
# and a sheet is searched once per label plus again for each value read. On
# these drawings that extraction is ~10 ms, so the searches cost more than the
# thing they are looking through. Extract once and pass it to every search.
_TEXT_PAGE_CACHE = "_maec_rebadge_textpage"


def text_page(page: pymupdf.Page) -> pymupdf.TextPage:
    """The sheet's text page, extracted once."""
    cached = getattr(page, _TEXT_PAGE_CACHE, None)
    if cached is not None:
        return cached

    built = page.get_textpage()
    try:
        setattr(page, _TEXT_PAGE_CACHE, built)
    except AttributeError:
        pass                      # a page that will not hold it just re-reads
    return built


def search(page: pymupdf.Page, text: str) -> list[pymupdf.Rect]:
    """Where `text` appears, in unrotated coordinates, via the shared page."""
    return page.search_for(text, textpage=text_page(page))


def forget_spans(page: pymupdf.Page) -> None:
    """Drop the cached text. Call after anything that changes the page."""
    for attribute in (_SPAN_CACHE, _WORD_CACHE, _TEXT_PAGE_CACHE):
        try:
            delattr(page, attribute)
        except AttributeError:
            pass


def _labels(page: pymupdf.Page, text: str) -> list[pymupdf.Rect]:
    matrix = page.rotation_matrix
    return [hit * matrix for hit in search(page, text)]


def find_label(page: pymupdf.Page, text: str) -> pymupdf.Rect:
    """The place this label is printed, in displayed coordinates."""
    hits = _labels(page, text)
    if not hits:
        raise TitleBlockError(f"label {text!r} not found")
    return hits[0]


# ------------------------------------------------------------------ cells
def _cell_around(label: pymupdf.Rect, rows, cols) -> pymupdf.Rect:
    """The ruled box the label sits in the top-left of."""
    crossing = [y for y, runs in rows.items() if _covers(runs, label.x0, label.x1)]
    above = [y for y in crossing if y <= label.y0 + _EDGE]
    below = [y for y in crossing if y >= label.y1 - _EDGE]
    if not above or not below:
        raise TitleBlockError("no ruled line above or below the label")
    top, bottom = max(above), min(below)

    middle = (top + bottom) / 2
    beside = [x for x, runs in cols.items() if _covers(runs, middle, middle)]
    left = [x for x in beside if x <= label.x0 + _EDGE]
    right = [x for x in beside if x >= label.x1 - _EDGE]
    if not left or not right:
        raise TitleBlockError("no ruled line either side of the label")
    return pymupdf.Rect(max(left), top, min(right), bottom)


def _value_zone(cell: pymupdf.Rect, label: pymupdf.Rect) -> pymupdf.Rect:
    """The part of a cell a value may occupy: below the label, inside the rules.

    Redaction is clipped to this, which is what keeps the label and the table
    borders when the old value is removed.
    """
    return pymupdf.Rect(cell.x0 + 1.5, label.y1 + 0.8, cell.x1 - 1.5, cell.y1 - 1.5)


def _labelled_cell(page, text, rows, cols, *, label_rect=None) -> Cell:
    label = label_rect if label_rect is not None else find_label(page, text)
    cell = _cell_around(label, rows, cols)
    return Cell(text, label, cell, _value_zone(cell, label))


# ---------------------------------------------------------- history table
def _history(page, rows_by_y, cols_by_x, stage_cell: Cell) -> HistoryTable:
    """Columns from the header labels, rows from the rules above them.

    The header row carries REV / DESCRIPTION / DATE / APPROVED BY immediately
    above PROJECT STAGE. Column edges are the verticals crossing it; body rows
    are the bands stacked above it, which is the direction the table grows.
    """
    top_of_stage = stage_cell.rect.y0
    header_labels = {}
    for name in HISTORY_LABELS:
        candidates = [r for r in _labels(page, name) if r.y1 <= top_of_stage + _EDGE]
        if not candidates:
            raise TitleBlockError(f"history label {name!r} not found above PROJECT STAGE")
        header_labels[name] = max(candidates, key=lambda r: r.y0)

    leftmost = min(header_labels.values(), key=lambda r: r.x0)
    header = _cell_around(leftmost, rows_by_y, cols_by_x)
    right_edge = max(_cell_around(r, rows_by_y, cols_by_x).x1
                     for r in header_labels.values())
    header = pymupdf.Rect(header.x0, header.y0, right_edge, header.y1)

    middle = (header.y0 + header.y1) / 2
    edges = sorted(x for x, runs in cols_by_x.items()
                   if _covers(runs, middle, middle)
                   and header.x0 - _EDGE <= x <= header.x1 + _EDGE)
    if len(edges) < len(HISTORY_LABELS) + 1:
        raise TitleBlockError("revision table has too few column rules")

    columns: dict[str, tuple[float, float]] = {}
    for name, label in header_labels.items():
        centre = (label.x0 + label.x1) / 2
        left = max((e for e in edges if e <= centre), default=None)
        right = min((e for e in edges if e >= centre), default=None)
        if left is None or right is None:
            raise TitleBlockError(f"no column found for {name!r}")
        columns[_COLUMN_KEYS[name]] = (left, right)

    rules = sorted((y for y, runs in rows_by_y.items()
                    if y <= header.y0 + _EDGE and _covers(runs, header.x0, header.x1)),
                   reverse=True)
    rows: list[pymupdf.Rect] = []
    for lower, upper in zip(rules, rules[1:]):
        height = lower - upper
        if height < _MIN_ROW:
            continue                    # a rule drawn twice, not a row
        if rows and height > 2.5 * (rows[-1].y1 - rows[-1].y0):
            break                       # past the top of the table
        rows.append(pymupdf.Rect(header.x0, upper, header.x1, lower))
    if not rows:
        raise TitleBlockError("revision table has no rows")
    rows.reverse()                      # topmost first
    return HistoryTable(columns, rows, header)


def find_title_block(page: pymupdf.Page) -> TitleBlock:
    """Locate every region this module edits, or say why it cannot."""
    horizontals, verticals = _segments(page)
    if not horizontals or not verticals:
        raise TitleBlockError("no ruled lines on the sheet — is it a scan?")
    rows_by_y, cols_by_x = _group(horizontals), _group(verticals)

    stage = _labelled_cell(page, STAGE_LABEL, rows_by_y, cols_by_x)
    status = _labelled_cell(page, STATUS_LABEL, rows_by_y, cols_by_x)

    # REVISION sits low on the sheet; REV in the history table is a different
    # cell entirely, so take the bottom-most match.
    revision_labels = _labels(page, REVISION_LABEL)
    if not revision_labels:
        raise TitleBlockError(f"label {REVISION_LABEL!r} not found")
    revision = _labelled_cell(page, REVISION_LABEL, rows_by_y, cols_by_x,
                              label_rect=max(revision_labels, key=lambda r: r.y0))

    history = _history(page, rows_by_y, cols_by_x, stage)
    return TitleBlock(stage=stage, status=status, revision=revision,
                      history=history, rotation=page.rotation,
                      derotation=page.derotation_matrix)

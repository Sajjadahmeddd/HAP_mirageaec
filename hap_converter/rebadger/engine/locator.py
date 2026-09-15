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


# The title block sits in the right-hand strip of the sheet and the drawing
# fills the rest. Only line work touching this region is read: from a little
# left of the PROJECT STAGE label — the history table and the cells all start
# at that column — to the sheet's right edge, and from well above the label
# down to the bottom edge. The revision table grows upward from its header; in
# both drawing sets seen so far it reaches at most ~120 pt above PROJECT STAGE,
# so 400 pt leaves room for a much taller table without reading the drawing.
_REGION_LEFT = 40.0
_REGION_ABOVE = 400.0


def _title_region(page: pymupdf.Page, stage_label: pymupdf.Rect) -> pymupdf.Rect:
    """The displayed area whose ruled lines can bound a title-block cell."""
    return pymupdf.Rect(stage_label.x0 - _REGION_LEFT, stage_label.y0 - _REGION_ABOVE,
                        page.rect.x1, page.rect.y1)


def _segments(page: pymupdf.Page, region: pymupdf.Rect) -> tuple[list, list]:
    """Ruled lines in displayed space near `region`: (horizontals, verticals).

    Why a region, and why a callback. This used to be `page.get_drawings()`,
    which builds a Python object for every vector path on the sheet. The
    drawing is never edited, yet it is nearly all of that: ELE-1010 of the
    00044-DHCGP set carries 692,017 items, and reading them peaked at 2.6 GB —
    five times what the deployed service has, so a single upload killed it and
    the browser was left with a bare 502. `get_cdrawings(callback=...)` hands
    over one path at a time and keeps nothing; a path whose bounding box misses
    the region is dropped after one comparison. Measured on ELE-1010: 53 MB.

    A path is kept whole when its box touches the region, so a rule that runs
    across the sheet is still seen at its full length — `_covers` needs that.

    Why everything in the callback is guarded. PyMuPDF runs the callback from
    inside MuPDF, and an exception that escapes it does not come back as an
    exception: it takes the process down (exit 139 when tried deliberately) —
    in production, the whole web service. So the first failure is recorded,
    the rest of the page is skipped, and the sheet is refused as unreadable.

    Rectangles and quads are unrolled into their four edges — the grid is drawn
    as a mix of lines, rectangles and, on ELE-1111, the sheet frame as a single
    quad, and a cell boundary is a cell boundary however it was emitted. Edges
    that are not axis-aligned fail the straightness test and drop out.

    The rotation is one affine transform, applied as float arithmetic rather
    than `Point * Matrix`, which on tens of thousands of endpoints costs several
    times more than reading the drawings did.
    """
    a, b, c, d, e, f = page.rotation_matrix
    zone = (region * page.derotation_matrix).normalize()
    zx0, zy0, zx1, zy1 = zone.x0, zone.y0, zone.x1, zone.y1
    horizontals: list[tuple[float, float, float]] = []
    verticals: list[tuple[float, float, float]] = []
    failure: list[BaseException] = []

    def edge(sx, sy, ex, ey):
        x1 = sx * a + sy * c + e
        y1 = sx * b + sy * d + f
        x2 = ex * a + ey * c + e
        y2 = ex * b + ey * d + f
        if abs(y1 - y2) < _STRAIGHT and abs(x1 - x2) >= _STRAIGHT:
            horizontals.append((y1, min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < _STRAIGHT and abs(y1 - y2) >= _STRAIGHT:
            verticals.append((x1, min(y1, y2), max(y1, y2)))

    def keep(path):
        if failure:
            return
        try:
            px0, py0, px1, py1 = path["rect"]
            if px1 < zx0 or px0 > zx1 or py1 < zy0 or py0 > zy1:
                return                             # the drawing, not the title block
            for item in path["items"]:
                kind = item[0]
                if kind == "l":
                    (sx, sy), (ex, ey) = item[1], item[2]
                    edge(sx, sy, ex, ey)
                elif kind == "re":
                    x0, y0, x1, y1 = item[1]
                    edge(x0, y0, x1, y0)
                    edge(x1, y0, x1, y1)
                    edge(x1, y1, x0, y1)
                    edge(x0, y1, x0, y0)
                elif kind == "qu":
                    (ulx, uly), (urx, ury), (llx, lly), (lrx, lry) = item[1]
                    edge(ulx, uly, urx, ury)
                    edge(urx, ury, lrx, lry)
                    edge(lrx, lry, llx, lly)
                    edge(llx, lly, ulx, uly)
                # curves are never grid lines
        except Exception as exc:                   # must not cross into MuPDF
            failure.append(exc)

    page.get_cdrawings(callback=keep)
    if failure:
        raise TitleBlockError(f"could not read the sheet's line work: {failure[0]}")
    return horizontals, verticals


# ------------------------------------------------------------------- text
# Extracting a text page from an A1 CAD drawing costs about a second, and the
# reader asks for spans half a dozen times per sheet. Holding the result on the
# page turns that into one extraction. It is cleared explicitly whenever the
# page is edited — see `forget_spans` — so nothing can read a stale layout.
_SPAN_CACHE = "_maec_rebadge_spans"

# `get_text("dict")` defaults to TEXTFLAGS_DICT, which sets TEXT_PRESERVE_IMAGES
# — so MuPDF decodes every raster on the page in order to build image blocks.
# These drawings carry ~50 of them at around 1000x880 each, and we read none of
# them: all this call is ever asked for is the font size and weight of four
# cells. Clearing that one flag takes the call from ~1.0s to ~9ms and returns
# byte-for-byte identical spans.
_STYLE_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES


def spans(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, dict]]:
    """Every non-blank text span with its displayed bounding box."""
    cached = getattr(page, _SPAN_CACHE, None)
    if cached is not None:
        return cached

    matrix = page.rotation_matrix
    out = []
    for block in page.get_text("dict", flags=_STYLE_FLAGS)["blocks"]:
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

    Labels are believed only on the header row itself. The same words can be
    printed anywhere on a sheet, and a sheet can misprint its own heading: the
    whole 00044-DHCGP set reads "APRROVED BY", and the only "APPROVED BY" on
    those sheets is a note near the top. Taking the nearest match above PROJECT
    STAGE put APPROVED BY in the DATE column — the approver's initials were
    printed over the date and the old approver was left in place. So the row is
    fixed by DESCRIPTION, REV and DATE must be on it, and APPROVED BY is read
    from it when spelled as expected and is otherwise the column right of DATE.
    """
    top_of_stage = stage_cell.rect.y0
    above = [r for r in _labels(page, "DESCRIPTION") if r.y1 <= top_of_stage + _EDGE]
    if not above:
        raise TitleBlockError("history label 'DESCRIPTION' not found above PROJECT STAGE")
    anchor = max(above, key=lambda r: r.y0)
    row_middle = (anchor.y0 + anchor.y1) / 2

    def on_header_row(name: str) -> list[pymupdf.Rect]:
        return [r for r in _labels(page, name)
                if r.y0 - _EDGE <= row_middle <= r.y1 + _EDGE and r.y1 <= top_of_stage + _EDGE]

    header_labels = {}
    for name in HISTORY_LABELS:
        hits = on_header_row(name)
        if hits:
            header_labels[name] = min(hits, key=lambda r: r.x0)
        elif name != "APPROVED BY":
            raise TitleBlockError(f"history label {name!r} not found on the revision table header")

    leftmost = min(header_labels.values(), key=lambda r: r.x0)
    header = _cell_around(leftmost, rows_by_y, cols_by_x)
    middle = (header.y0 + header.y1) / 2
    crossing = sorted(x for x, runs in cols_by_x.items()
                      if _covers(runs, middle, middle) and x >= header.x0 - _EDGE)

    if "APPROVED BY" in header_labels:
        right_edge = max(_cell_around(r, rows_by_y, cols_by_x).x1
                         for r in header_labels.values())
    else:
        date_right = _cell_around(header_labels["DATE"], rows_by_y, cols_by_x).x1
        beyond = [x for x in crossing if x > date_right + _EDGE]
        if not beyond:
            raise TitleBlockError("no column found for 'APPROVED BY' right of DATE")
        right_edge = beyond[0]
    header = pymupdf.Rect(header.x0, header.y0, right_edge, header.y1)

    edges = [x for x in crossing if x <= header.x1 + _EDGE]
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
    if "approved_by" not in columns:
        columns["approved_by"] = (columns["date"][1], right_edge)

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
    """Locate every region this module edits, or say why it cannot.

    PROJECT STAGE is found first, from the text layer, because it says where
    the title block is — and so which line work is worth reading at all.
    """
    stage_label = find_label(page, STAGE_LABEL)
    horizontals, verticals = _segments(page, _title_region(page, stage_label))
    if not horizontals or not verticals:
        raise TitleBlockError("no ruled lines around the title block — is it a scan?")
    rows_by_y, cols_by_x = _group(horizontals), _group(verticals)

    stage = _labelled_cell(page, STAGE_LABEL, rows_by_y, cols_by_x, label_rect=stage_label)
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

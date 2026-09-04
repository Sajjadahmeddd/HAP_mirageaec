"""Read back the project block that heads a downloaded schedule.

`xlsx_exporter.write_project_header` writes rows 1-5: a title, the client's
logo in the merged right-hand zone, and eight label/value pairs. This reads
that back, so AirSizer can offer the details a schedule already carries
instead of asking an engineer to type all nine inputs a second time.

Nothing here raises on a file that is simply not one of ours — an engineer
may load any spreadsheet, and "no details found" is an ordinary answer, not
an error. Only the caller knows whether that matters.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from .synthesizer import PROJECT_FIELDS

# where write_project_header puts each half of a label/value pair
_LEFT_LABEL, _LEFT_VALUE = 1, 2
_RIGHT_LABEL, _RIGHT_VALUE = 7, 8
_FIRST_FIELD_ROW = 2

# the logo occupies the merged zone in row 1 from this column on
_LOGO_COL_INDEX = 6          # zero-based, as openpyxl anchors report it


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_project_header(xlsx_path: str | Path) -> tuple[dict[str, str], bytes | None]:
    """Return `(details, logo_png_bytes)` from a schedule's header block.

    `details` is keyed exactly as `synthesizer.PROJECT_FIELDS` and the project
    details form, so it can be handed straight back to either. A field the
    sheet does not carry is absent rather than blank, which lets the caller
    tell "not filled in" from "not one of our schedules" — an empty dict.

    The logo comes back as image bytes, or None when the sheet has none, which
    is normal: a CSV cannot embed one at all.
    """
    try:
        workbook = openpyxl.load_workbook(xlsx_path)
    except Exception:
        return {}, None            # not a workbook, or one we cannot open

    sheet = workbook.worksheets[0]
    labels = {label: key for key, label in PROJECT_FIELDS}

    details: dict[str, str] = {}
    for row in range(_FIRST_FIELD_ROW, _FIRST_FIELD_ROW + 4):
        for label_col, value_col in ((_LEFT_LABEL, _LEFT_VALUE),
                                     (_RIGHT_LABEL, _RIGHT_VALUE)):
            key = labels.get(_text(sheet.cell(row=row, column=label_col).value))
            if key is None:
                continue           # some other spreadsheet's row 2-5
            value = _text(sheet.cell(row=row, column=value_col).value)
            if value:
                details[key] = value

    return details, _read_logo(sheet)


def _read_logo(sheet) -> bytes | None:
    """The image anchored in row 1's right-hand zone, if there is one.

    openpyxl exposes embedded images only through a private attribute; a
    workbook written by another tool may not have it at all, so this never
    assumes it exists.
    """
    for image in getattr(sheet, "_images", ()):
        anchor = getattr(image, "anchor", None)
        start = getattr(anchor, "_from", None)
        # anything anchored to the header row counts; a picture further down
        # the sheet is somebody's annotation, not the schedule's logo
        if start is not None and start.row == 0 and start.col >= _LOGO_COL_INDEX:
            try:
                return image._data()
            except Exception:
                return None
    return None


def has_details(details: dict[str, str]) -> bool:
    """True when every printed field came back, so the form can be filled
    without leaving an engineer to notice a gap."""
    return all(key in details for key, _ in PROJECT_FIELDS)

"""Check a sheet, rebadge a sheet, rebadge a batch.

Two rules shape everything here. A sheet that cannot be edited correctly is
never emitted — it is reported with a reason and skipped, and the batch
carries on. And the source file is never written to: every edit happens on a
document opened from bytes, and the result is new bytes.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pymupdf

from . import editor, locator, reader, verify
from .locator import TitleBlock, TitleBlockError, find_title_block
from .models import BatchResult, RebadgeInputs, SheetCheck, SheetResult

# Only single-sheet drawings are in scope; a bundled set is reported rather
# than half-processed.
_LABELS = ("PROJECT STAGE", "SHEET STATUS", "REV",
           "DESCRIPTION", "DATE", "APPROVED BY", "REVISION")


def _open(source: str | Path | bytes) -> pymupdf.Document:
    if isinstance(source, bytes):
        return pymupdf.open(stream=source, filetype="pdf")
    return pymupdf.open(source)


def _labels_found(page: pymupdf.Page) -> dict[str, bool]:
    return {label: bool(locator.search(page, label)) for label in _LABELS}


def check(source: str | Path | bytes, filename: str) -> SheetCheck:
    """What we can and cannot do with this sheet, before touching it."""
    try:
        doc = _open(source)
    except Exception as exc:
        return SheetCheck(filename, ok=False, errors=[f"not a readable PDF ({exc})"])

    with doc:
        if doc.page_count != 1:
            return SheetCheck(
                filename, ok=False,
                errors=[f"expected a single-sheet drawing, found {doc.page_count} pages"],
            )
        page = doc[0]
        found = _labels_found(page)
        result = SheetCheck(filename, ok=False, rotation=page.rotation,
                            labels_found=found)

        if not page.get_text("text").strip():
            result.errors.append(
                "no text layer — a scanned or flattened drawing cannot be rebadged")
            return result

        try:
            block = find_title_block(page)
        except TitleBlockError as exc:
            result.errors.append(f"title block not readable: {exc}")
            return result

        # No room check: the latest revision row is overwritten rather than
        # added to, so a full table rebadges like any other.
        result.current = reader.read_current(page, block)
        result.ok = True
        return result


def rebadge(source: str | Path | bytes, inputs: RebadgeInputs,
            filename: str) -> tuple[bytes | None, SheetResult]:
    """Apply the six values to one sheet. Returns `(new_pdf_bytes, result)`.

    `None` bytes means the sheet was not edited; the result says why. The
    input is never modified — the document is saved to a fresh buffer.
    """
    result = SheetResult(filename, ok=False, new_rev=inputs.rev)

    missing = inputs.missing()
    if missing:
        result.errors.append(f"missing input: {', '.join(missing)}")
        return None, result

    try:
        doc = _open(source)
    except Exception as exc:
        result.errors.append(f"not a readable PDF ({exc})")
        return None, result

    with doc:
        if doc.page_count != 1:
            result.errors.append(
                f"expected a single-sheet drawing, found {doc.page_count} pages")
            return None, result

        page = doc[0]
        try:
            block = find_title_block(page)
        except TitleBlockError as exc:
            result.errors.append(f"title block not readable: {exc}")
            return None, result

        rows = reader.read_history(page, block)
        target = reader.overwrite_row_index(rows)

        before_text = verify.span_index(page)
        result.previous_rev = reader.read_cell(page, block.revision)
        if result.previous_rev and result.previous_rev.strip().upper() == inputs.rev.strip().upper():
            result.warnings.append(
                f"revision is already {result.previous_rev} — nothing changes on this sheet")

        stage_style = _style(reader.value_style(page, block.stage), 20.0, True)
        status_style = _style(reader.value_style(page, block.status), 20.0, True)
        rev_style = _style(reader.value_style(page, block.revision), 20.0, False)
        row_style = editor.TextStyle(*reader.history_style(page, block, rows))

        try:
            # in place: the old value leaves the file, the label and rules stay
            for cell, text, style in (
                (block.stage, inputs.project_stage.upper(), stage_style),
                (block.status, inputs.sheet_status.upper(), status_style),
            ):
                report = editor.replace_cell(page, block, cell, text, style)
                result.warnings += report.warnings

            # overwritten: the latest revision row is replaced where it
            # stands, never stacked on; older rows below it are untouched
            result.warnings += editor.overwrite_history_row(
                page, block, inputs, target, row_style).warnings

            # overwritten: this cell always shows the current revision
            result.warnings += editor.overwrite_revision_cell(
                page, block, inputs.rev, rev_style).warnings
        except (editor.RedactionError, editor.CellOverflowError) as exc:
            result.errors.append(str(exc))
            return None, result

        # The drawing is not assumed intact: rewriting the content stream is
        # the one thing that could disturb it, so it is checked rather than
        # trusted. Anything that moved outside the cells we edited is named.
        edited = [block.stage.rect, block.status.rect, block.revision.rect,
                  block.history.rows[target]]
        for problem in verify.displaced(before_text, verify.span_index(page), edited):
            result.warnings.append(f"drawing content: {problem}")

        buffer = io.BytesIO()
        doc.save(buffer, garbage=3, deflate=True)
        result.ok = True
        return buffer.getvalue(), result


def _style(measured, fallback_size: float, fallback_bold: bool) -> editor.TextStyle:
    if measured is None:
        return editor.TextStyle(fallback_size, fallback_bold)
    size, bold = measured
    return editor.TextStyle(size, bold)


def output_name(original: str, taken: set[str]) -> str:
    """`<stem>_rebadged.pdf`, versioned if that name is already spoken for."""
    stem = Path(original).stem
    candidate = f"{stem}_rebadged.pdf"
    version = 2
    while candidate in taken:
        candidate = f"{stem}_rebadged_v{version}.pdf"
        version += 1
    return candidate


def rebadge_batch(files: list[tuple[str, bytes]],
                  inputs: RebadgeInputs) -> tuple[dict[str, bytes], BatchResult]:
    """Apply one set of values to every sheet.

    A sheet that fails is recorded and skipped; the rest of the batch still
    produces output, because a set of thirty drawings should not be lost to
    one bad file.
    """
    outputs: dict[str, bytes] = {}
    batch = BatchResult()
    for filename, data in files:
        payload, result = rebadge(data, inputs, filename)
        batch.sheets.append(result)
        if payload is not None:
            outputs[output_name(filename, set(outputs))] = payload
    return outputs, batch


def preview(source: bytes, inputs: RebadgeInputs, filename: str,
            zoom: float = 2.0) -> tuple[bytes | None, SheetResult]:
    """A PNG of the title block as it will look, from the real pipeline.

    The edits are the same ones apply performs — this rasterises the actual
    result rather than drawing a mock of it, so what the engineer approves is
    what the workbook will contain.
    """
    payload, result = rebadge(source, inputs, filename)
    if payload is None:
        return None, result

    with _open(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        clip = pymupdf.Rect(
            block.history.header.x0 - 10,
            block.history.rows[0].y0 - 14,
            block.stage.rect.x1 + 10,
            block.status.rect.y1 + 14,
        )
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
        return pixmap.tobytes("png"), result


def build_zip(outputs: dict[str, bytes], audit: tuple[str, bytes] | None) -> bytes:
    """The batch as one archive: every rebadged sheet plus the audit record."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in outputs.items():
            archive.writestr(name, data)
        if audit is not None:
            archive.writestr(audit[0], audit[1])
    return buffer.getvalue()

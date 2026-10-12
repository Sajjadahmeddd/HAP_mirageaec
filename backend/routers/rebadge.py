"""PDF Rebadging over HTTP: validate, preview, apply.

Thin wrappers, as elsewhere: every route reads uploads into memory, calls one
engine function, and streams the result back. Nothing is stored — a batch is
processed inside the request that asked for it.

The engine takes and returns bytes rather than paths, so uploads never reach
disk at all. Only the response file is written out, into a temp directory that
Starlette removes once it has finished streaming.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from hap_converter.rebadger.engine import audit as audit_mod
from hap_converter.rebadger.engine import pipeline
from hap_converter.rebadger.engine.models import RebadgeInputs

from ..deps import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/rebadge", tags=["rebadge"])


# These sheets' title blocks are set in Arial Narrow, but the rebadger writes
# in Helvetica, which is wider -- so editor.py steps the size down a quarter
# point at a time until the value fits, and says so. On this drawing set that
# is not the exception, it is the normal path: every sheet reports it, every
# time. The note tells an engineer nothing they can act on, it buried the two
# warnings that DO matter, and 28 copies of it overflowed nginx's 4 KB header
# buffer, which returned 502 on a batch the backend had already completed.
#
# Dropped here rather than in the engine, so the engine stays byte-identical.
# This hides only the notification: the value is still shrunk to fit exactly
# as before, and text that cannot fit even at the floor still raises
# CellOverflowError in editor.py and fails that sheet properly.
_COSMETIC = ("text reduced from",)


def _worth_reporting(warnings: list[str]) -> list[str]:
    """Warnings an engineer can act on. See _COSMETIC above."""
    return [w for w in warnings if not any(c in w for c in _COSMETIC)]


# These three routes are declared `def`, not `async def`, on purpose. Every one
# of them spends seconds inside PyMuPDF, which is blocking C code. An `async`
# route runs on the event loop itself, so that work stalls the entire worker —
# no other request is read, and the health check cannot be answered either.
# Declared sync, Starlette runs them in its threadpool and the loop stays free.
PDF_SUFFIX = ".pdf"
PDF_MIME = "application/pdf"
ZIP_MIME = "application/zip"

# One request handles a whole submission set. Past this the wait stops being
# a loading state and starts being a job queue, which is out of scope.
MAX_SHEETS = 200


def _read(uploads: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Uploads as `(filename, bytes)`, rejecting anything that is not a PDF."""
    if not uploads:
        raise HTTPException(status_code=400, detail="No PDF supplied.")
    if len(uploads) > MAX_SHEETS:
        raise HTTPException(
            status_code=400,
            detail=f"{len(uploads)} sheets is more than this can process at once "
                   f"(limit {MAX_SHEETS}). Split the set and run it twice.",
        )

    files: list[tuple[str, bytes]] = []
    total = 0
    for upload in uploads:
        name = Path(upload.filename or "sheet.pdf").name
        if Path(name).suffix.lower() != PDF_SUFFIX:
            raise HTTPException(status_code=400, detail=f"{name}: expected a .pdf file.")
        data = upload.file.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="That drawing set is too large.")
        if not data:
            raise HTTPException(status_code=400, detail=f"{name} is empty.")
        files.append((name, data))
    return files


def _inputs(payload: str) -> RebadgeInputs:
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed inputs: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Inputs must be an object.")

    inputs = RebadgeInputs.from_dict(data)
    missing = inputs.missing()
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"All six values are required. Missing: {', '.join(missing)}.",
        )
    return inputs


@router.post("/validate")
def validate(files: list[UploadFile] = File(...)):
    """What each sheet will and will not allow, before anything is edited."""
    checks = []
    for name, data in _read(files):
        check = pipeline.check(data, name)
        checks.append({
            "filename": check.filename,
            "ok": check.ok,
            "rotation": check.rotation,
            "labels_found": check.labels_found,
            "missing_labels": check.missing_labels(),
            "current": check.current,
            "warnings": check.warnings,
            "errors": check.errors,
        })
    return {"sheets": checks,
            "ok_count": sum(1 for c in checks if c["ok"]),
            "error_count": sum(1 for c in checks if not c["ok"])}


@router.post("/preview")
def preview(file: UploadFile = File(...), payload: str = Form(...)):
    """The title block as it will actually look, rendered from the real edit."""
    inputs = _inputs(payload)
    (name, data), = _read([file])

    png, result = pipeline.preview(data, inputs, name)
    if png is None:
        raise HTTPException(
            status_code=422,
            detail=f"{name}: {'; '.join(result.errors) or 'cannot be rebadged.'}",
        )
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Rebadge-Warnings": json.dumps(_worth_reporting(result.warnings))},
    )


# A response header block must fit in ONE proxy buffer, and the default is a
# single memory page -- 4096 bytes. frontend/nginx.conf raises ours to 16k,
# but that only helps where we own the proxy; this app also runs on Render,
# where we do not. So the bound belongs here as well.
#
# Bounded by BYTES, not entry count. "Cap it at 20 sheets" bounds nothing:
# measured on real batches, one entry is 165 B for a rejected sheet but 323 B
# for one carrying warnings, so twenty of the latter is 6.5 KB -- still over
# the 4 KB default. A byte budget holds whatever the messages turn out to be.
#
# 3000 B leaves room for the JSON envelope plus the ordinary headers
# (Content-Disposition, ETag, CSP and the rest) inside 4096, and gives better
# than 5x margin against the 16k nginx now allows.
_SUMMARY_BUDGET = 3000
_SUMMARY_MAX_SHEETS = 20


def _summary(batch) -> str:
    """A compact result summary for the response header.

    Only sheets with something to say are listed: on a 126-sheet set the
    counts carry the rest, and a header has to stay small enough to send.

    warning_count is recomputed from the filtered warnings rather than taken
    from the batch, so the Export screen's "N informational" always agrees
    with the rows listed beneath it.

    The list was previously unbounded, which made the ERROR path the overflow
    path: the header grew largest exactly when something was wrong, so a batch
    of sheets that all failed would 502 instead of reporting which failed and
    why. Failed sheets are therefore emitted FIRST, and `truncated` says how
    many notable sheets did not fit. error_count and warning_count stay full
    counts, so the Export screen's totals remain correct either way.
    """
    kept = [(s, _worth_reporting(s.warnings)) for s in batch.sheets]
    notable = [(s, w) for s, w in kept if w or s.errors or not s.ok]
    # False sorts before True, so failures lead; the sort is stable, so the
    # original sheet order survives within each group.
    notable.sort(key=lambda pair: pair[0].ok)

    entries: list[dict] = []
    used = 0
    for sheet, warnings in notable:
        entry = {"filename": sheet.filename, "ok": sheet.ok,
                 "previous_rev": sheet.previous_rev, "new_rev": sheet.new_rev,
                 "warnings": warnings, "errors": sheet.errors}
        size = len(json.dumps(entry)) + 1          # +1 for the separating comma
        # Always emit at least one, so a single verbose entry is reported
        # rather than silently dropped.
        if entries and (used + size > _SUMMARY_BUDGET
                        or len(entries) >= _SUMMARY_MAX_SHEETS):
            break
        entries.append(entry)
        used += size

    return json.dumps({
        "total": len(batch.sheets),
        "ok_count": batch.ok_count,
        "error_count": batch.error_count,
        "warning_count": sum(len(w) for _, w in kept),
        "sheets": entries,
        "truncated": len(notable) - len(entries),
    })


@router.post("/apply")
def apply(files: list[UploadFile] = File(...), payload: str = Form(...)):
    """Rebadge the set: one PDF, or a ZIP of every sheet plus the audit."""
    inputs = _inputs(payload)
    sheets = _read(files)

    outputs, batch = pipeline.rebadge_batch(sheets, inputs)
    if not outputs:
        reasons = "; ".join(f"{s.filename}: {', '.join(s.errors)}"
                            for s in batch.sheets if s.errors)
        raise HTTPException(status_code=422,
                            detail=f"No sheet could be rebadged. {reasons}")

    audit_file = (audit_mod.audit_name(), audit_mod.build_audit(inputs, batch))
    single = len(outputs) == 1 and batch.error_count == 0

    if single:
        name, data = next(iter(outputs.items()))
        media = PDF_MIME
    else:
        name = "Rebadged_Drawings.zip"
        data = pipeline.build_zip(outputs, audit_file)
        media = ZIP_MIME

    # Not workspace(): that removes the directory when the block exits, which
    # is before Starlette has streamed the file. Cleanup rides on the response.
    scratch = Path(tempfile.mkdtemp(prefix="maec_rebadge_"))
    try:
        target = scratch / name
        target.write_bytes(data)
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    return FileResponse(
        target,
        media_type=media,
        filename=name,
        headers={"X-Rebadge-Summary": _summary(batch)},
        background=BackgroundTask(shutil.rmtree, scratch, ignore_errors=True),
    )

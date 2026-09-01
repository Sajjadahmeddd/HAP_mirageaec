"""HAPExt over HTTP: PDF -> schedule, and the Change Request append.

Every route calls the same `hap_converter.engine.pipeline` functions the
PySide6 window calls. The one difference the web forces is *where* the result
lives between steps: the desktop stages a CSV in %LOCALAPPDATA% and reads it
back when the user finally clicks Download. Render's disk cannot be trusted
between requests, so `convert` returns the rows to the browser and `download`
rebuilds the file from those rows — through `synthesizer`/`xlsx_exporter`, so
the bytes are identical either way.
"""

from __future__ import annotations

import base64
import csv
import json
import shutil
import tempfile
from pathlib import Path

import openpyxl
import pymupdf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from hap_converter.engine import change_request, exporter, pipeline
from hap_converter.engine.synthesizer import LOGO_KEY, PROJECT_FIELDS, build_project_header
from hap_converter.engine.xlsx_exporter import write_fcu_xlsx

from ..deps import hapext_config, save_upload, workspace

router = APIRouter(prefix="/api/hapext", tags=["hapext"])

# The desktop failure page keys its explanations off issue.field; the same
# strings travel to the browser so the React page can branch identically.
LOGO_SUFFIXES = (".png", ".jpg", ".jpeg")


def _issues(result) -> list[dict]:
    return [
        {"page": issue.page, "field": issue.field, "description": issue.description}
        for issue in result.issues
    ]


@router.post("/convert")
async def convert(pdf: UploadFile = File(...)):
    """Parse + validate a HAP report. Returns every row, or the blocking issues."""
    config = hapext_config()
    with workspace() as scratch:
        pdf_path = save_upload(pdf, scratch, suffixes=(".pdf",))
        out_dir = scratch / "out"
        out_dir.mkdir()

        result = pipeline.convert(str(pdf_path), str(out_dir), config)
        if not result.ok:
            # all-or-nothing: nothing was written, report page + field
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "issues": _issues(result),
                    "stats": result.stats,
                    "source": pdf_path.name,
                },
            )

        with open(result.output_path, encoding=config.csv_encoding, newline="") as handle:
            rows = list(csv.reader(handle))

    return {
        "ok": True,
        "issues": [],
        "stats": result.stats,
        "source": pdf_path.name,
        "base_name": Path(pdf.filename or "schedule").stem,
        "header": rows[0] if rows else [],
        "rows": rows[1:],
    }


def _details_from(payload: str, logo_path: Path | None) -> dict:
    try:
        details = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad project details: {exc}") from exc
    details = {str(k): str(v) for k, v in details.items()}
    details[LOGO_KEY] = str(logo_path) if logo_path else ""
    missing = [label.rstrip(":") for key, label in PROJECT_FIELDS if not details.get(key, "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail="Missing: " + ", ".join(missing))
    return details


@router.post("/download")
async def download(
    payload: str = Form(...),
    details: str = Form(...),
    fmt: str = Form("xlsx"),
    logo: UploadFile | None = File(None),
):
    """Rebuild the schedule file from the rows the browser is holding.

    `payload` is {header, rows, base_name}; `details` is the mandatory project
    block. The logo rides along as a real file because `write_fcu_xlsx`
    embeds it into the merged G1:N1 header cell.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad payload: {exc}") from exc

    header = [str(c) for c in data.get("header", [])]
    rows = [[str(c) for c in row] for row in data.get("rows", [])]
    if not header or not rows:
        raise HTTPException(status_code=400, detail="Nothing to download.")
    base_name = str(data.get("base_name") or "schedule")

    config = hapext_config()
    scratch = Path(tempfile.mkdtemp(prefix="maec_dl_"))
    try:
        logo_path = None
        if logo is not None and logo.filename:
            logo_path = save_upload(logo, scratch, suffixes=LOGO_SUFFIXES)
        detail_map = _details_from(details, logo_path)

        if fmt == "csv":
            target = exporter.versioned_path(scratch, base_name, suffix=".csv")
            with open(target, "w", encoding=config.csv_encoding, newline="") as handle:
                csv.writer(handle).writerows(
                    build_project_header(detail_map) + [header] + rows
                )
            media = "text/csv"
        else:
            target = exporter.versioned_path(scratch, base_name, suffix=".xlsx")
            write_fcu_xlsx(detail_map, header, rows, target)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    # FileResponse streams *after* this handler returns, so the scratch
    # directory is cleaned by a background task, not a finally block.
    return FileResponse(
        target,
        media_type=media,
        filename=target.name,
        background=BackgroundTask(shutil.rmtree, scratch, ignore_errors=True),
    )


@router.post("/change-request")
async def change_request_route(
    xlsx: UploadFile = File(...),
    pdf: UploadFile = File(...),
):
    """Append a revised PDF's new units to a schedule this app produced.

    The generated workbook is a *copy* of the uploaded one — it keeps the
    original header block, embedded logo and merged cells — so it cannot be
    rebuilt from rows. It comes back base64-encoded and the browser saves it
    on Approve & Download, which keeps the whole flow stateless.
    """
    config = hapext_config()
    with workspace() as scratch:
        xlsx_path = save_upload(xlsx, scratch, suffixes=(".xlsx",))
        pdf_path = save_upload(pdf, scratch, suffixes=(".pdf",))
        out_dir = scratch / "out"
        out_dir.mkdir()

        result = pipeline.convert_change_request(
            str(xlsx_path), str(pdf_path), str(out_dir), config
        )
        if not result.ok:
            return {
                "ok": False,
                "issues": _issues(result),
                "stats": result.stats,
                "source": pdf_path.name,
            }

        sheet = openpyxl.load_workbook(result.output_path, data_only=True).active
        columns = len(config.csv_columns)
        header = [
            "" if cell.value is None else str(cell.value)
            for cell in sheet[change_request.HEADER_ROW][:columns]
        ]
        rows = []
        for row in sheet.iter_rows(min_row=change_request.FIRST_DATA_ROW, max_col=columns):
            values = ["" if c.value is None else str(c.value) for c in row]
            if any(v.strip() for v in values):
                rows.append(values)

        content = base64.b64encode(Path(result.output_path).read_bytes()).decode("ascii")

    return {
        "ok": True,
        "issues": [],
        "stats": result.stats,
        "previous_name": xlsx_path.name,
        "filename": Path(result.output_path).name,
        "header": header,
        "rows": rows,
        "existing_rows": result.stats.get("existing_rows", 0),
        "file_b64": content,
    }


@router.post("/inspect")
async def inspect(pdf: UploadFile = File(...)):
    """Page count + size for the upload card, mirroring the desktop's Upload step."""
    with workspace() as scratch:
        path = save_upload(pdf, scratch, suffixes=(".pdf",))
        try:
            with pymupdf.open(path) as doc:
                pages = doc.page_count
        except Exception:
            raise HTTPException(
                status_code=400, detail="This file could not be opened as a PDF"
            ) from None
        return {"name": path.name, "pages": pages, "size": path.stat().st_size}


@router.post("/inspect-schedule")
async def inspect_schedule(xlsx: UploadFile = File(...)):
    """Validate a previously generated workbook for the Change Request card."""
    config = hapext_config()
    with workspace() as scratch:
        path = save_upload(xlsx, scratch, suffixes=(".xlsx",))
        try:
            schedule = change_request.load_schedule(path, config)
        except change_request.ScheduleFormatError as exc:
            return {"ok": False, "name": path.name, "message": str(exc)}
        return {
            "ok": True,
            "name": path.name,
            "rows": schedule.row_count,
            "columns": len(schedule.column_header),
        }

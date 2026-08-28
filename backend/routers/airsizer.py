"""AirSizer Pro over HTTP: config, load, size, export.

`/config` serialises the same `input_matrix.json` the desktop form is built
from, so the React form is driven by exactly one source of truth — add a
sixth diffuser to the config and both UIs grow it.

The export deliberately re-runs `size_space` on the server rather than
trusting numbers posted up from the browser: the exported workbook can only
ever contain values the engine produced.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from hap_converter.airsizer.engine import export, pipeline
from hap_converter.airsizer.engine.models import SizingInput, Space

from ..deps import CONFIG_DIR, airsizer_config, save_upload, workspace

router = APIRouter(prefix="/api/airsizer", tags=["airsizer"])

SCHEDULE_SUFFIXES = (".xlsx", ".csv")


def _space_from(payload: dict) -> Space:
    return Space(
        name=str(payload.get("name", "")),
        floor_area=str(payload.get("floor_area", "")),
        total_coil=str(payload.get("total_coil", "")),
        sens_coil=str(payload.get("sens_coil", "")),
        air_flow=str(payload.get("air_flow", "")),
        is_unit=bool(payload.get("is_unit", False)),
        row=int(payload.get("row", 0)),
    )


def _space_json(space: Space) -> dict:
    return {
        "name": space.name,
        "floor_area": space.floor_area,
        "total_coil": space.total_coil,
        "sens_coil": space.sens_coil,
        "air_flow": space.air_flow,
        "is_unit": space.is_unit,
        "row": space.row,
        "sizable": pipeline.sizable(space),
    }


def _result_json(result) -> dict:
    return {
        "ok": result.ok,
        "group": result.group,
        "message": result.message,
        "interpolated": result.interpolated,
        "status": result.status,
        "lsm": result.lsm,
        "length_m": result.length_m,
        "pieces": result.pieces,
        "size": result.size,
        "alt_sizes": result.alt_sizes,
        "outlets": result.outlets,
        "throw": result.throw,
        "throw_range": result.throw_range,
        "nc": result.nc,
        "velocity": result.velocity,
        "pt": result.pt,
        "table": result.table,
    }


@router.get("/config")
async def get_config():
    """The input matrix that drives the dynamic sizing form."""
    config = airsizer_config()
    return {
        "inputs": [
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "title": spec.title(),
                "kind": spec.kind,
                "options": list(spec.options),
            }
            for spec in config.inputs.values()
        ],
        "diffusers": [
            {
                "key": spec.key,
                "label": spec.label,
                "group": spec.group,
                "inputs": list(spec.inputs),
                # per-diffuser dropdown overrides (e.g. slot widths differ
                # between the slot and flow-bar catalogues)
                "options": {k: list(v) for k, v in spec.options.items()},
                "diagram": f"/api/airsizer/diagram/{spec.key}",
            }
            for spec in config.diffusers.values()
        ],
        "result_columns": [
            {"key": c.key, "label": c.label, "default": c.default, "locked": c.locked}
            for c in config.result_columns
        ],
        "input_columns": config.input_columns,
    }


@router.get("/diagram/{key}")
async def diagram(key: str):
    """The construction reference drawing shown beside the sizing form."""
    config = airsizer_config()
    if key not in config.diffusers:
        raise HTTPException(status_code=404, detail=f"Unknown diffuser: {key}")
    path = config.diagram_path(key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Diagram not found")
    return FileResponse(path, media_type="image/png")


@router.post("/load")
async def load(schedule: UploadFile = File(...)):
    """Read a HAPExt schedule into the subspace list the wizard renders."""
    config = airsizer_config()
    with workspace() as scratch:
        path = save_upload(schedule, scratch, suffixes=SCHEDULE_SUFFIXES)
        try:
            spaces = pipeline.load_spaces(path, config)
        except pipeline.SourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "source": path.name,
        "base_name": Path(schedule.filename or "schedule").stem,
        "spaces": [_space_json(s) for s in spaces],
    }


@router.post("/load-rows")
async def load_rows(payload: dict):
    """Carry a HAPExt run straight into AirSizer without a round trip to disk.

    The browser posts the header + rows it already holds from
    /api/hapext/convert; they are written to a temp CSV and read back through
    the very same `load_spaces` the file upload uses, so both paths agree.
    """
    header = [str(c) for c in payload.get("header", [])]
    rows = [[str(c) for c in row] for row in payload.get("rows", [])]
    if not header or not rows:
        raise HTTPException(status_code=400, detail="No schedule rows supplied.")

    import csv

    config = airsizer_config()
    with workspace() as scratch:
        path = scratch / "schedule.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        try:
            spaces = pipeline.load_spaces(path, config)
        except pipeline.SourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "source": str(payload.get("source") or "HAPExt schedule"),
        "base_name": str(payload.get("base_name") or "schedule"),
        "spaces": [_space_json(s) for s in spaces],
    }


@router.post("/size")
async def size(payload: dict):
    """Size one subspace. A selection that cannot be made is a 200, not a 500."""
    config = airsizer_config()
    space = _space_from(payload.get("space") or {})
    sizing_input = SizingInput(
        diffuser=str(payload.get("diffuser", "")),
        values={str(k): str(v) for k, v in (payload.get("values") or {}).items()},
    )
    return _result_json(pipeline.size_space(space, sizing_input, config))


@router.post("/export")
async def export_route(payload: str = Form(...)):
    """Build the sized schedule, honouring the column picker's selection."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad payload: {exc}") from exc

    config = airsizer_config()
    spaces = [_space_from(s) for s in data.get("spaces", [])]
    if not spaces:
        raise HTTPException(status_code=400, detail="No schedule rows to export.")

    inputs: dict[int, SizingInput] = {}
    for row, entry in (data.get("inputs") or {}).items():
        inputs[int(row)] = SizingInput(
            diffuser=str(entry.get("diffuser", "")),
            values={str(k): str(v) for k, v in (entry.get("values") or {}).items()},
        )

    # recompute rather than trust the browser: the file only ever carries
    # numbers this engine produced
    by_row = {s.row: s for s in spaces}
    results = {
        row: pipeline.size_space(by_row[row], sizing_input, config)
        for row, sizing_input in inputs.items()
        if row in by_row
    }

    visible = data.get("visible_columns")
    columns = export.visible_columns(config, visible if visible is not None else None)
    base_name = str(data.get("base_name") or "air_diffuser_sizing")

    scratch = Path(tempfile.mkdtemp(prefix="maec_air_"))
    try:
        target = export.write_xlsx(
            spaces, inputs, results, config, columns,
            scratch, f"{base_name} - sized", str(data.get("project_name") or ""),
        )
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    return FileResponse(
        target,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=target.name,
        background=BackgroundTask(shutil.rmtree, scratch, ignore_errors=True),
    )

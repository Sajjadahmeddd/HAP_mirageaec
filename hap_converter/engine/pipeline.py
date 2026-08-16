"""Orchestrates parse → validate → synthesize → export.

The engine's single public entry point:

    convert(pdf_path, output_dir, config, progress_cb) -> Result

Never raises for input problems — file errors and validation failures come
back as Result(ok=False, issues=[...]) so the UI has one code path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import change_request, exporter, parser, synthesizer, validator
from .config import Config
from .validator import Issue


@dataclass
class Result:
    ok: bool
    output_path: Path | None
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


_PREFLIGHT_DESCRIPTIONS = {
    "protected": "This PDF is password protected or restricted from data extraction.",
    "scanned": "The PDF appears to be scanned. Text cannot be extracted.",
}


@dataclass
class ChangeResult:
    """Outcome of a change request (append revised PDF to existing sheet)."""

    ok: bool
    output_path: Path | None
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def convert_change_request(
    xlsx_path: str,
    pdf_path: str,
    output_dir: str,
    config: Config,
    progress_cb: parser.ProgressCb | None = None,
    cancel_cb: parser.CancelCb | None = None,
) -> ChangeResult:
    """Append a revised PDF's new line items to an existing schedule.

    No project details are collected: the existing header block and its
    embedded logo are preserved untouched. Existing rows are never edited.
    """
    started = time.perf_counter()
    stats: dict = {}

    def fail(field_name: str, description: str) -> ChangeResult:
        stats["elapsed_s"] = round(time.perf_counter() - started, 2)
        return ChangeResult(
            ok=False,
            output_path=None,
            issues=[Issue(page=0, field=field_name, description=description)],
            stats=stats,
        )

    # -- step 1: load + validate the previously generated workbook
    if progress_cb:
        progress_cb(1, 4, "Loading previous Excel")
    try:
        schedule = change_request.load_schedule(xlsx_path, config)
    except change_request.ScheduleFormatError as exc:
        return fail("excel_format", str(exc))
    except Exception as exc:
        return fail("excel_format", f"Could not read the Excel file: {exc}")
    stats["existing_rows"] = schedule.row_count
    stats["columns"] = len(schedule.column_header)

    # -- step 2: parse the revised PDF (same engine as a new project)
    if progress_cb:
        progress_cb(2, 4, "Extracting revised PDF")
    try:
        blocker = parser.preflight(pdf_path)
        if blocker:
            return fail(blocker, _PREFLIGHT_DESCRIPTIONS[blocker])
        units = list(parser.parse(pdf_path, config, None, cancel_cb))
    except Exception as exc:
        return fail("file", f"Cannot read PDF: {exc}")

    if cancel_cb and cancel_cb():
        return fail("cancelled", "Change request cancelled by user.")

    # -- the same all-or-nothing gate as a new project
    issues = validator.validate(units, config)
    if issues:
        stats["elapsed_s"] = round(time.perf_counter() - started, 2)
        return ChangeResult(ok=False, output_path=None, issues=issues, stats=stats)

    # -- step 3: compare line items
    if progress_cb:
        progress_cb(3, 4, "Comparing line items")
    new_rows = synthesizer.build_rows(units, config)[1:]  # drop the header row
    blocks, skipped = change_request.select_new_blocks(schedule, new_rows)
    appended_rows = sum(len(b) for b in blocks)
    stats.update(
        {
            "new_units": len(blocks),
            "new_rows": appended_rows,
            "skipped_units": len(skipped),
            "total_rows": schedule.row_count + appended_rows,
        }
    )

    if not blocks:
        return fail(
            "no_changes",
            "The revised PDF contains no new line items — every unit in it is "
            "already present in the Excel file. Nothing was appended.",
        )

    # -- step 4: append + highlight
    if progress_cb:
        progress_cb(4, 4, "Generating updated Excel")
    try:
        out_path = exporter.versioned_path(
            output_dir, Path(xlsx_path).stem, suffix=".xlsx"
        )
        change_request.append_blocks(schedule, blocks, out_path)
    except Exception as exc:
        return fail("error", f"Could not write the updated Excel: {exc}")

    stats["elapsed_s"] = round(time.perf_counter() - started, 2)
    return ChangeResult(ok=True, output_path=out_path, issues=[], stats=stats)


def convert(
    pdf_path: str,
    output_dir: str,
    config: Config,
    progress_cb: parser.ProgressCb | None = None,
    cancel_cb: parser.CancelCb | None = None,
) -> Result:
    started = time.perf_counter()

    try:
        blocker = parser.preflight(pdf_path)
        if blocker:
            return Result(
                ok=False,
                output_path=None,
                issues=[
                    Issue(page=0, field=blocker, description=_PREFLIGHT_DESCRIPTIONS[blocker])
                ],
                stats={"elapsed_s": round(time.perf_counter() - started, 2)},
            )
        units = list(parser.parse(pdf_path, config, progress_cb, cancel_cb))
    except Exception as exc:  # unreadable / corrupt / non-PDF input
        return Result(
            ok=False,
            output_path=None,
            issues=[Issue(page=0, field="file", description=f"Cannot read PDF: {exc}")],
            stats={"elapsed_s": round(time.perf_counter() - started, 2)},
        )

    if cancel_cb and cancel_cb():
        return Result(
            ok=False,
            output_path=None,
            issues=[Issue(page=0, field="cancelled", description="Conversion cancelled by user.")],
            stats={"elapsed_s": round(time.perf_counter() - started, 2)},
        )

    stats = {
        "units": len(units),
        "spaces": sum(len(u.spaces) for u in units),
    }

    issues = validator.validate(units, config)
    if issues:
        stats["elapsed_s"] = round(time.perf_counter() - started, 2)
        return Result(ok=False, output_path=None, issues=issues, stats=stats)

    if progress_cb:
        progress_cb(1, 1, "Writing CSV")
    try:
        rows = synthesizer.build_rows(units, config)
        out_path = exporter.write_csv(
            rows, output_dir, Path(pdf_path).stem, encoding=config.csv_encoding
        )
    except Exception as exc:  # e.g. output folder locked / not writable
        stats["elapsed_s"] = round(time.perf_counter() - started, 2)
        return Result(
            ok=False,
            output_path=None,
            issues=[Issue(page=0, field="error", description=f"Could not write the CSV: {exc}")],
            stats=stats,
        )

    stats["rows"] = len(rows) - 1  # excluding header
    stats["elapsed_s"] = round(time.perf_counter() - started, 2)
    return Result(ok=True, output_path=out_path, issues=[], stats=stats)

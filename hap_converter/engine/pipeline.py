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

from . import exporter, parser, synthesizer, validator
from .config import Config
from .validator import Issue


@dataclass
class Result:
    ok: bool
    output_path: Path | None
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def convert(
    pdf_path: str,
    output_dir: str,
    config: Config,
    progress_cb: parser.ProgressCb | None = None,
    cancel_cb: parser.CancelCb | None = None,
) -> Result:
    started = time.perf_counter()

    try:
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

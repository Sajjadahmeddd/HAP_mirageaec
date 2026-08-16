"""CSV writer with auto-versioning.

Values are written string-exact via the standard-library csv module. If the
target filename exists, _v1, _v2, … is appended — an existing file is never
overwritten.
"""

from __future__ import annotations

import csv
from pathlib import Path


def versioned_path(
    output_dir: str | Path, base_name: str, suffix: str = ".csv"
) -> Path:
    """First free `<base_name><suffix>`, adding _v1, _v2, … on collision."""
    output_dir = Path(output_dir)
    candidate = output_dir / f"{base_name}{suffix}"
    version = 0
    while candidate.exists():
        version += 1
        candidate = output_dir / f"{base_name}_v{version}{suffix}"
    return candidate


def write_csv(
    rows: list[list[str]],
    output_dir: str | Path,
    base_name: str,
    encoding: str = "utf-8-sig",
) -> Path:
    out_path = versioned_path(output_dir, base_name)
    with open(out_path, "w", encoding=encoding, newline="") as handle:
        csv.writer(handle).writerows(rows)
    return out_path

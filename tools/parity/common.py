"""Shared plumbing for the parity harness.

Repo-relative by construction: every path is derived from this file's location,
so the harness runs unchanged on Windows, inside the backend container, and in
CI. Nothing here is specific to one machine.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys

# tools/parity/common.py -> tools/parity -> tools -> repo root
REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINES = pathlib.Path(__file__).resolve().parent / "baselines.json"

# The engine packages are not importable until the repo root is on sys.path.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The container image carries backend/, hap_converter/ and config/ but NOT the
# sample drawings -- .dockerignore strips every PDF. So fixtures are looked up
# in the repo first and then at MAEC_PARITY_FIXTURES, which is where the
# container run mounts them. See README.md.
FIXTURE_ROOTS = [REPO]
if os.environ.get("MAEC_PARITY_FIXTURES"):
    FIXTURE_ROOTS.insert(0, pathlib.Path(os.environ["MAEC_PARITY_FIXTURES"]))

# The second element of a PDF's /ID array is required by the spec to change on
# every save, so two identical rebadges of one sheet differ in exactly these
# bytes. Masking it is what makes a byte comparison meaningful; the first
# element, which is permanent, is left alone deliberately.
_PDF_ID = re.compile(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]")


def fixture(relative: str) -> pathlib.Path:
    """Resolve a fixture path against the repo, then the mount point."""
    for root in FIXTURE_ROOTS:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    searched = "\n  ".join(str(r / relative) for r in FIXTURE_ROOTS)
    raise SystemExit(
        f"fixture not found: {relative}\nlooked in:\n  {searched}\n"
        "Inside the container, mount the sample drawings and set "
        "MAEC_PARITY_FIXTURES -- see tools/parity/README.md."
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mask_pdf_id(data: bytes) -> bytes:
    """A rebadged PDF with its per-save identifier neutralised."""
    return _PDF_ID.sub(b"/ID[<X><X>]", data)


def engine_versions() -> dict:
    """What produced a result. A baseline is only meaningful beside this."""
    import openpyxl
    import PIL
    import pymupdf
    return {
        "python": ".".join(str(v) for v in sys.version_info[:3]),
        "pymupdf": pymupdf.__version__,
        "openpyxl": openpyxl.__version__,
        "pillow": PIL.__version__,
    }


def load_baselines() -> dict:
    if not BASELINES.is_file():
        return {}
    return json.loads(BASELINES.read_text(encoding="utf-8"))


def save_baselines(data: dict) -> None:
    BASELINES.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} {detail}")
    return ok

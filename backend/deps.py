"""Shared helpers: config loading and temp-file plumbing.

Render's filesystem is ephemeral, so nothing is kept between requests. Every
upload is written to a temp file, handed to the engine as a path (the engines
take paths, and the port does not change that), and deleted in a `finally`.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, UploadFile

from hap_converter.airsizer.engine import config as air_config_mod
from hap_converter.engine import config as hapext_config_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

MAX_UPLOAD_BYTES = 200 * 1024 * 1024   # a 350-page HAP report runs ~2 MB


@lru_cache(maxsize=1)
def hapext_config():
    """config/mapping.json — the same file the desktop app loads."""
    return hapext_config_mod.load(CONFIG_DIR / "mapping.json")


@lru_cache(maxsize=1)
def airsizer_config():
    """config/input_matrix.json plus the five catalogs."""
    return air_config_mod.load(CONFIG_DIR / "input_matrix.json")


@contextmanager
def workspace() -> Iterator[Path]:
    """A scratch directory that is always removed, even on error."""
    directory = Path(tempfile.mkdtemp(prefix="maec_"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def save_upload(upload: UploadFile, directory: Path, *, suffixes: tuple[str, ...]) -> Path:
    """Write an upload into `directory`, rejecting the wrong file type."""
    name = Path(upload.filename or "upload").name
    if Path(name).suffix.lower() not in suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"{name}: expected {' or '.join(suffixes)}.",
        )
    target = directory / name
    size = 0
    with open(target, "wb") as handle:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"{name} is too large.")
            handle.write(chunk)
    if not size:
        raise HTTPException(status_code=400, detail=f"{name} is empty.")
    return target


# A filesystem name component is 255 bytes on every common filesystem; past
# that the write raises and the request becomes a 500. Well under it.
_MAX_BASE_NAME = 150


def safe_base_name(value: object, default: str) -> str:
    """A client-supplied output name, reduced to one safe path component.

    `base_name` arrives in the request body and becomes the name of the file
    the response is written to, so it must never carry a directory. Without
    this, "../x" or an absolute path wrote outside the scratch directory --
    Path's `/` REPLACES the left-hand side when the right is absolute.

    Backslashes are treated as separators too: on the Linux server they are
    ordinary characters, so a Windows-style path using them would otherwise
    survive as a single odd-looking name. Anything left with no letter or
    digit in it -- "", ".", "..", "---" -- falls back to the default rather
    than producing a hidden or empty filename.

    A legitimate name passes through unchanged: this only removes what a
    real schedule name never contains.
    """
    text = str(value or "").replace("\\", "/")
    name = Path(text).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    name = name[:_MAX_BASE_NAME]
    if not any(ch.isalnum() for ch in name):
        return default
    return name

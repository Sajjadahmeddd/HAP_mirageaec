"""Every download goes through the Save As dialog.

A standing rule, not a one-off: when someone downloads a workbook, a CSV, a
ZIP or a PDF, the browser's Save As dialog opens on their Downloads folder and
they choose where the file lands. `saveFile` in frontend/src/api.js does that.

A component that builds its own `<a download>` skips the dialog with no
visible sign in the code review or in the app — the file just lands in
Downloads again — so these tests read the frontend source and fail on one.
There is no JavaScript test runner in this project; this is the cheapest
place the rule can be enforced.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
HELPER = SRC / "api.js"

# The shapes a download takes when it goes around saveFile.
BYPASS = {
    "sets anchor.download": re.compile(r"\.download\s*="),
    "renders <a download>": re.compile(r"<a\b[^>]*\bdownload\b"),
    "calls a raw blob saver": re.compile(r"\b(?:saveBlob|downloadBlob|msSaveOrOpenBlob)\s*\("),
    "opens the file picker itself": re.compile(r"showSaveFilePicker"),
    # Navigating the page to a file endpoint downloads it with no dialog at
    # all. Not used here today, but it is how the maec-one-core admin screens
    # export CSVs, so it is the likeliest shape to be copied in.
    "navigates to an /api/ file": re.compile(
        r"""(?:location\.(?:assign|replace)\s*\(|location\.href\s*=|window\.open\s*\()\s*[`'"]/api/"""),
}


def sources():
    files = sorted([*SRC.rglob("*.js"), *SRC.rglob("*.jsx")])
    # An empty scan would pass every assertion below vacuously — the same way
    # a wrong path once silently skipped a whole test module in this codebase.
    assert HELPER.is_file(), f"api.js not found at {HELPER}"
    assert len(files) > 10, f"only {len(files)} frontend sources found under {SRC}"
    return files


@pytest.mark.parametrize("rule", sorted(BYPASS))
def test_no_component_downloads_around_the_save_as_dialog(rule):
    offenders = []
    for path in sources():
        if path == HELPER:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BYPASS[rule].search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")
    assert not offenders, (
        f"a download that {rule} skips the Save As dialog — use saveFile from api.js:\n"
        + "\n".join(offenders)
    )


def test_the_dialog_opens_on_the_downloads_folder():
    text = HELPER.read_text(encoding="utf-8")
    assert "export async function saveFile" in text
    assert "startIn: 'downloads'" in text


def test_the_plain_download_is_only_a_fallback_not_an_export():
    """If it were exported, the next module could call it and skip the dialog."""
    text = HELPER.read_text(encoding="utf-8")
    assert "function downloadBlob" in text
    assert "export function downloadBlob" not in text
    assert "export { downloadBlob" not in text


@pytest.mark.parametrize("module", [
    "api.js",                    # HAPExt workbook/CSV and AirSizer Pro export
    "hapext/ChangeReview.jsx",   # HAPExt change request
    "rebadge/Wizard.jsx",        # PDF Rebadging ZIP or PDF
])
def test_each_module_saves_through_the_dialog(module):
    assert "saveFile(" in (SRC / module).read_text(encoding="utf-8")

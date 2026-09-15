"""PDF Rebadging: the engine, against the real sample drawings.

The acceptance conditions that matter for a revision-controlled document are
all here: the old value leaves the file rather than being covered up — in all
seven places, the latest revision row included, which is replaced rather than
stacked on — older rows stay exactly as they were, and the drawing itself
comes through untouched.

Both coordinate frames are exercised. The samples are rotated-portrait; the
native-landscape variant is built in a fixture from one of them, because the
two print identically but share no raw coordinates and the label-anchored
geometry has to handle either.
"""

import glob
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageChops

from hap_converter.rebadger.engine import audit, editor, locator, pipeline, reader, verify
from hap_converter.rebadger.engine.locator import TitleBlockError, find_title_block
from hap_converter.rebadger.engine.models import RebadgeInputs

SAMPLES = sorted(glob.glob("HAP_ext/PDF_Rebadging/Sample inputs pdf/*.pdf"))
ARTIFACTS = Path(__file__).resolve().parent / "artifacts" / "rebadging"

INPUTS = RebadgeInputs(
    project_stage="Detailed Design",
    sheet_status="For Construction",
    rev="B",
    description="100% DETAILED DESIGN SUBMISSION",
    date="03 SEP 2026",
    approved_by="CK",
)

# what every sample carries before it is touched
EXISTING_ROW = ["A", "100% CONCEPT DESIGN SUBMISSION", "14 AUG 2026", "SK"]
# what the latest row reads after INPUTS is applied
NEW_ROW = ["B", "100% DETAILED DESIGN SUBMISSION", "03 SEP 2026", "CK"]


pytestmark = pytest.mark.skipif(not SAMPLES, reason="sample drawings not present")


@pytest.fixture(scope="module")
def landscape(tmp_path_factory):
    """The same sheet as a native-landscape page: rotation 0, fractional box.

    Rotating the media box and folding the rotation into the content stream is
    what a CAD tool does when it exports landscape natively — same printed
    sheet, completely different coordinates.
    """
    source = pymupdf.open(SAMPLES[0])
    width, height = source[0].mediabox.width, source[0].mediabox.height
    doc = pymupdf.open()
    doc.insert_pdf(source)
    source.close()

    page = doc[0]
    page.set_rotation(0)
    new_w, new_h = 2383.92, 1683.72          # deliberately not a round number
    doc.xref_set_key(page.xref, "MediaBox", f"[0 0 {new_w} {new_h}]")
    if doc.xref_get_key(page.xref, "CropBox")[0] != "null":
        doc.xref_set_key(page.xref, "CropBox", f"[0 0 {new_w} {new_h}]")

    xrefs = page.get_contents()
    body = b"".join(doc.xref_stream(x) for x in xrefs)
    scale_x, scale_y = new_w / height, new_h / width
    prefix = f"q {scale_x:.6f} 0 0 {scale_y:.6f} 0 0 cm 0 -1 1 0 0 {width:.0f} cm\n"
    doc.update_stream(xrefs[0], prefix.encode() + body + b"\nQ")
    for extra in xrefs[1:]:
        doc.update_stream(extra, b" ")

    target = tmp_path_factory.mktemp("rebadge") / "landscape.pdf"
    doc.save(target, garbage=1)
    doc.close()
    return target


@pytest.fixture(scope="module")
def rebadged():
    """Every sample rebadged once, reused across the assertions below."""
    out = {}
    for path in SAMPLES:
        name = Path(path).name
        payload, result = pipeline.rebadge(Path(path).read_bytes(), INPUTS, name)
        out[name] = (payload, result)
    return out


def _page(data: bytes):
    return pymupdf.open(stream=data, filetype="pdf")


def _crop(page, rect, zoom=1):
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect)
    return Image.open(io.BytesIO(pixmap.tobytes("png")))


# --------------------------------------------------------------- locating
@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: Path(p).stem[-12:])
def test_every_sample_validates(path):
    check = pipeline.check(Path(path).read_bytes(), Path(path).name)
    assert check.ok, check.errors
    assert check.missing_labels() == []
    assert check.current["stage"] == "CONCEPT DESIGN"
    assert check.current["rev"] == "A"
    assert len(check.current["history_rows"]) == 1


def test_the_landscape_variant_reads_the_same(landscape):
    """A different coordinate frame, the same printed sheet."""
    with pymupdf.open(landscape) as doc:
        assert doc[0].rotation == 0                    # not the samples' 90
        assert doc[0].rect.width != int(doc[0].rect.width)   # fractional box

    check = pipeline.check(landscape.read_bytes(), landscape.name)
    assert check.ok, check.errors
    assert check.rotation == 0
    assert check.current["stage"] == "CONCEPT DESIGN"


def test_a_file_that_is_not_a_pdf_is_reported_not_raised():
    check = pipeline.check(b"%PDF-1.4 and then nothing", "junk.pdf")
    assert not check.ok
    assert "not a readable PDF" in check.errors[0]


def test_a_pdf_without_our_title_block_is_reported(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text(pymupdf.Point(72, 72), "Somebody else's drawing")
    target = tmp_path / "other.pdf"
    doc.save(target)
    doc.close()

    check = pipeline.check(target.read_bytes(), "other.pdf")
    assert not check.ok
    assert check.missing_labels()


# ---------------------------------------------------------------- editing
@pytest.mark.parametrize("name", [Path(p).name for p in SAMPLES])
def test_the_old_value_leaves_the_file(rebadged, name):
    """Redaction, not cover-up: the old text must be gone, not hidden."""
    payload, result = rebadged[name]
    assert result.ok, result.errors

    with _page(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        for cell in (block.stage, block.status):
            zone = (cell.value_zone * block.derotation).normalize()
            assert "CONCEPT" not in page.get_text("text", clip=zone).upper()

        assert reader.read_cell(page, block.stage) == "DETAILED DESIGN"
        assert reader.read_cell(page, block.status) == "FOR CONSTRUCTION"
        # the whole page, not just the cell: no stray copy left behind
        assert "CONCEPT DESIGN\n" not in page.get_text("text").replace(
            "100% CONCEPT DESIGN SUBMISSION", "")


@pytest.mark.parametrize("name", [Path(p).name for p in SAMPLES])
def test_the_labels_and_rules_survive(rebadged, name):
    payload, _ = rebadged[name]
    with _page(payload) as doc:
        page = doc[0]
        for label in ("PROJECT STAGE", "SHEET STATUS", "REVISION",
                      "REV", "DESCRIPTION", "DATE", "APPROVED BY"):
            assert page.search_for(label), f"{label} was removed"
        find_title_block(page)          # the grid still parses


@pytest.mark.parametrize("name", [Path(p).name for p in SAMPLES])
def test_the_latest_history_row_is_overwritten_not_stacked_on(rebadged, name):
    """The revision table gains no row: the latest entry is replaced where it
    stands, and its old text leaves the file rather than sitting underneath."""
    payload, _ = rebadged[name]
    with _page(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        rows = reader.read_history(page, block)
        filled = [(i, r) for i, r in enumerate(rows) if r.filled()]

        assert len(filled) == 1, "a rebadge must not add a revision row"
        index, row = filled[0]
        assert index == len(rows) - 1, "the entry is replaced where it stands"
        assert [row.rev, row.description, row.date, row.approved_by] == NEW_ROW

        # redaction, not cover-up: exactly the new words are in the row, so
        # none of "A / 100% CONCEPT DESIGN SUBMISSION / 14 AUG 2026 / SK" remain
        zone = (block.history.rows[index] * block.derotation).normalize()
        found = sorted(w[4] for w in page.get_text("words", clip=zone))
        assert found == sorted(" ".join(NEW_ROW).split())


@pytest.mark.parametrize("name", [Path(p).name for p in SAMPLES])
def test_the_revision_cell_reads_the_new_rev_only(rebadged, name):
    payload, _ = rebadged[name]
    with _page(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        assert reader.read_cell(page, block.revision) == "B"


def test_the_landscape_variant_edits_identically(landscape):
    payload, result = pipeline.rebadge(landscape.read_bytes(), INPUTS, "landscape.pdf")
    assert result.ok, result.errors
    with _page(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        assert reader.read_cell(page, block.stage) == "DETAILED DESIGN"
        assert reader.read_cell(page, block.revision) == "B"
        rows = [r for r in reader.read_history(page, block) if r.filled()]
        assert [[r.rev, r.description, r.date, r.approved_by] for r in rows] == [NEW_ROW]


# ------------------------------------------------------- the drawing area
@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: Path(p).stem[-12:])
def test_the_drawing_is_not_moved(rebadged, path):
    """Nothing outside the edited cells may shift when the stream is rewritten.

    Comparing every span's position catches this exactly, where a pixel sample
    of one slab would miss anything that moved elsewhere on the sheet. One
    sample does disturb a single annotation; the engine reports it as a
    warning rather than letting it pass silently, which is what this asserts.
    """
    name = Path(path).name
    payload, result = rebadged[name]

    with _page(Path(path).read_bytes()) as before_doc, _page(payload) as after_doc:
        before, after = before_doc[0], after_doc[0]
        block = find_title_block(before)
        edited = [block.stage.rect, block.status.rect, block.revision.rect,
                  *block.history.rows]
        moved = verify.displaced(verify.span_index(before),
                                 verify.span_index(after), edited)

    reported = [w for w in result.warnings if w.startswith("drawing content:")]
    assert len(moved) == len(reported), (
        f"{name}: {len(moved)} span(s) moved but {len(reported)} were reported"
    )


def test_the_drawing_raster_is_untouched(rebadged):
    """A clean sheet renders pixel for pixel the same outside the title block."""
    path = next(p for p in SAMPLES if "B02" in p)
    payload, result = rebadged[Path(path).name]
    assert not [w for w in result.warnings if w.startswith("drawing content:")]

    region = pymupdf.Rect(200, 300, 1700, 1300)
    with _page(Path(path).read_bytes()) as before, _page(payload) as after:
        diff = ImageChops.difference(_crop(before[0], region).convert("RGB"),
                                     _crop(after[0], region).convert("RGB"))
    assert diff.getbbox() is None, "the drawing area changed"


def test_before_and_after_crops_are_written_for_review(rebadged):
    """The eyes-on artifact: the title block as it was and as it ends up."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = next(p for p in SAMPLES if "B02" in p)
    payload, _ = rebadged[Path(path).name]

    with _page(Path(path).read_bytes()) as before, _page(payload) as after:
        block = find_title_block(before[0])
        clip = pymupdf.Rect(block.history.header.x0 - 8, block.history.rows[0].y0 - 10,
                            block.stage.rect.x1 + 8, block.status.rect.y1 + 10)
        _crop(before[0], clip, zoom=3).save(ARTIFACTS / "title-block-before.png")
        _crop(after[0], clip, zoom=3).save(ARTIFACTS / "title-block-after.png")

    for name in ("title-block-before.png", "title-block-after.png"):
        assert (ARTIFACTS / name).stat().st_size > 1000


def test_the_source_file_is_never_written_to():
    path = Path(SAMPLES[0])
    original = path.read_bytes()
    pipeline.rebadge(original, INPUTS, path.name)
    assert path.read_bytes() == original


# ------------------------------------------------------------- the batch
def test_a_batch_produces_one_output_per_sheet_and_skips_what_it_cannot_do():
    files = [(Path(p).name, Path(p).read_bytes()) for p in SAMPLES]
    files.append(("broken.pdf", b"%PDF-1.4 not a drawing"))

    outputs, batch = pipeline.rebadge_batch(files, INPUTS)
    assert batch.ok_count == len(SAMPLES)
    assert batch.error_count == 1
    assert len(outputs) == len(SAMPLES)
    assert all(name.endswith("_rebadged.pdf") for name in outputs)

    skipped = next(s for s in batch.sheets if not s.ok)
    assert skipped.filename == "broken.pdf"
    assert skipped.errors


def test_a_name_collision_inside_a_batch_is_versioned():
    data = Path(SAMPLES[0]).read_bytes()
    outputs, batch = pipeline.rebadge_batch([("sheet.pdf", data), ("sheet.pdf", data)],
                                            INPUTS)
    assert sorted(outputs) == ["sheet_rebadged.pdf", "sheet_rebadged_v2.pdf"]
    assert batch.ok_count == 2


def test_the_zip_carries_every_sheet_and_the_audit():
    files = [(Path(p).name, Path(p).read_bytes()) for p in SAMPLES]
    outputs, batch = pipeline.rebadge_batch(files, INPUTS)
    name = audit.audit_name()
    blob = pipeline.build_zip(outputs, (name, audit.build_audit(INPUTS, batch)))

    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert len(names) == len(SAMPLES) + 1
    assert name in names
    assert name.startswith("Rebadging_Audit_") and name.endswith(".pdf")


def test_the_audit_names_what_was_applied_and_what_was_skipped():
    files = [(Path(SAMPLES[0]).name, Path(SAMPLES[0]).read_bytes()),
             ("broken.pdf", b"not a pdf at all")]
    _, batch = pipeline.rebadge_batch(files, INPUTS)
    text = pymupdf.open(stream=audit.build_audit(INPUTS, batch),
                        filetype="pdf")[0].get_text("text")

    assert "Detailed Design" in text and "For Construction" in text
    assert "100% DETAILED DESIGN SUBMISSION" in text
    assert "REBADGED" in text and "SKIPPED" in text
    assert "broken.pdf" in text
    assert "A" in text and "B" in text          # the revision it moved through


# ------------------------------------------------------------- the guards
def test_a_missing_input_stops_the_edit():
    incomplete = RebadgeInputs("Detailed Design", "", "B", "d", "date", "CK")
    assert incomplete.missing() == ["Sheet Status"]
    payload, result = pipeline.rebadge(Path(SAMPLES[0]).read_bytes(),
                                       incomplete, "sheet.pdf")
    assert payload is None
    assert not result.ok
    assert "Sheet Status" in result.errors[0]


def test_reusing_the_current_revision_warns_but_still_works():
    """Almost always a typo — say so, but it is the engineer's call."""
    same = RebadgeInputs("Detailed Design", "For Construction", "A",
                         "100% CONCEPT DESIGN SUBMISSION", "14 AUG 2026", "SK")
    payload, result = pipeline.rebadge(Path(SAMPLES[0]).read_bytes(), same, "sheet.pdf")
    assert result.ok and payload is not None
    assert any("already A" in w for w in result.warnings)


def _with_history(entries: list[RebadgeInputs]) -> bytes:
    """The first sample with its revision table set to `entries`, bottom row first."""
    doc = pymupdf.open(stream=Path(SAMPLES[0]).read_bytes(), filetype="pdf")
    page = doc[0]
    block = find_title_block(page)
    style = editor.TextStyle(7.7, False)
    bottom = len(block.history.rows) - 1
    for offset, entry in enumerate(entries):
        editor.overwrite_history_row(page, block, entry, bottom - offset, style)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def _history_of(payload: bytes) -> list[list[str]]:
    with _page(payload) as doc:
        page = doc[0]
        return [[r.rev, r.description, r.date, r.approved_by]
                for r in reader.read_history(page, find_title_block(page)) if r.filled()]


OLDER = replace(INPUTS, rev="A", description="100% CONCEPT DESIGN SUBMISSION",
                date="14 AUG 2026", approved_by="SK")
NEWER = replace(INPUTS, rev="B", description="100% DETAILED DESIGN SUBMISSION",
                date="03 SEP 2026", approved_by="CK")


def test_only_the_latest_row_is_replaced_and_older_revisions_stay():
    """B is the latest entry, A below it. Rebadging to C replaces B alone —
    A comes through word for word, which also proves the clearing zone did not
    reach into the row beneath."""
    data = _with_history([OLDER, NEWER])
    assert _history_of(data) == [NEW_ROW, EXISTING_ROW]

    later = replace(INPUTS, rev="C", description="ISSUED FOR TENDER",
                    date="20 SEP 2026", approved_by="MA")
    payload, result = pipeline.rebadge(data, later, "two-rows.pdf")
    assert result.ok, result.errors
    assert _history_of(payload) == [["C", "ISSUED FOR TENDER", "20 SEP 2026", "MA"],
                                    EXISTING_ROW]


def test_a_full_revision_table_is_rebadged_not_refused():
    """Overwriting needs no blank row, so a full table is no longer a reason
    to skip a sheet. The topmost row is the latest entry and is the one replaced."""
    with pymupdf.open(SAMPLES[0]) as doc:
        count = len(find_title_block(doc[0]).history.rows)
    entries = [replace(INPUTS, rev=f"R{i}", description=f"ENTRY {i}",
                       date="01 JAN 2026", approved_by="SK") for i in range(count)]
    data = _with_history(entries)

    check = pipeline.check(data, "full.pdf")
    assert check.ok, check.errors

    payload, result = pipeline.rebadge(data, INPUTS, "full.pdf")
    assert result.ok, result.errors
    assert [row[0] for row in _history_of(payload)] == [
        "B", *[f"R{i}" for i in range(count - 2, -1, -1)]]


def test_an_empty_revision_table_is_written_from_the_bottom_row():
    """With no entry to replace, the values go where the first one would."""
    data = _with_history([RebadgeInputs("", "", "", "", "", "")])   # clears row A
    assert _history_of(data) == []

    payload, result = pipeline.rebadge(data, INPUTS, "empty.pdf")
    assert result.ok, result.errors
    with _page(payload) as doc:
        page = doc[0]
        rows = reader.read_history(page, find_title_block(page))
    assert [i for i, r in enumerate(rows) if r.filled()] == [len(rows) - 1]
    assert _history_of(payload) == [NEW_ROW]


def test_a_description_containing_a_heading_word_is_still_cleared():
    """Headings are guarded by counting them outside the row, because a search
    is a substring match — an old "REVISED LAYOUT" contains REV, and taking it
    out is the point, not a lost heading."""
    revised = replace(OLDER, description="REVISED LAYOUT")
    payload, result = pipeline.rebadge(_with_history([revised]), INPUTS, "revised.pdf")
    assert result.ok, result.errors
    assert _history_of(payload) == [NEW_ROW]


def test_text_that_needs_shrinking_is_shrunk_and_reported():
    """It still fits, so the sheet is fine — the engineer is just told."""
    payload, result = pipeline.rebadge(Path(SAMPLES[0]).read_bytes(), INPUTS, "sheet.pdf")
    assert result.ok and payload is not None
    assert any("reduced from" in w for w in result.warnings)

    with _page(payload) as doc:
        page = doc[0]
        block = find_title_block(page)
        rows = [r for r in reader.read_history(page, block) if r.filled()]
        assert rows[0].date == "03 SEP 2026"      # shrunk, but complete and legible


def test_a_value_that_cannot_fit_its_cell_fails_the_sheet():
    """Overflowing text would run over the rules into the next cell. That is a
    defect the tool can see coming, so it refuses rather than prints it."""
    wordy = RebadgeInputs(
        project_stage="A Project Stage Name Far Longer Than This Cell Could Ever Allow "
                      "No Matter How Small The Type Is Made",
        sheet_status="For Construction", rev="B", description="d",
        date="03 SEP 2026", approved_by="CK")
    payload, result = pipeline.rebadge(Path(SAMPLES[0]).read_bytes(), wordy, "sheet.pdf")

    assert payload is None, "a sheet that cannot be edited correctly must not be emitted"
    assert not result.ok
    assert "Shorten the value" in result.errors[0]


# ----------------------------------------------- a consultant's real drawing set
# Sheets from the 00044-DHCGP package that the deployed service could not
# process. They live in the repository folder the user added them to; the
# tests skip when it is absent rather than failing on a checkout without it.
FAILURES = Path(__file__).resolve().parents[1] / "PDF_Rebadging failures"


def _failure(tag: str) -> Path:
    found = sorted(FAILURES.glob(f"*{tag}.pdf"))
    if not found:
        pytest.skip(f"{tag} from the 00044-DHCGP set is not present")
    return found[0]


def test_a_misspelled_approved_by_heading_keeps_its_own_column():
    """The set prints "APRROVED BY", and the only "APPROVED BY" on the sheet is
    a note near the top. Believing that note put APPROVED BY in the DATE
    column: the initials were printed over the date and the old approver was
    left in place, while validation reported the sheet as fine."""
    path = _failure("ELE-1110")
    with pymupdf.open(path) as doc:
        columns = find_title_block(doc[0]).history.columns
    assert columns["approved_by"] != columns["date"]
    assert columns["approved_by"][0] >= columns["date"][1] - 0.6

    payload, result = pipeline.rebadge(path.read_bytes(), INPUTS, path.name)
    assert result.ok, result.errors
    assert _history_of(payload) == [NEW_ROW]


def test_a_sheet_frame_drawn_as_one_quad_still_bounds_the_title_block():
    """ELE-1111 draws its outer frame as a single quad rather than four lines,
    and that frame is the right edge of PROJECT STAGE and SHEET STATUS and the
    bottom edge of REVISION. Reading only lines and rectangles, the sheet was
    refused: "no ruled line either side of the label"."""
    path = _failure("ELE-1111")
    check = pipeline.check(path.read_bytes(), path.name)
    assert check.ok, check.errors

    payload, result = pipeline.rebadge(path.read_bytes(), INPUTS, path.name)
    assert result.ok, result.errors
    assert _history_of(payload) == [NEW_ROW]
    with _page(payload) as doc:
        page = doc[0]
        assert reader.read_cell(page, find_title_block(page).revision) == "B"


def test_a_failure_while_reading_line_work_is_a_refusal_not_a_crash(monkeypatch):
    """PyMuPDF calls back into Python for every vector path, and an exception
    that escapes that callback does not come back as an exception — MuPDF
    takes the whole process down with it, which in production is the web
    service. Anything that goes wrong in there has to become a refused sheet.

    Without the guard this test does not fail; it kills the test run."""
    monkeypatch.setattr(locator, "_STRAIGHT", None)    # every comparison raises TypeError
    check = pipeline.check(Path(SAMPLES[0]).read_bytes(), "sheet.pdf")
    assert not check.ok
    assert "could not read the sheet's line work" in check.errors[0]


def test_the_drawing_outside_the_title_block_is_not_read():
    """ELE-1010 carries 692,017 vector items. Reading all of them peaked at
    2.6 GB and a single upload took down the 512 MB service. Paths whose
    bounding box misses the title-block region are never collected."""
    path = _failure("ELE-1110")
    with pymupdf.open(path) as doc:
        page = doc[0]
        region = locator._title_region(page, locator.find_label(page, locator.STAGE_LABEL))
        horizontals, verticals = locator._segments(page, region)
        everything_h, everything_v = locator._segments(page, page.rect)
    assert horizontals and verticals
    assert len(horizontals) + len(verticals) < len(everything_h) + len(everything_v)

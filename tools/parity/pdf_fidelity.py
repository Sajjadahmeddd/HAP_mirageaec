"""PDF fidelity: does a rebadged drawing still come out the same?

    python tools/parity/pdf_fidelity.py                # check against baseline
    python tools/parity/pdf_fidelity.py --update       # re-pin on current pins

Three comparisons, weakest to strongest:

  bytes     the whole file with the PDF /ID masked. A PyMuPDF patch may
            legitimately reorder objects or recompress streams, so a byte
            difference is a question, not a verdict.
  content   the page's content stream -- the drawing operators themselves.
  geometry  every word's position, via the engine's own verify.span_index().
            This is the one that decides: if no word moved, the drawing is
            visually and semantically unchanged whatever the bytes did.

That ordering is what lets a security patch through without waving through a
patch that actually moves ink.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from common import (engine_versions, fixture, load_baselines, mask_pdf_id,
                    report, save_baselines, sha)

SHEET = "PDF_Rebadging failures/00044-DHCGP-MRG-PL1-BD1-DWG-ELE-1101.pdf"

# Fixed inputs. Part of the baseline: different values produce a different
# drawing, so they are pinned here rather than passed in.
INPUTS = {
    "project_stage": "TENDER DOCUMENTATION",
    "sheet_status": "FOR INFORMATION",
    "rev": "0",
    "description": "ISSUED FOR TENDER",
    "date": "19 SEP 2026",
    "approved_by": "SAJJAD",
}


def produce() -> dict:
    import pymupdf
    from hap_converter.rebadger.engine import pipeline, verify
    from hap_converter.rebadger.engine.models import RebadgeInputs

    source = fixture(SHEET)
    outputs, batch = pipeline.rebadge_batch(
        [(source.name, source.read_bytes())], RebadgeInputs(**INPUTS))
    if not outputs:
        errors = "; ".join(e for s in batch.sheets for e in s.errors)
        raise SystemExit(f"the sheet did not rebadge at all: {errors}")
    data = next(iter(outputs.values()))

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[0]
        # span_index maps each word to its displayed origins. Sorted JSON so
        # the hash is stable across dict ordering.
        geometry = json.dumps(
            {k: [list(map(lambda v: round(v, 4), p)) for p in v]
             for k, v in sorted(verify.span_index(page).items())},
            sort_keys=True)
        content = bytes(page.read_contents())
        text = page.get_text("text")
    finally:
        doc.close()

    return {
        "fixture": SHEET,
        "inputs": INPUTS,
        "bytes": len(data),
        "sha256_id_masked": sha(mask_pdf_id(data)),
        "content_sha256": sha(content),
        "content_bytes": len(content),
        "geometry_sha256": sha(geometry.encode()),
        "words": len(json.loads(geometry)),
        "text_sha256": sha(text.encode()),
        "ok_count": batch.ok_count,
        "error_count": batch.error_count,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="re-pin the baseline on the CURRENT pins")
    args = ap.parse_args()

    print(f"engine: {engine_versions()}")
    result = produce()
    baselines = load_baselines()

    if args.update or "rebadge" not in baselines:
        why = "re-pinned" if args.update else "no baseline existed, pinned"
        baselines["rebadge"] = result | {"engine": engine_versions()}
        save_baselines(baselines)
        print(f"  {why}: geometry {result['geometry_sha256'][:16]}  "
              f"{result['words']} distinct words  {result['bytes']:,} B")
        return 0

    want = baselines["rebadge"]
    bytes_same = result["sha256_id_masked"] == want["sha256_id_masked"]
    content_same = result["content_sha256"] == want["content_sha256"]
    geometry_same = result["geometry_sha256"] == want["geometry_sha256"]
    text_same = result["text_sha256"] == want["text_sha256"]

    report("bytes identical (/ID masked)", bytes_same,
           "" if bytes_same else "-> not fatal on its own, see geometry")
    report("content stream identical", content_same,
           f"{result['content_bytes']:,} B")
    report("geometry identical", geometry_same,
           f"{result['words']} distinct words compared")
    report("page text identical", text_same)

    if bytes_same and content_same and geometry_same and text_same:
        print("\n  VERDICT: accept -- output is unchanged.")
        return 0
    if geometry_same and text_same:
        print("\n  VERDICT: accept WITH A NOTE -- bytes moved but no word did.")
        print("  Record in the commit message that the encoding changed and the")
        print("  drawing did not. Re-pin with --update as part of that commit.")
        return 0
    print("\n  VERDICT: REJECT -- a word moved. The drawing is not the same.")
    print(f"  baseline pinned on: {want.get('engine')}")
    print(f"  this run:           {engine_versions()}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

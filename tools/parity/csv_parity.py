"""CSV parity: does the HAP converter still produce the same bytes?

    python tools/parity/csv_parity.py                  # check against baseline
    python tools/parity/csv_parity.py --update         # re-pin on current pins

Deliberately calls the ENGINE, not the HTTP API. The web /download endpoint
prepends a project-details block that is operator input, so its hash depends
on what someone typed as much as on the engine -- a different project name
reads as a regression that isn't one. pipeline.convert() has no such input, so
this baseline moves only when the engine's behaviour moves.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
import tempfile

from common import (engine_versions, fixture, load_baselines, report,
                    save_baselines, sha)

REPORT = "tests/fixtures/System Design.pdf"


def produce() -> dict:
    from hap_converter.engine import config as config_mod
    from hap_converter.engine import pipeline

    cfg = config_mod.load(pathlib.Path(__file__).resolve().parents[2] / "config" / "mapping.json")
    out = pathlib.Path(tempfile.mkdtemp(prefix="maec_parity_"))
    pipeline.convert(str(fixture(REPORT)), str(out), cfg)
    written = next(out.glob("*.csv"))
    data = written.read_bytes()

    rows = list(csv.reader(data.decode(cfg.csv_encoding).splitlines()))
    # rows[0] is the column header; only data rows are counted. A unit row
    # carries a total-coil value, a space row does not.
    data_rows = rows[1:]
    units = sum(1 for r in data_rows if len(r) > 2 and r[2])
    return {
        "fixture": REPORT,
        "sha256": sha(data),
        "bytes": len(data),
        "rows": len(data_rows),
        "unit_rows": units,
        "space_rows": len(data_rows) - units,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="re-pin the baseline on the CURRENT pins")
    args = ap.parse_args()

    print(f"engine: {engine_versions()}")
    result = produce()
    baselines = load_baselines()

    if args.update or "csv" not in baselines:
        why = "re-pinned" if args.update else "no baseline existed, pinned"
        baselines["csv"] = result | {"engine": engine_versions()}
        save_baselines(baselines)
        print(f"  {why}: {result['sha256'][:16]}  {result['bytes']:,} B  "
              f"{result['rows']} rows")
        return 0

    want = baselines["csv"]
    ok = True
    ok &= report("CSV bytes identical", result["sha256"] == want["sha256"],
                 f"{result['sha256'][:16]} vs {want['sha256'][:16]}")
    ok &= report("size unchanged", result["bytes"] == want["bytes"],
                 f"{result['bytes']:,} B")
    ok &= report("row counts unchanged",
                 (result["rows"], result["unit_rows"]) == (want["rows"], want["unit_rows"]),
                 f"{result['rows']} rows, {result['unit_rows']} units, "
                 f"{result['space_rows']} spaces")
    if not ok:
        print(f"\n  baseline was pinned on: {want.get('engine')}")
        print(f"  this run:               {engine_versions()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

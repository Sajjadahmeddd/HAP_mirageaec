"""Speed guard: did an engine bump cost us wall-clock time?

    python tools/parity/timing.py run --iterations 7 --out old.json
    python tools/parity/timing.py once                    # one number, for interleaving
    python tools/parity/timing.py interleave --a "<cmd>" --b "<cmd>" -n 7
    python tools/parity/timing.py compare old.json new.json

Why interleave. This machine was measured swinging 2.4x between consecutive
runs of identical code, because Windows moves a background process between
performance and efficiency cores. Running all the old iterations and then all
the new ones measures whichever arm happened to get the good cores. Alternating
them spreads that noise evenly across both, which is what makes a +/-5%
threshold mean anything. The container is steadier (~4%) and is where these
numbers should be taken.

The workload is a single-sheet rebadge: CPU-bound, entirely inside PyMuPDF,
and the thing users actually wait for.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import time

from common import engine_versions, fixture

SHEET = "PDF_Rebadging failures/00044-DHCGP-MRG-PL1-BD1-DWG-ELE-1101.pdf"
THRESHOLD = 0.05          # 5% -- reject a bump that costs more than this


def one_iteration(payload: bytes, name: str) -> float:
    from hap_converter.rebadger.engine import pipeline
    from hap_converter.rebadger.engine.models import RebadgeInputs
    inputs = RebadgeInputs(project_stage="TENDER DOCUMENTATION",
                           sheet_status="FOR INFORMATION", rev="0",
                           description="ISSUED FOR TENDER", date="19 SEP 2026",
                           approved_by="SAJJAD")
    start = time.perf_counter()
    pipeline.rebadge_batch([(name, payload)], inputs)
    return time.perf_counter() - start


def measure(iterations: int) -> list[float]:
    source = fixture(SHEET)
    payload, name = source.read_bytes(), source.name
    one_iteration(payload, name)                     # warm: first call pays import costs
    return [one_iteration(payload, name) for _ in range(iterations)]


def summarise(times: list[float], label: str) -> dict:
    return {
        "label": label,
        "engine": engine_versions(),
        "iterations": len(times),
        "times": [round(t, 4) for t in times],
        "median": round(statistics.median(times), 4),
        "min": round(min(times), 4),
        "max": round(max(times), 4),
        "spread": round(max(times) / min(times), 3),
    }


def verdict(a: dict, b: dict) -> int:
    ratio = b["median"] / a["median"]
    worst_spread = max(a["spread"], b["spread"])
    print(f"  {a['label']:<10} median {a['median']:7.3f}s   spread {a['spread']:.2f}x   "
          f"{a['engine'].get('pymupdf')}")
    print(f"  {b['label']:<10} median {b['median']:7.3f}s   spread {b['spread']:.2f}x   "
          f"{b['engine'].get('pymupdf')}")
    print(f"\n  ratio B/A: {ratio:.3f}x   threshold: +/-{THRESHOLD:.0%}")
    if worst_spread > 1 + THRESHOLD * 2:
        print(f"  WARNING: within-arm spread is {worst_spread:.2f}x, wider than the")
        print("  threshold itself. This machine is too noisy -- re-run in the")
        print("  container, interleaved, with nothing else running.")
    if ratio > 1 + THRESHOLD:
        print(f"\n  VERDICT: REJECT -- {(ratio - 1):.1%} slower.")
        return 1
    if ratio < 1 - THRESHOLD:
        print(f"\n  VERDICT: accept -- {(1 - ratio):.1%} faster. Record it.")
        return 0
    print("\n  VERDICT: accept -- within noise.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="measure this environment")
    r.add_argument("--iterations", type=int, default=7)
    r.add_argument("--label", default="this")
    r.add_argument("--out", type=pathlib.Path)

    sub.add_parser("once", help="print a single iteration's seconds, for interleaving")

    i = sub.add_parser("interleave", help="alternate two commands that each print seconds")
    i.add_argument("--a", required=True, help="command for arm A, prints one float")
    i.add_argument("--b", required=True, help="command for arm B, prints one float")
    i.add_argument("-n", type=int, default=7)

    c = sub.add_parser("compare", help="compare two run outputs")
    c.add_argument("a", type=pathlib.Path)
    c.add_argument("b", type=pathlib.Path)

    args = ap.parse_args()

    if args.cmd == "once":
        source = fixture(SHEET)
        payload, name = source.read_bytes(), source.name
        one_iteration(payload, name)
        print(f"{one_iteration(payload, name):.6f}")
        return 0

    if args.cmd == "run":
        result = summarise(measure(args.iterations), args.label)
        print(json.dumps(result, indent=2))
        if args.out:
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0

    if args.cmd == "interleave":
        a_times, b_times = [], []
        for n in range(args.n):
            for cmd, bucket, tag in ((args.a, a_times, "A"), (args.b, bucket_b := b_times, "B")):
                out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if out.returncode != 0:
                    print(out.stderr[-500:])
                    raise SystemExit(f"arm {tag} failed")
                bucket.append(float(out.stdout.strip().splitlines()[-1]))
                print(f"  round {n + 1} arm {tag}: {bucket[-1]:.3f}s", flush=True)
        a = summarise(a_times, "A"); a["engine"] = {"pymupdf": "arm A"}
        b = summarise(b_times, "B"); b["engine"] = {"pymupdf": "arm B"}
        print()
        return verdict(a, b)

    return verdict(json.loads(args.a.read_text()), json.loads(args.b.read_text()))


if __name__ == "__main__":
    sys.exit(main())

# Parity harness — the output and speed guard

These drawings are signed and issued to clients. The test suite proves the
engine is **correct**; it does not prove the engine is **unchanged**. A PyMuPDF
patch can move a glyph half a point, or cost 20% on every batch, and pass all
295 tests.

This harness is what stands between a dependency bump and that outcome. Run it
before moving any pin on `pymupdf`, `openpyxl` or `pillow`.

## The three checks

| Script | Answers |
|---|---|
| `csv_parity.py` | Does the HAP converter still produce byte-identical CSV? |
| `pdf_fidelity.py` | Does a rebadged drawing still come out the same? |
| `timing.py` | Did it get slower? |

All three call the **engine directly**. No server, no auth, no ports — so they
run the same way on a laptop, in the container and in CI.

`csv_parity.py` deliberately does not use the web `/download` endpoint. That
endpoint prepends a project-details block which is operator input, so its hash
depends on what someone typed as much as on the engine. A different project
name would read as a regression that isn't one.

## Running it

```bash
python tools/parity/csv_parity.py        # exit 0 = unchanged
python tools/parity/pdf_fidelity.py
python tools/parity/timing.py run --iterations 7 --label before --out before.json
```

Add `--update` to re-pin a baseline. **Only ever re-pin on the version you are
moving away from, before the bump** — re-pinning afterwards measures the new
version against itself and passes everything.

### In the container, which is where the numbers should come from

This machine was measured swinging **2.4× between consecutive runs of
identical code**, because Windows moves a background process between
performance and efficiency cores. The container held within ~4%. A ±5%
threshold only means something on the steadier platform.

The image carries `backend/`, `hap_converter/` and `config/` but not `tools/`
and not the sample drawings — `.dockerignore` strips every PDF. So mount both:

```bash
docker compose run --rm \
  -v "$PWD/tools:/app/tools" \
  -v "$PWD/tests/fixtures:/fixtures/tests/fixtures" \
  -v "$PWD/PDF_Rebadging failures:/fixtures/PDF_Rebadging failures" \
  -e MAEC_PARITY_FIXTURES=/fixtures \
  backend python tools/parity/csv_parity.py
```

`MAEC_PARITY_FIXTURES` is searched before the repo, so the same scripts work
either way with no edits.

## Comparing two versions

A before/after comparison needs **two builds** — one on the old pin, one on the
new. Build both, keep them both running, and alternate:

```bash
# 1. current pins
docker compose build backend && docker tag maec-et-backend:latest maec-et-backend:before

# 2. bump the pin in backend/requirements.txt, then
docker compose build backend && docker tag maec-et-backend:latest maec-et-backend:after

# 3. fidelity: run the checks inside the AFTER image against the baseline
#    pinned on BEFORE (the baselines.json travels with the repo mount)

# 4. speed: alternate the two, never all-of-one-then-all-of-the-other
MOUNTS='-v '"$PWD"'/tools:/app/tools -v '"$PWD"'/PDF_Rebadging failures:/fixtures/PDF_Rebadging failures -e MAEC_PARITY_FIXTURES=/fixtures'
python tools/parity/timing.py interleave -n 7 \
  --a "docker run --rm $MOUNTS maec-et-backend:before python tools/parity/timing.py once" \
  --b "docker run --rm $MOUNTS maec-et-backend:after  python tools/parity/timing.py once"
```

Alternating matters. Run all the old iterations then all the new ones and you
measure whichever arm happened to get the good cores, plus any thermal drift
across the run.

## The decision

| Result | Action |
|---|---|
| Bytes identical, median within ±5% | **Accept.** Record both numbers. |
| **Bytes differ** | **Not an automatic reject.** A patch may reorder objects or recompress streams with no visual change. `pdf_fidelity.py` falls through to geometry — every word's position, via the engine's own `verify.span_index()`. No word moved → accept, and say in the commit message that the encoding changed and the drawing did not. Any word moved → **reject**. |
| Median regressed > 5% | **Reject.** Report the figures. |
| A check fails and the CVE is critical (RCE in the parser) | **Stop. Escalate to a human.** A remote-code-execution hole in the component that parses files arriving from outside the company outranks a 6% slowdown or a re-validation afternoon. Present both options with the evidence. |

A rejected bump goes to *fix later* **with its measured numbers**, so nobody
repeats the experiment in six months.

Packages outside the engine path — Starlette, itsdangerous, FastAPI — need only
the test suite.

## The baselines

`baselines.json` holds the pinned hashes and the exact inputs that produced
them, next to the engine versions in force at the time. Read it before
trusting a pass: **a guard with no baseline silently passes everything.** Both
scripts refuse to compare when no baseline exists, and pin one instead.

Current baselines were pinned on pymupdf 1.28.2 / openpyxl 3.1.5 / pillow
12.3.0 — the versions `pip freeze` reported on the live Render instance.

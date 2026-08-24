# MAEC — HAPExt + AirSizer Pro

Standalone Windows desktop suite. Two modules share one window, one build
and one engine discipline.

- **HAPExt** (module 1) converts one merged Carrier HAP
  "System Design" PDF (200-1000+ pages) into one structured FCU schedule
  (Excel/CSV), and appends revised PDFs to an existing schedule.
- **AirSizer Pro** (module 2) reads that schedule and sizes a TECNALCO
  diffuser per subspace from the manufacturer catalogs.

Offline, single user, no admin install. See
`HAP_Phase1_Implementation_Brief.md` for the module 1 spec.

## Run (development)

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m hap_converter.main
```

## Test

```powershell
.\.venv\Scripts\python -m pytest
```

Tests run against both **synthetic fixture PDFs** (built in `conftest.py`,
mirroring the real layout's edge cases) and the **real 212-page report**
(`tests/fixtures/System Design.pdf`, auto-skipped if absent). Extraction was
cross-checked against the DCG PLOT-01 FCU schedule Excel: every matching
unit's values agree except one, which the PDF itself confirms changed
between project revisions.

## Architecture

- `hap_converter/engine/` — UI-independent core. **Never imports from `ui/`.**
  Public API: `pipeline.convert(pdf_path, output_dir, config, progress_cb) -> Result`.
- `hap_converter/ui/` — PySide6 window + `QThread` worker.
- `config/mapping.json` — all anchors, offsets, mandatory fields, CSV columns.
  Editable without recompiling.

Guarantees honored:

- Every extracted value is carried as the **exact string** from the PDF —
  never floated, never rounded.
- All-or-nothing validation: any missing/unreadable mandatory value blocks
  the export entirely; the popup lists page + field for every issue.
- Streaming page-by-page parse; flat memory on 1000-page reports.
- Auto-versioning output: `name.csv`, `name_v1.csv`, `name_v2.csv`, …
- Derived fields: `W/m² = Total Coil Load ÷ Floor Area × 1000` (1 decimal),
  `Total kW = Total Coil Load × Qty` with Qty defaulting to 1 (Qty itself is
  a manual column, emitted blank).

## Tuning the parser (`config/mapping.json`, schema v2)

The parser is config-driven and was validated against the real HAP v5.2
"Zone Sizing Summary" report; nothing about the PDF layout is hard-coded:

- `page_signature` — text that identifies a unit page (others are skipped).
- `unit_fields.<field>` — two spec styles:
  - label-anchored (`anchor` + `offset`): value on the same line as the
    label or `offset` lines below. The unit **name** uses the page-title
    line (`Zone Sizing Summary for X`) because the "Air System Name" cell
    is empty on some pages of real reports.
  - section-row (`section` + `row_regex` + `offset`): value `offset` lines
    after the `Zone N` row inside the named section — HAP prints the sizing
    table as one positional row with fragmented header labels.
- `space_table` — space rows are detected by **indentation** (names may
  start with `#`, `@`, `@@`, or nothing; HAP width-truncates long names and
  the truncated text is carried as-is). `fields.<field>.offset` is the cell
  position after the name, counted after a split time-of-peak cell
  ("Jul" / "1500") is re-merged (`merge_time_of_peak`).

Encoding note: output is UTF-8 with BOM (`utf-8-sig`) so Excel renders
`m²` / `°C` correctly on double-click. Switch `csv_encoding` to `utf-8`
for a BOM-less file.


## AirSizer Pro (module 2)

Takes the schedule HAPExt produced and automates the catalog reading an
HVAC engineer does by hand: pick a diffuser type per subspace, enter its
inputs, and the engine narrows the right catalog table, reads (or
interpolates) the cell, and derives the outlet length.

### Architecture

- `hap_converter/airsizer/engine/` — UI-independent, same rule as module 1.
  - `config.py` loads `config/input_matrix.json` + `config/catalogs/*.json`
  - `lookup.py` resolves table -> row/column -> cell, with banding and
    linear interpolation
  - `calc.py` derived length, piece count, catalog length corrections
  - `pipeline.py` `load_spaces(path, config)` and
    `size_space(space, sizing_input, config) -> SizingResult`
  - `export.py` row assembly (shared by the review table and the writer)
    + the auto-versioned .xlsx
  - `project.py` one JSON per sizing session + a recent-projects index
- `hap_converter/airsizer/ui/` — home, the four-step wizard, the sizing
  panel, review/summary.

One generic engine, five catalog configs. Adding a sixth diffuser type is
two JSON entries and no code change.

### The two catalog shapes

- **Group A** (Linear Slot, Linear Bar Grille, Flow Bar) — rows are
  No. of Slots / nominal width, columns are L/s/m, each cell
  `[Pt (Pa), "min-mid-max throw", "NC"]`. Output: **L/s/m + throw**, then
  `Air Outlet Length (m) = Air Flow (L/s) / (L/s/m)` and the piece count.
- **Group B** (Square Ceiling Diffuser, Grilles & Registers) — rows are
  air flow (L/s), columns are list sizes, each cell
  `[velocity (m/s), "min-max throw", "NC"]`. Output: the **size in mm x mm**
  — the smallest listed size whose velocity and NC both stay within limits.

Guarantees:

- Tables are **banded**. Inputs outside a row's or column's published range
  return "no valid selection", never an extrapolation.
- A value read between two catalog entries is **interpolated linearly and
  flagged**; the panel shows an amber banner and the export tints the row.
- All arithmetic is `Decimal` on the exact catalog and schedule values.
- Export writes only the columns left visible in the column picker, and
  auto-versions (`name.xlsx`, `name_v1.xlsx`, ...).

### Tuning (`config/input_matrix.json`)

`diffuser_types[]` says which inputs a type takes, which catalog it reads
and which diagram it shows. `parameters` holds the rules the brief left
open (section 8), each with a `_TODO` note beside it:

| parameter | default | what it decides |
|---|---|---|
| `nc_rule` | `cap_lsm_by_nc` | Noise Criteria caps the L/s/m column |
| `throw_output` | `mid` | which terminal velocity is "the" Flow Throw |
| `apply_length_correction` / `length_correction_basis` | `true` / `total` | whether the catalog length correction is applied, and to which length |
| `flow_bar_slots_multiply_lsm` | `true` | parallel Flow Bar slots share the airflow |
| `nc_less_than_policy` | `as_value` | how a cell printed `<20` compares |

Catalog transcriptions live in `config/catalogs/`; each file records its
source pages and every place the printed catalog is internally
inconsistent, in its `notes`.

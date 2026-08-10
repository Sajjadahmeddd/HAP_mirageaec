# HAP PDF-to-CSV Converter (Phase 1)

Standalone Windows desktop tool that converts one merged Carrier HAP
"System Design" PDF (200–1000+ pages) into one structured CSV. Offline,
single user, no admin install. See `HAP_Phase1_Implementation_Brief.md`
for the full spec.

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

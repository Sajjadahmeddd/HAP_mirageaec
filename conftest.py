"""Shared fixtures: synthetic PDFs mirroring the real HAP v5.2
"Zone Sizing Summary" get_text() layout (verified against the 212-page
DCG BREEZE System Design.pdf):

- one unit per page; fragmented table-header lines; positional "Zone 1" rows
- "Air System Name" value on the next line (page-1 style) or on the same
  line (page-2 style) — both occur in the real report
- space rows detected by indentation; names may start with #, @, or nothing,
  and can be width-truncated by HAP
- time-of-peak normally one cell ("Jul 1500"); one fixture splits it to
  exercise the merge

The real report + reference Excel live in tests/fixtures/ (see
tests/test_real_report.py, skipped when absent).
"""

from pathlib import Path

import pymupdf
import pytest

from hap_converter.engine import config as config_mod

CONFIG_PATH = Path(__file__).parent / "config" / "mapping.json"

COVER_PAGE = [
    "Carrier HAP v5.2",
    "System Design Reports",
    "Project: Sample Tower",
    "Table of Contents",
]

_COOLING_HEADER = [
    "Terminal Unit Sizing Data - Cooling",
    " ",
    "Total",
    "Sens",
    "Coil",
    "Coil",
    "Water",
    "Time",
    "Coil",
    "Coil",
    "Entering",
    "Leaving",
    "Flow",
    "of",
    "Load",
    "Load",
    "DB / WB",
    "DB / WB",
    "@ 9.0 K",
    "Peak Coil",
    "Zone",
    "Zone Name",
    "(kW)",
    "(kW)",
    "(°C)",
    "(°C)",
    "(L/s)",
    "Load",
    "L/(s·m²)",
]

_HEATING_SECTION = [
    "Terminal Unit Sizing Data - Heating, Fan, Ventilation",
    "Zone Name",
    "(kW)",
    "Zone 1",
    "0.0",
    "-18.3 / -",
    "18.3",
    "0.00",
    "689",
    "0.087",
    "0.069",
    "0",
]

_SPACE_HEADER = [
    "Space Loads and Airflows",
    "Zone Name /",
    "     Space Name",
    "Mult.",
    "Cooling",
    "Sensible",
    "(kW)",
    "Time of",
    "Peak",
    "Sensible",
    "Load",
    "Air",
    "Flow",
    "(L/s)",
    "Heating",
    "Load",
    "(kW)",
    "Floor",
    "Area",
    "(m²)",
    "Space",
    "L/(s·m²)",
]

_FOOTER = ["Hourly Analysis Program v5.2", "Page    1  of  3"]


def _unit_page(
    title_name: str,
    name_lines: list[str],
    floor_area: str,
    cooling_row: list[str],
    space_rows: list[list[str]],
) -> list[str]:
    lines = [
        f"Zone Sizing Summary for {title_name}",
        "03. SAMPLE PROJECT",
        "Air System Information",
        *name_lines,
        "    Equipment Class ",
        " TERM",
        "    Air System Type ",
        " 2P-FC",
        "Number of zones ",
        " 1",
        "Floor Area ",
        f" {floor_area}",
        "m²",
        "Location ",
        " Dubai, United Arab Emirates",
        *_COOLING_HEADER,
        "Zone 1",
        *cooling_row,
        *_HEATING_SECTION,
        *_SPACE_HEADER,
        "Zone 1",
        " ",
        " ",
        " ",
    ]
    for row in space_rows:
        lines.extend(row)
    lines.extend(_FOOTER)
    return lines


# Page-1 style: ASN value on the line after the anchor; # prefix;
# multi-space; split time-of-peak in the second space row.
UNIT1_PAGE = _unit_page(
    title_name="#01-9FCorridor1(LIFT)",
    name_lines=["    Air System Name ", " #01-9FCorridor1(LIFT)"],
    floor_area="178.2",
    cooling_row=["9.2", "8.6", "23.5 / 16.7", "13.2 / 12.5", "0.24", "Jul 1600", "3.87"],
    space_rows=[
        ["     #01-9FCorridor1(LIFT)   ", "1", "8.7", "Jul 1500", "689", "0.2", "178.2", "3.87"],
        ["     @@L1-Office (West)  ", "1", "1.65", "Aug", "1600", "142", "0.0", "60.25", "2.36"],
    ],
)

# Real page-60 style: the "Air System Name" cell is EMPTY (happens on all
# @@-prefixed pages in the real report) — the name must come from the
# page-title line instead.
UNIT2_PAGE = _unit_page(
    title_name="@023-029-4-2F-5F-1B12-FCU1",
    name_lines=["    Air System Name ", " "],
    floor_area="59.5",
    cooling_row=["4.9", "4.2", "23.8 / 17.1", "13.7 / 12.7", "0.13", "Jun 1700", "5.79"],
    space_rows=[
        ["     @023-4-2F-5F-1B12-Bed   ", "1", "1.8", "Jun 1700", "139", "0.3", "15.3", "9.12"],
    ],
)

# No name prefix at all (real: "154-BD1-RF--PUMP RM").
UNIT3_PAGE = _unit_page(
    title_name="154-BD1-RF--PUMP RM",
    name_lines=["    Air System Name ", " 154-BD1-RF--PUMP RM"],
    floor_area="24.7",
    cooling_row=["2.3", "1.9", "23.7 / 17.1", "13.4 / 12.4", "0.06", "Jul 1700", "6.25"],
    space_rows=[
        ["     154-BD1-RF--PUMP RM     ", "1", "2.0", "Jul 1800", "154", "0.2", "24.7", "6.25"],
    ],
)

# Broken page: cooling row is missing its water-flow cell (the next section
# heading follows), and the space row is truncated before air flow.
BAD_UNIT_PAGE = [
    "Zone Sizing Summary for FCU-BAD-01",
    "Air System Information",
    "    Air System Name ",
    " FCU-BAD-01",
    "Number of zones ",
    " 1",
    "Floor Area ",
    " 50.00",
    "m²",
    *_COOLING_HEADER,
    "Zone 1",
    "2.0",
    "1.5",
    "26.0 / 19.0",
    "13.0 / 12.6",
    *_HEATING_SECTION,
    *_SPACE_HEADER,
    "Zone 1",
    " ",
    "     #BAD-Space",
    "1",
    "1.00",
    *_FOOTER,
]


def _write_pdf(path: Path, pages: list[list[str]]) -> Path:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()  # A4: fixture pages run ~110 lines, keep them on-page
        y = 30.0
        for line in lines:
            page.insert_text((40, y), line, fontsize=5.5)
            y += 7.0
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="session")
def config():
    return config_mod.load(CONFIG_PATH)


@pytest.fixture
def sample_pdf(tmp_path):
    """Cover page + three unit pages covering the real report's variants."""
    return _write_pdf(
        tmp_path / "sample_report.pdf", [COVER_PAGE, UNIT1_PAGE, UNIT2_PAGE, UNIT3_PAGE]
    )


@pytest.fixture
def bad_pdf(tmp_path):
    """One unit page with a missing water flow and a truncated space row."""
    return _write_pdf(tmp_path / "bad_report.pdf", [BAD_UNIT_PAGE])


# --------------------------------------------------------------- AirSizer Pro
AIR_CONFIG_PATH = Path(__file__).parent / "config" / "input_matrix.json"


@pytest.fixture(scope="session")
def air_config():
    """The AirSizer input matrix + all five transcribed catalogs."""
    from hap_converter.airsizer.engine import config as air_config_mod

    return air_config_mod.load(AIR_CONFIG_PATH)


@pytest.fixture
def space():
    """One subspace row from a HAPExt schedule (page 1 of the real report)."""
    from hap_converter.airsizer.engine.models import Space

    return Space(name="#01D-9F-Lift Lobby", floor_area="23.9", air_flow="218", row=8)

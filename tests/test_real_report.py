"""Integration tests against the real 212-page DCG BREEZE System Design.pdf.

Skipped automatically when the fixture PDF is absent (it is large and may
not travel with every checkout).
"""

from pathlib import Path

import pytest

from hap_converter.engine import parser, pipeline

REAL_PDF = Path(__file__).parent / "fixtures" / "System Design.pdf"

pytestmark = pytest.mark.skipif(
    not REAL_PDF.is_file(), reason="real report fixture not present"
)


@pytest.fixture(scope="module")
def real_units(config):
    return list(parser.parse(str(REAL_PDF), config))


def test_all_212_units_found(real_units):
    assert len(real_units) == 212
    assert sum(len(u.spaces) for u in real_units) == 601


def test_page1_values_match_pdf(real_units):
    unit = real_units[0]
    assert unit.name == "#01-9FCorridor1(LIFT)"
    assert unit.floor_area == "178.2"
    assert unit.total_coil == "9.2"
    assert unit.sens_coil == "8.6"
    assert unit.coil_entering == "23.5 / 16.7"
    assert unit.coil_leaving == "13.2 / 12.5"
    assert unit.water_flow == "0.24"
    assert len(unit.spaces) == 1
    assert unit.spaces[0].name == "#01-9FCorridor1(LIFT)"
    assert unit.spaces[0].air_flow == "689"
    assert unit.spaces[0].floor_area == "178.2"


def test_page2_same_line_name(real_units):
    assert real_units[1].name == "#01A-1F-8FCorridor1(LIFT)"
    # HAP truncates the space-name cell; the truncated text is carried as-is
    assert real_units[1].spaces[0].name == "#01A-1F-8FCor1(LIFT"


def test_last_page_no_prefix_name(real_units):
    unit = real_units[-1]
    assert unit.page == 212
    assert unit.name == "154-BD1-RF--PUMP RM"
    assert unit.spaces[0].air_flow == "154"


def test_multi_space_apartment_unit(real_units):
    unit = real_units[99]  # page 100: 7-space apartment FCU
    assert unit.name == "@023-029-4-2F-5F-1B12-FCU1"
    assert len(unit.spaces) == 7
    assert unit.spaces[0].name == "@023-4-2F-5F-1B12-Bed"
    assert unit.spaces[0].air_flow == "139"
    assert unit.spaces[-1].name == "@029-4-2F-5F-1B12-Pow"
    assert unit.spaces[-1].air_flow == "15"


def test_full_conversion_passes_gate_and_writes_csv(tmp_path, config):
    result = pipeline.convert(str(REAL_PDF), str(tmp_path), config)
    assert result.ok, result.issues[:10]
    assert result.stats["units"] == 212
    assert result.stats["spaces"] == 601
    assert result.stats["rows"] == 212 + 601
    content = result.output_path.read_bytes().decode("utf-8-sig")
    assert content.count("\r\n") == 1 + 212 + 601
    first_data_line = content.splitlines()[1]
    assert first_data_line == (
        "#01-9FCorridor1(LIFT),178.2,9.2,8.6,689,23.5 / 16.7,13.2 / 12.5,0.24,51.63,,9.2,,,"
    )

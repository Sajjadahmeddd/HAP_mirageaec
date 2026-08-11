from hap_converter.engine import pipeline

EXPECTED_CSV = (
    "Zone Name / Space Name,Floor Area (m²),Total Coil Load (KW),Sens Coil Load (KW),"
    "Air Flow (L/s),Coil Entering DB / WB (°C),Coil Leaving DB / WB (°C),"
    "Water Flow @9.0 K (L/s),W/m2,Qty,Total KW,ESP,FCU Types,Remarks\r\n"
    "#01-9FCorridor1(LIFT),178.2,9.2,8.6,,23.5 / 16.7,13.2 / 12.5,0.24,51.63,,9.2,,,\r\n"
    "#01-9FCorridor1(LIFT),178.2,,,689,,,,,,,,,\r\n"
    "@@L1-Office (West),60.25,,,142,,,,,,,,,\r\n"
    "@023-029-4-2F-5F-1B12-FCU1,59.5,4.9,4.2,,23.8 / 17.1,13.7 / 12.7,0.13,82.35,,4.9,,,\r\n"
    "@023-4-2F-5F-1B12-Bed,15.3,,,139,,,,,,,,,\r\n"
    "154-BD1-RF--PUMP RM,24.7,2.3,1.9,,23.7 / 17.1,13.4 / 12.4,0.06,93.12,,2.3,,,\r\n"
    "154-BD1-RF--PUMP RM,24.7,,,154,,,,,,,,,\r\n"
)


def test_end_to_end_byte_exact(sample_pdf, tmp_path, config):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = pipeline.convert(str(sample_pdf), str(out_dir), config)
    assert result.ok, result.issues
    assert result.output_path.name == "sample_report.csv"
    assert result.stats["units"] == 3
    assert result.stats["spaces"] == 4
    assert result.output_path.read_bytes() == b"\xef\xbb\xbf" + EXPECTED_CSV.encode("utf-8")


def test_validation_failure_blocks_export_entirely(bad_pdf, tmp_path, config):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = pipeline.convert(str(bad_pdf), str(out_dir), config)
    assert not result.ok
    assert result.output_path is None
    assert list(out_dir.iterdir()) == []  # nothing written
    fields = {issue.field for issue in result.issues}
    assert "Water Flow @9.0 K (L/s)" in fields
    assert "Air Flow (L/s)" in fields
    assert all(issue.page == 1 for issue in result.issues)


def test_unreadable_file_returns_issue_not_exception(tmp_path, config):
    fake = tmp_path / "not_a_pdf.pdf"
    fake.write_text("hello")
    result = pipeline.convert(str(fake), str(tmp_path), config)
    assert not result.ok
    assert result.issues[0].field == "file"


def test_cancel_stops_conversion_and_writes_nothing(sample_pdf, tmp_path, config):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    pages_seen = []
    result = pipeline.convert(
        str(sample_pdf),
        str(out_dir),
        config,
        progress_cb=lambda d, t, m: pages_seen.append(d),
        cancel_cb=lambda: len(pages_seen) >= 2,  # cancel after two pages
    )
    assert not result.ok
    assert result.output_path is None
    assert result.issues[0].field == "cancelled"
    assert list(out_dir.iterdir()) == []
    assert len(pages_seen) < 4  # stopped before the last pages


def test_unwritable_output_dir_returns_issue_not_exception(sample_pdf, tmp_path, config):
    missing_dir = tmp_path / "does" / "not" / "exist"
    result = pipeline.convert(str(sample_pdf), str(missing_dir), config)
    assert not result.ok
    assert result.issues[0].field == "error"
    assert "Could not write the CSV" in result.issues[0].description


def test_output_auto_versions_on_second_run(sample_pdf, tmp_path, config):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    first = pipeline.convert(str(sample_pdf), str(out_dir), config)
    second = pipeline.convert(str(sample_pdf), str(out_dir), config)
    assert first.output_path.name == "sample_report.csv"
    assert second.output_path.name == "sample_report_v1.csv"

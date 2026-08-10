from hap_converter.engine import exporter

ROWS = [["A", "B"], ["1,5", "x / y"]]


def test_writes_csv(tmp_path):
    path = exporter.write_csv(ROWS, tmp_path, "report")
    assert path.name == "report.csv"
    assert path.read_bytes() == b'\xef\xbb\xbfA,B\r\n"1,5",x / y\r\n'


def test_auto_versioning_never_overwrites(tmp_path):
    first = exporter.write_csv(ROWS, tmp_path, "report")
    second = exporter.write_csv(ROWS, tmp_path, "report")
    third = exporter.write_csv(ROWS, tmp_path, "report")
    assert first.name == "report.csv"
    assert second.name == "report_v1.csv"
    assert third.name == "report_v2.csv"
    assert first.read_text(encoding="utf-8-sig") == third.read_text(encoding="utf-8-sig")


def test_utf8_sig_bom_for_excel(tmp_path):
    path = exporter.write_csv([["Floor Area (m²)"]], tmp_path, "bom")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "m²" in raw.decode("utf-8-sig")

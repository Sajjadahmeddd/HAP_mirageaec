from hap_converter.engine import parser


def units_of(pdf, config):
    return list(parser.parse(str(pdf), config))


def test_parses_three_units_and_skips_cover(sample_pdf, config):
    units = units_of(sample_pdf, config)
    assert len(units) == 3
    assert [u.page for u in units] == [2, 3, 4]  # page 1 is the cover


def test_unit_fields_are_exact_strings(sample_pdf, config):
    unit = units_of(sample_pdf, config)[0]
    assert unit.name == "#01-9FCorridor1(LIFT)"
    assert unit.floor_area == "178.2"
    assert unit.total_coil == "9.2"
    assert unit.sens_coil == "8.6"
    assert unit.coil_entering == "23.5 / 16.7"  # combined cell kept as-is
    assert unit.coil_leaving == "13.2 / 12.5"
    assert unit.water_flow == "0.24"


def test_name_from_title_when_asn_cell_empty(sample_pdf, config):
    # real report: @@-prefixed pages have an empty "Air System Name" cell;
    # the name is sourced from the "Zone Sizing Summary for X" title line
    unit = units_of(sample_pdf, config)[1]
    assert unit.name == "@023-029-4-2F-5F-1B12-FCU1"


def test_name_without_prefix(sample_pdf, config):
    unit = units_of(sample_pdf, config)[2]
    assert unit.name == "154-BD1-RF--PUMP RM"
    assert unit.spaces[0].name == "154-BD1-RF--PUMP RM"


def test_spaces_multi_and_split_time_of_peak(sample_pdf, config):
    unit = units_of(sample_pdf, config)[0]
    assert [s.name for s in unit.spaces] == [
        "#01-9FCorridor1(LIFT)",
        "@@L1-Office (West)",
    ]
    assert unit.spaces[0].floor_area == "178.2"
    assert unit.spaces[0].air_flow == "689"
    # second row has "Aug" / "1600" split across two lines; offsets must
    # still land after the merge
    assert unit.spaces[1].floor_area == "60.25"
    assert unit.spaces[1].air_flow == "142"


def test_single_space_unit(sample_pdf, config):
    unit = units_of(sample_pdf, config)[1]
    assert len(unit.spaces) == 1
    assert unit.spaces[0].name == "@023-4-2F-5F-1B12-Bed"
    assert unit.spaces[0].floor_area == "15.3"
    assert unit.spaces[0].air_flow == "139"


def test_missing_value_yields_empty_string_not_next_heading(bad_pdf, config):
    unit = units_of(bad_pdf, config)[0]
    assert unit.water_flow == ""  # cooling row ends at the next section heading
    assert unit.spaces[0].name == "#BAD-Space"
    assert unit.spaces[0].air_flow == ""  # row truncated
    assert unit.spaces[0].floor_area == ""


def test_progress_callback_reports_every_page(sample_pdf, config):
    calls = []
    list(parser.parse(str(sample_pdf), config, lambda d, t, m: calls.append((d, t))))
    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]

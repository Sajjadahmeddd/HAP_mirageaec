from hap_converter.engine import synthesizer
from hap_converter.engine.models import Space, Unit


def make_unit():
    return Unit(
        name="#01-9FCorridor1(LIFT)",
        floor_area="178.2",
        total_coil="9.2",
        sens_coil="8.6",
        coil_entering="23.5 / 16.7",
        coil_leaving="13.2 / 12.5",
        water_flow="0.24",
        spaces=[
            Space(name="#01-9FCorridor1(LIFT)", floor_area="178.2", air_flow="689"),
            Space(name="@@L1-Office (West)", floor_area="60.25", air_flow="142"),
        ],
        page=2,
    )


def test_header_row_first(config):
    rows = synthesizer.build_rows([make_unit()], config)
    assert rows[0] == config.csv_columns
    assert rows[0][0] == "Zone Name / Space Name"


def test_unit_header_row(config):
    unit_row = synthesizer.build_rows([make_unit()], config)[1]
    # 9.2 / 178.2 * 1000 = 51.6273... -> 51.63 at 2 decimals
    assert unit_row == [
        "#01-9FCorridor1(LIFT)", "178.2", "9.2", "8.6", "", "23.5 / 16.7",
        "13.2 / 12.5", "0.24", "51.63", "", "9.2", "", "", "",
    ]


def test_total_kw_preserves_input_scale(config):
    # qty_default = 1: Total KW must reproduce the coil load string exactly
    unit_row = synthesizer.build_rows([make_unit()], config)[1]
    assert unit_row[10] == "9.2"


def test_space_rows(config):
    rows = synthesizer.build_rows([make_unit()], config)
    assert rows[2] == [
        "#01-9FCorridor1(LIFT)", "178.2", "", "", "689", "", "", "", "", "", "", "", "", "",
    ]
    assert rows[3][0] == "@@L1-Office (West)"
    assert rows[3][4] == "142"


def test_row_count(config):
    rows = synthesizer.build_rows([make_unit(), make_unit()], config)
    assert len(rows) == 1 + 2 * (1 + 2)  # header + 2 units x (1 header + 2 spaces)


def test_thousands_separator_in_source_string(config):
    unit = make_unit()
    unit.total_coil = "1,250.00"
    unit.floor_area = "2,500.00"
    rows = synthesizer.build_rows([unit], config)
    assert rows[1][2] == "1,250.00"  # extracted string is untouched
    assert rows[1][8] == "500.00"    # derived math strips separators

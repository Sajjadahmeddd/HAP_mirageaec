from hap_converter.engine import validator
from hap_converter.engine.models import Space, Unit


def make_unit(**overrides):
    unit = Unit(
        name="FCU-01",
        floor_area="100.00",
        total_coil="4.50",
        sens_coil="3.40",
        coil_entering="26.7 / 19.2",
        coil_leaving="12.8 / 12.5",
        water_flow="0.120",
        spaces=[Space(name="#Sp-1", floor_area="100.00", air_flow="150", page=1)],
        page=1,
    )
    for key, value in overrides.items():
        setattr(unit, key, value)
    return unit


def test_clean_unit_passes(config):
    assert validator.validate([make_unit()], config) == []


def test_empty_document_is_an_issue(config):
    issues = validator.validate([], config)
    assert len(issues) == 1
    assert issues[0].field == "document"


def test_missing_mandatory_unit_field(config):
    issues = validator.validate([make_unit(sens_coil="")], config)
    assert len(issues) == 1
    assert issues[0].page == 1
    assert issues[0].field == "Sens Coil Load (KW)"


def test_unreadable_numeric_field(config):
    issues = validator.validate([make_unit(total_coil="N/A")], config)
    assert len(issues) == 1
    assert "Unreadable" in issues[0].description


def test_zero_floor_area_blocks_derivation(config):
    issues = validator.validate([make_unit(floor_area="0")], config)
    assert len(issues) == 1
    assert "zero" in issues[0].description.lower()


def test_missing_space_air_flow(config):
    unit = make_unit()
    unit.spaces[0].air_flow = ""
    issues = validator.validate([unit], config)
    assert len(issues) == 1
    assert issues[0].field == "Air Flow (L/s)"
    assert "#Sp-1" in issues[0].description


def test_all_issues_are_collected_not_just_first(config):
    unit = make_unit(water_flow="", coil_entering="")
    unit.spaces[0].floor_area = ""
    issues = validator.validate([unit], config)
    assert len(issues) == 3

"""Catalogue accuracy: every expectation here was read off the TECNALCO
catalogue page by hand, then asserted against the engine.

Exact-cell reads must match the printed cell 100%. Interpolated reads are
computed between the two bracketing cells and must be flagged. Anything
outside a row's or column's published band must come back as "no valid
selection" rather than an extrapolation.
"""

from decimal import Decimal

import pytest

from hap_converter.airsizer.engine import lookup
from hap_converter.airsizer.engine.lookup import NoSelection


def read(air_config, diffuser, **values):
    catalog = air_config.catalog(diffuser)
    return lookup.read(air_config, catalog, values, Decimal("218"))


# ------------------------------------------------------- exact catalogue cells
def test_linear_slot_20mm_3_slots_nc15_reads_the_printed_cell(air_config):
    # p.19, slot width 20 mm, 3 slots (Ak 0.021): 50 L/s/m -> Pt 6, throw
    # 3.0-5.0-7.0, NC <15. NC 15 lands exactly on that column.
    reading = read(air_config, "linear_slot", nc="15", slot_width="20", no_of_slots="3")
    assert reading.interpolated is False
    assert reading.lsm == Decimal("50")
    assert reading.pt == Decimal("6")
    assert reading.throw == (Decimal("3.0"), Decimal("5.0"), Decimal("7.0"))
    assert str(reading.nc) == "<15"
    assert reading.ak == Decimal("0.021")


def test_linear_slot_16mm_1_slot_nc21_reads_the_printed_cell(air_config):
    # p.18, slot width 16 mm, 1 slot: 30 L/s/m -> Pt 20, throw 3.6-5.4-7.8, NC 21
    reading = read(air_config, "linear_slot", nc="21", slot_width="16", no_of_slots="1")
    assert reading.interpolated is False
    assert reading.lsm == Decimal("30")
    assert reading.pt == Decimal("20")
    assert reading.throw == (Decimal("3.6"), Decimal("5.4"), Decimal("7.8"))


def test_linear_bar_6mm_150_nc20_reads_the_printed_cell(air_config):
    # p.14, Bp 6 mm, nominal width 150 (Ak 0.063): 150 L/s/m -> Pt 7.0,
    # throw 4.0-4.7-6.8, NC 20
    reading = read(air_config, "linear_bar", nc="20", grille_height="150", bar_pitch="6",
                   velocity="2.5")
    assert reading.interpolated is False
    assert reading.lsm == Decimal("150")
    assert reading.pt == Decimal("7.0")
    assert reading.throw == (Decimal("4.0"), Decimal("4.7"), Decimal("6.8"))
    assert reading.ak == Decimal("0.063")


def test_linear_bar_12_5mm_100_nc33_reads_the_printed_cell(air_config):
    # p.15, Bp 12.5 mm, nominal width 100 (Ak 0.059): 300 L/s/m -> Pt 39.0,
    # throw 5.0-6.0-8.5, NC 33
    reading = read(air_config, "linear_bar", nc="33", grille_height="100", bar_pitch="12.5",
                   velocity="2.5")
    assert reading.interpolated is False
    assert reading.lsm == Decimal("300")
    assert reading.pt == Decimal("39.0")
    assert reading.throw == (Decimal("5.0"), Decimal("6.0"), Decimal("8.5"))


def test_flow_bar_76mm_nc45_reads_the_printed_cell(air_config):
    # Flowbar p.6, TFB-30-HT (76 mm slot): 302 l/s-m -> static 135 Pa,
    # throw 7.3-8.8-12.8, NC 45
    reading = read(air_config, "flow_bar", nc="45", slot_width="76", no_of_slots="1",
                   velocity="2.5")
    assert reading.interpolated is False
    assert reading.lsm == Decimal("302")
    assert reading.pt == Decimal("135")
    assert reading.throw == (Decimal("7.3"), Decimal("8.8"), Decimal("12.8"))


def test_square_300x300_at_180_reads_the_printed_cell(air_config):
    # Ceiling diffusers p.25 (square core, 4 way): 300 x 300 at 180 L/s ->
    # neck velocity 2.0 m/s, throw 4.9-6.1-8.2, NC 24
    catalog = air_config.catalog("square")
    reading = lookup.read_group_b(
        catalog, {"velocity": "2.5", "nc": "25"}, Decimal("180"), air_config.parameters
    )
    assert reading.interpolated is False
    assert reading.size == "300 x 300"
    assert reading.velocity == Decimal("2.0")
    assert reading.throw == (Decimal("4.9"), Decimal("6.1"), Decimal("8.2"))
    assert str(reading.nc) == "24"


def test_grille_picks_smallest_size_within_both_limits(air_config):
    # Grilles p.16: at 100 L/s every smaller column exceeds 2.5 m/s; the
    # 700 x 100 column reads 2.46 m/s / 3.2-4.7 m throw / NC 15.
    catalog = air_config.catalog("grille")
    reading = lookup.read_group_b(
        catalog,
        {"velocity": "2.5", "nc": "20", "deflection": "0"},
        Decimal("100"),
        air_config.parameters,
    )
    assert reading.interpolated is False
    assert reading.size == "700 x 100"
    assert reading.velocity == Decimal("2.46")
    assert reading.throw == (Decimal("3.2"), Decimal("4.7"))
    assert reading.alt_sizes == ("450 x 150", "250 x 250")


# ------------------------------------------------------------- interpolation
def test_noise_limit_between_columns_interpolates_and_flags(air_config):
    # p.19, 20 mm / 3 slots: NC 18 at 75 L/s/m and NC 26 at 100 L/s/m.
    # A limit of NC 20 sits a quarter of the way up: 75 + 0.25 * 25 = 81.25.
    reading = read(air_config, "linear_slot", nc="20", slot_width="20", no_of_slots="3")
    assert reading.interpolated is True
    assert reading.lsm == Decimal("81.25")
    # Pt interpolates the same way: 13 + 0.25 * (23 - 13) = 15.5
    assert reading.pt == Decimal("15.5")
    # throw likewise: 4.5 + 0.25 * (6.0 - 4.5) = 4.875
    assert reading.throw[0] == Decimal("4.875")
    assert reading.nc.value == Decimal("20")


def test_flow_between_published_rows_interpolates_group_b(air_config):
    # Ceiling diffusers, 300 x 300: 135 L/s -> 1.5 m/s, 180 L/s -> 2.0 m/s.
    # Halfway (157.5 L/s) must read 1.75 m/s and be flagged.
    catalog = air_config.catalog("square")
    reading = lookup.read_group_b(
        catalog, {"velocity": "2.5", "nc": "25"}, Decimal("157.5"), air_config.parameters
    )
    assert reading.interpolated is True
    assert reading.size == "300 x 300"
    assert reading.velocity == Decimal("1.75")


def test_exact_cell_is_not_flagged_as_interpolated(air_config):
    reading = read(air_config, "linear_slot", nc="15", slot_width="20", no_of_slots="3")
    assert reading.interpolated is False


# ------------------------------------------------------------------- banding
def test_noise_limit_below_the_quietest_cell_has_no_selection(air_config):
    # p.18, 16 mm / 2 slots: the quietest published column is NC 20.
    with pytest.raises(NoSelection, match="below the quietest"):
        read(air_config, "linear_slot", nc="15", slot_width="16", no_of_slots="2")


def test_row_absent_from_the_catalogue_has_no_selection(air_config):
    # The FlowBar catalogue publishes 25/38/51/63/76 mm slots, not 20 mm.
    with pytest.raises(NoSelection, match="no row for slot_width"):
        read(air_config, "flow_bar", nc="25", slot_width="20", no_of_slots="1", velocity="2.5")


def test_missing_table_for_a_configuration_has_no_selection(air_config):
    # Only 0 degree deflection tables are published for grilles.
    catalog = air_config.catalog("grille")
    with pytest.raises(NoSelection, match="no selection table"):
        lookup.read_group_b(
            catalog,
            {"velocity": "2.5", "nc": "25", "deflection": "15"},
            Decimal("100"),
            air_config.parameters,
        )


def test_flow_outside_every_column_band_has_no_selection(air_config):
    # The grille tables start at 25 L/s; 5 L/s is below every column.
    catalog = air_config.catalog("grille")
    with pytest.raises(NoSelection, match="outside the published"):
        lookup.read_group_b(
            catalog,
            {"velocity": "2.5", "nc": "25", "deflection": "0"},
            Decimal("5"),
            air_config.parameters,
        )


def test_limits_too_tight_for_any_size_has_no_selection(air_config):
    # 100 L/s is inside several bands, but no size gets under 1.0 m/s.
    catalog = air_config.catalog("grille")
    with pytest.raises(NoSelection, match="No list size serves"):
        lookup.read_group_b(
            catalog,
            {"velocity": "1.0", "nc": "25", "deflection": "0"},
            Decimal("100"),
            air_config.parameters,
        )


def test_never_extrapolates_past_the_largest_published_column(air_config):
    # 16 mm / 1 slot stops at 75 L/s/m (NC 46). A limit of NC 60 must read
    # that last column, not invent a bigger one.
    reading = read(air_config, "linear_slot", nc="60", slot_width="16", no_of_slots="1")
    assert reading.lsm == Decimal("75")
    assert reading.interpolated is False

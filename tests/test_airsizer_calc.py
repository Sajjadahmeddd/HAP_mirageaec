"""Derived maths: air-outlet length, piece count, length correction, and the
formatting the engineer actually reads.
"""

from decimal import Decimal

import pytest

from hap_converter.airsizer.engine import calc
from hap_converter.airsizer.engine.models import NoiseCriteria


def test_air_outlet_length_is_flow_over_lsm():
    # The review screen's worked example: 868 L/s at 40 L/s/m -> 21.7 m
    assert calc.air_outlet_length(Decimal("868"), Decimal("40")) == Decimal("21.7")
    assert calc.air_outlet_length(Decimal("218"), Decimal("40")) == Decimal("5.45")


def test_zero_lsm_cannot_derive_a_length():
    with pytest.raises(ValueError):
        calc.air_outlet_length(Decimal("218"), Decimal("0"))


def test_piece_count_always_rounds_up():
    one_metre = Decimal("1")
    assert calc.piece_count(Decimal("2.0"), one_metre) == 2
    assert calc.piece_count(Decimal("2.18"), one_metre) == 3
    assert calc.piece_count(Decimal("0.4"), one_metre) == 1     # never zero pieces
    # FlowBar ships 1200 mm sections
    assert calc.piece_count(Decimal("2.4"), Decimal("1.2")) == 2
    assert calc.piece_count(Decimal("2.5"), Decimal("1.2")) == 3


def test_fmt_rounds_half_up_then_drops_trailing_zeros():
    assert calc.fmt(Decimal("21.70"), 2) == "21.7"
    assert calc.fmt(Decimal("2.875"), 2) == "2.88"
    assert calc.fmt(Decimal("25.775"), 2) == "25.78"
    assert calc.fmt(Decimal("5.450"), 2) == "5.45"
    assert calc.fmt(Decimal("40"), 2) == "40"
    assert calc.fmt(None, 2) == ""


def test_fmt_nc_keeps_the_below_threshold_marker():
    assert calc.fmt_nc(NoiseCriteria(Decimal("23.8"))) == "24"
    assert calc.fmt_nc(NoiseCriteria(Decimal("15"), below=True)) == "<15"
    assert calc.fmt_nc(None) == ""


def test_length_correction_steps_throw_and_nc_by_band(air_config):
    # Linear bar grille p.10: 3-5 m -> throw x1.1, NC +4
    catalog = air_config.catalog("linear_bar")
    throw = (Decimal("2.2"), Decimal("4.0"), Decimal("5.3"))
    corrected, nc = calc.apply_length_correction(
        catalog, Decimal("2.18"), throw, NoiseCriteria(Decimal("15")), air_config.parameters
    )
    assert corrected == (Decimal("2.42"), Decimal("4.40"), Decimal("5.83"))
    assert nc.value == Decimal("19")


def test_one_metre_length_is_the_uncorrected_reference(air_config):
    catalog = air_config.catalog("linear_bar")
    throw = (Decimal("2.2"), Decimal("4.0"), Decimal("5.3"))
    corrected, nc = calc.apply_length_correction(
        catalog, Decimal("0.8"), throw, NoiseCriteria(Decimal("15")), air_config.parameters
    )
    assert corrected == throw
    assert nc.value == Decimal("15")


def test_length_past_the_last_band_keeps_the_last_band(air_config):
    # The catalogue stops at 6-10 m; a 14 m run keeps x1.15 / +8.
    catalog = air_config.catalog("linear_bar")
    corrected, nc = calc.apply_length_correction(
        catalog, Decimal("14"), (Decimal("4"),), NoiseCriteria(Decimal("20")), air_config.parameters
    )
    assert corrected == (Decimal("4.60"),)
    assert nc.value == Decimal("28")


def test_flow_bar_short_section_shrinks_the_throw(air_config):
    # Flowbar table B: a 600 mm section throws 0.72x the 1200 mm data.
    catalog = air_config.catalog("flow_bar")
    corrected, nc = calc.apply_length_correction(
        catalog, Decimal("0.6"), (Decimal("5.0"),), NoiseCriteria(Decimal("30")), air_config.parameters
    )
    assert corrected == (Decimal("3.600"),)
    assert nc.value == Decimal("27")     # table A supply correction: -3


def test_pick_throw_follows_the_configured_terminal_velocity(air_config):
    params = air_config.parameters
    three = (Decimal("3"), Decimal("5"), Decimal("7"))
    assert params.throw_output == "mid"
    assert calc.pick_throw(three, params) == Decimal("5")
    # a two-value grille cell has no printed middle: take the mean of the pair
    assert calc.pick_throw((Decimal("3"), Decimal("7")), params) == Decimal("5")
    assert calc.pick_throw((), params) is None

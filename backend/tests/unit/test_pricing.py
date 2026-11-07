import random
from datetime import date, timedelta

import pytest

from app.services.pricing import (
    GstRule,
    LineInput,
    gst_paise,
    gst_rate_bp,
    percent_discount_paise,
    price_line,
    price_night,
    price_stay,
    round_half_up_div,
)

RULE = GstRule(threshold_paise=750_000, low_rate_bp=500, high_rate_bp=1_800)
THU = date(2026, 11, 12)


def rupees(amount: int) -> int:
    return amount * 100


# ---------- rounding ----------


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(0, 7, 0), (5, 10, 1), (4, 10, 0), (15, 10, 2), (14, 10, 1), (25, 10, 3)],
)
def test_round_half_up_div(numerator: int, denominator: int, expected: int) -> None:
    assert round_half_up_div(numerator, denominator) == expected


def test_round_half_up_div_rejects_negative_input() -> None:
    with pytest.raises(ValueError):
        round_half_up_div(-1, 10)


@pytest.mark.parametrize(
    ("taxable", "rate_bp", "expected"),
    [
        (330, 500, 17),  # 16.5 paise rounds up
        (329, 500, 16),  # 16.45 paise rounds down
        (rupees(6_000), 500, rupees(300)),
        (rupees(8_000), 1_800, rupees(1_440)),
    ],
)
def test_gst_paise_rounds_half_up(taxable: int, rate_bp: int, expected: int) -> None:
    assert gst_paise(taxable, rate_bp) == expected


@pytest.mark.parametrize(
    ("amount", "percent", "expected"),
    [(250, 1, 3), (333, 10, 33), (335, 15, 50), (rupees(8_000), 10, rupees(800)), (999, 0, 0)],
)
def test_percent_discount_rounds_half_up(amount: int, percent: int, expected: int) -> None:
    assert percent_discount_paise(amount, percent) == expected


@pytest.mark.parametrize("percent", [-1, 101])
def test_percent_discount_rejects_out_of_range(percent: int) -> None:
    with pytest.raises(ValueError):
        percent_discount_paise(rupees(1_000), percent)


# ---------- GST slab ----------


@pytest.mark.parametrize(
    ("taxable", "expected_bp"),
    [
        (1, 500),
        (rupees(7_500), 500),  # exactly the threshold stays in the low slab
        (rupees(7_500) + 1, 1_800),  # one paisa above moves to the high slab
        (rupees(28_700), 1_800),
    ],
)
def test_gst_slab_boundary(taxable: int, expected_bp: int) -> None:
    assert gst_rate_bp(taxable, RULE) == expected_bp


def test_slab_comes_from_the_rule_not_constants() -> None:
    rule = GstRule(threshold_paise=rupees(1_000), low_rate_bp=0, high_rate_bp=1_200)
    assert gst_rate_bp(rupees(1_000), rule) == 0
    assert gst_rate_bp(rupees(1_001), rule) == 1_200


# ---------- one night ----------


def test_night_without_discount_above_threshold_is_18_percent() -> None:
    night = price_night(THU, rupees(8_000), 0, RULE)
    assert (night.taxable_paise, night.tax_rate_bp, night.tax_paise) == (
        rupees(8_000),
        1_800,
        rupees(1_440),
    )


def test_discount_can_move_a_night_into_the_lower_slab() -> None:
    # Rs 8,000 with 10% off is charged Rs 7,200, so GST is 5% of 7,200.
    night = price_night(THU, rupees(8_000), 10, RULE)
    assert night.discount_paise == rupees(800)
    assert night.taxable_paise == rupees(7_200)
    assert night.tax_rate_bp == 500
    assert night.tax_paise == rupees(360)


def test_night_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError):
        price_night(THU, 0, 0, RULE)


# ---------- lines and stays ----------


def test_one_stay_can_mix_gst_rates_by_night() -> None:
    # Deluxe Room: Rs 7,200 on Friday (5%), Rs 8,400 on a peak night (18%).
    line = LineInput({date(2026, 12, 18): rupees(7_200), date(2026, 12, 20): rupees(8_400)}, 1)
    priced = price_line(line, 0, RULE)
    assert [n.tax_rate_bp for n in priced.nights] == [500, 1_800]
    assert priced.tax_paise == rupees(360) + rupees(1_512)


def test_line_multiplies_per_unit_night_amounts_by_units() -> None:
    nights = {THU: rupees(6_000), THU + timedelta(days=1): rupees(7_200)}
    one = price_line(LineInput(nights, 1), 10, RULE)
    two = price_line(LineInput(nights, 2), 10, RULE)
    assert two.subtotal_paise == 2 * one.subtotal_paise
    assert two.discount_paise == 2 * one.discount_paise
    assert two.tax_paise == 2 * one.tax_paise


def test_slab_is_per_unit_not_per_line() -> None:
    # Two rooms at Rs 5,000 are 5% each, not 18% on a Rs 10,000 total.
    priced = price_line(LineInput({THU: rupees(5_000)}, 2), 0, RULE)
    assert priced.nights[0].tax_rate_bp == 500
    assert priced.tax_paise == rupees(500)


def test_nights_are_ordered_by_date() -> None:
    later, earlier = THU + timedelta(days=1), THU
    priced = price_line(LineInput({later: rupees(7_000), earlier: rupees(6_000)}, 1), 0, RULE)
    assert [n.stay_date for n in priced.nights] == [earlier, later]


def test_stay_sums_its_lines() -> None:
    a = LineInput({THU: rupees(6_000), THU + timedelta(days=1): rupees(7_200)}, 2)
    b = LineInput({THU: rupees(14_000), THU + timedelta(days=1): rupees(16_800)}, 1)
    stay = price_stay([a, b], 20, RULE)
    assert stay.subtotal_paise == sum(line.subtotal_paise for line in stay.lines)
    assert stay.discount_paise == sum(line.discount_paise for line in stay.lines)
    assert stay.tax_paise == sum(line.tax_paise for line in stay.lines)
    assert stay.total_paise == stay.subtotal_paise - stay.discount_paise + stay.tax_paise


@pytest.mark.parametrize("units", [0, -1])
def test_line_rejects_non_positive_units(units: int) -> None:
    with pytest.raises(ValueError):
        price_line(LineInput({THU: rupees(6_000)}, units), 0, RULE)


def test_line_and_stay_reject_empty_input() -> None:
    with pytest.raises(ValueError):
        price_line(LineInput({}, 1), 0, RULE)
    with pytest.raises(ValueError):
        price_stay([], 0, RULE)


def test_invariants_hold_for_many_random_stays() -> None:
    """Every total is an exact sum and every night uses the slab for its taxable value,
    the same rules the database CHECK constraints enforce."""
    rng = random.Random(7)
    for _ in range(500):
        lines = []
        for _ in range(rng.randint(1, 3)):
            nights = {
                THU + timedelta(days=i): rng.randint(100_000, 3_000_000)
                for i in range(rng.randint(1, 7))
            }
            lines.append(LineInput(nights, rng.randint(1, 4)))
        stay = price_stay(lines, rng.choice([0, 10, 15, 20, 100]), RULE)
        assert 0 <= stay.discount_paise <= stay.subtotal_paise
        assert stay.total_paise == stay.subtotal_paise - stay.discount_paise + stay.tax_paise
        for line in stay.lines:
            for night in line.nights:
                assert night.taxable_paise == night.rate_paise - night.discount_paise
                assert night.tax_rate_bp == gst_rate_bp(night.taxable_paise, RULE)

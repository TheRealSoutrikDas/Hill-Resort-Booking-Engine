"""Room-night pricing: promo discount, GST slab and totals.

Pure functions on integer paise, testable without a database or HTTP. Callers look up
the nightly rates and the promo; this module only does the arithmetic.

Rules (docs/ASSUMPTIONS.md A-08, docs/DECISIONS.md D-17):
- Everything is calculated per unit (room) per night, then multiplied by units.
  This keeps the GST slab test per room per night, and makes every total an exact sum.
- The promo discount is a percentage of that night's rate.
- The GST slab is chosen on the taxable value: the rate after discount.
  At or below the threshold the low rate applies; above it, the high rate.
- Rounding: half up to the nearest paise, once per unit-night, for the discount and
  for the tax. Integer arithmetic only, so there are no floating point errors.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.core.config import Settings

BASIS_POINTS = 10_000


@dataclass(frozen=True)
class GstRule:
    threshold_paise: int
    low_rate_bp: int
    high_rate_bp: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "GstRule":
        return cls(
            threshold_paise=settings.gst_slab_threshold_paise,
            low_rate_bp=settings.gst_rate_low_bp,
            high_rate_bp=settings.gst_rate_high_bp,
        )


def round_half_up_div(numerator: int, denominator: int) -> int:
    """numerator / denominator rounded half up, for non-negative integers."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("round_half_up_div expects numerator >= 0 and denominator > 0")
    return (2 * numerator + denominator) // (2 * denominator)


def percent_discount_paise(amount_paise: int, percent_off: int) -> int:
    if not 0 <= percent_off <= 100:
        raise ValueError("percent_off must be between 0 and 100")
    return round_half_up_div(amount_paise * percent_off, 100)


def gst_rate_bp(taxable_paise: int, rule: GstRule) -> int:
    return rule.low_rate_bp if taxable_paise <= rule.threshold_paise else rule.high_rate_bp


def gst_paise(taxable_paise: int, rate_bp: int) -> int:
    return round_half_up_div(taxable_paise * rate_bp, BASIS_POINTS)


@dataclass(frozen=True)
class NightPrice:
    """One night for one unit."""

    stay_date: date
    rate_paise: int
    discount_paise: int
    taxable_paise: int
    tax_rate_bp: int
    tax_paise: int


@dataclass(frozen=True)
class LinePrice:
    """One booking line: the per-unit nights, and totals for all its units."""

    units: int
    nights: tuple[NightPrice, ...]
    subtotal_paise: int
    discount_paise: int
    tax_paise: int

    @property
    def total_paise(self) -> int:
        return self.subtotal_paise - self.discount_paise + self.tax_paise


@dataclass(frozen=True)
class StayPrice:
    lines: tuple[LinePrice, ...]
    subtotal_paise: int
    discount_paise: int
    tax_paise: int

    @property
    def total_paise(self) -> int:
        return self.subtotal_paise - self.discount_paise + self.tax_paise


@dataclass(frozen=True)
class LineInput:
    """Nightly per-unit rates (one entry per night of the stay) and the number of units."""

    nightly_rates_paise: Mapping[date, int]
    units: int


def price_night(stay_date: date, rate_paise: int, percent_off: int, rule: GstRule) -> NightPrice:
    if rate_paise <= 0:
        raise ValueError("rate_paise must be positive")
    discount = percent_discount_paise(rate_paise, percent_off)
    taxable = rate_paise - discount
    rate_bp = gst_rate_bp(taxable, rule)
    return NightPrice(
        stay_date=stay_date,
        rate_paise=rate_paise,
        discount_paise=discount,
        taxable_paise=taxable,
        tax_rate_bp=rate_bp,
        tax_paise=gst_paise(taxable, rate_bp),
    )


def price_line(line: LineInput, percent_off: int, rule: GstRule) -> LinePrice:
    if line.units <= 0:
        raise ValueError("units must be positive")
    if not line.nightly_rates_paise:
        raise ValueError("a line needs at least one night")
    nights = tuple(
        price_night(day, rate, percent_off, rule)
        for day, rate in sorted(line.nightly_rates_paise.items())
    )
    return LinePrice(
        units=line.units,
        nights=nights,
        subtotal_paise=line.units * sum(n.rate_paise for n in nights),
        discount_paise=line.units * sum(n.discount_paise for n in nights),
        tax_paise=line.units * sum(n.tax_paise for n in nights),
    )


def price_stay(lines: Sequence[LineInput], percent_off: int, rule: GstRule) -> StayPrice:
    """Price every line of a stay. percent_off is 0 when there is no promo code."""
    if not lines:
        raise ValueError("a stay needs at least one line")
    priced = tuple(price_line(line, percent_off, rule) for line in lines)
    return StayPrice(
        lines=priced,
        subtotal_paise=sum(p.subtotal_paise for p in priced),
        discount_paise=sum(p.discount_paise for p in priced),
        tax_paise=sum(p.tax_paise for p in priced),
    )

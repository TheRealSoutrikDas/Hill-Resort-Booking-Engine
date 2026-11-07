"""Quotes: the room page's price with GST, from the same code path as holds (D-30)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Allotment, DailyRate, Hold
from app.services.errors import InvalidBookingRequest, InvalidPromoCode
from app.services.holds import create_hold
from app.services.quotes import quote_stay
from tests.factories import NOW, RULES, STAY, catalogue, line, promo, request


def test_quote_shows_each_nights_gst_rate(db: Session) -> None:
    c = catalogue(db)
    quote = quote_stay(
        db, request(line(c.dlx, c.ro), line(c.fst, c.ro, 1, 2)), now=NOW, rules=RULES
    )
    rates = [[n.tax_rate_bp for n in line_price.nights] for line_price in quote.price.lines]
    assert rates == [[500, 500], [1_800, 1_800]]  # Rs 6,000 at 5%, Rs 10,000 at 18%
    assert quote.nights == (STAY, STAY + timedelta(days=1)) and quote.promo is None


@pytest.mark.parametrize("code", [None, "WELCOME10"])
def test_quote_equals_the_price_then_held(db: Session, code: str | None) -> None:
    c = catalogue(db)
    promo(db, "WELCOME10", 10)
    req = request(line(c.dlx, c.bb, 2), line(c.fst, c.ro, 1, 3))
    quoted = quote_stay(db, req, now=NOW, rules=RULES, promo_code=code)
    held = create_hold(db, c.user.id, req, now=NOW, rules=RULES, promo_code=code)
    assert held.price == quoted.price


def test_quote_reserves_nothing_and_ignores_stock(db: Session) -> None:
    c = catalogue(db, dlx_web=0)  # nothing on sale, but a price can still be shown
    quote = quote_stay(db, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    assert quote.price.total_paise > 0
    assert db.scalar(select(func.count()).select_from(Hold)) == 0
    assert db.scalars(select(Allotment.sold)).all() == [0, 0, 0, 0]


def test_quote_applies_the_same_rules_as_a_hold(db: Session) -> None:
    c = catalogue(db)
    db.delete(db.get(DailyRate, (c.dlx.id, c.ro.id, STAY)))
    db.flush()
    with pytest.raises(InvalidBookingRequest) as err:
        quote_stay(db, request(line(c.dlx, c.ro)), now=NOW, rules=RULES)
    assert err.value.code == "rate_unavailable"
    with pytest.raises(InvalidPromoCode) as err:
        quote_stay(db, request(line(c.fst, c.ro)), now=NOW, rules=RULES, promo_code="NOPE")
    assert err.value.code == "promo_not_found"

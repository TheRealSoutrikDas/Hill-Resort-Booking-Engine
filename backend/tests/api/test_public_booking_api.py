"""Public booking routes: room search, room detail, quotes and lookup (12a; A-84 to A-89)."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Allotment, DailyRate, Hold, Payment, RatePlan, RoomType, User
from app.services.bookings import cancel_booking, confirm_booking
from app.services.holds import create_hold, set_guest_details
from app.services.quotes import HoldLineRequest, HoldRequest, quote_stay
from tests.factories import NIGHTS, NOW, RULES, STAY, catalogue, guest, promo

CHECK_IN, CHECK_OUT = STAY.isoformat(), (STAY + timedelta(days=2)).isoformat()
DATES = {"check_in": CHECK_IN, "check_out": CHECK_OUT}


@pytest.fixture
def client(make_client, committed: sessionmaker[Session]) -> TestClient:
    with committed() as s, s.begin():
        catalogue(
            s
        )  # DLX (Rs 6,000, 5% GST) and FST (Rs 10,000, 18%); plans RO, BB, OFF (inactive)
        promo(s, "WELCOME10", 10)
    return make_client(clock=lambda: NOW)


def stay(*lines: dict, promo_code: str | None = None) -> dict:
    return {**DATES, "lines": list(lines), "promo_code": promo_code}


def ln(room: str = "DLX", plan: str = "RO", units: int = 1, guests: int = 2) -> dict:
    return {"room_type": room, "rate_plan": plan, "units": units, "guests": guests}


# ---------- room search (screen 1, A-85) ----------


def test_search_without_dates_lists_room_types_only(client: TestClient) -> None:
    body = client.get("/api/rooms").json()
    assert [r["code"] for r in body["rooms"]] == ["DLX", "FST"]
    assert all(
        r["available_units"] is None and r["lowest_total_paise"] is None for r in body["rooms"]
    )


def test_search_with_dates_adds_availability_and_lowest_price(
    client: TestClient, committed
) -> None:
    rooms = {
        r["code"]: r
        for r in client.get("/api/rooms", params={**DATES, "guests": 2}).json()["rooms"]
    }
    assert (rooms["DLX"]["available_units"], rooms["FST"]["available_units"]) == (4, 3)
    # Room Only is the cheapest active plan: Rs 6,000 x 2 nights + 5% GST.
    assert rooms["DLX"]["lowest_total_paise"] == 2 * (600_000 + 30_000)
    assert rooms["DLX"]["fits_guests"] is True


def test_search_shows_sold_out_and_guest_fit(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        dlx = s.scalar(select(RoomType.id).where(RoomType.code == "DLX"))
        s.execute(
            update(Allotment)
            .where(Allotment.room_type_id == dlx)
            .values(sold=Allotment.total_for_web)
        )
    rooms = {
        r["code"]: r
        for r in client.get("/api/rooms", params={**DATES, "guests": 4}).json()["rooms"]
    }
    assert rooms["DLX"]["available_units"] == 0
    assert (rooms["DLX"]["fits_guests"], rooms["FST"]["fits_guests"]) == (
        False,
        True,
    )  # DLX takes 3


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"check_in": CHECK_IN}, "dates_incomplete"),
        ({"check_in": "2026-11-01", "check_out": "2026-11-03"}, "check_in_in_past"),
        ({"check_in": CHECK_OUT, "check_out": CHECK_IN}, "check_out_not_after_check_in"),
    ],
)
def test_search_rejects_bad_dates(client: TestClient, params: dict, code: str) -> None:
    response = client.get("/api/rooms", params=params)
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)


# ---------- room detail (screen 2) ----------


def test_room_detail_without_dates(client: TestClient) -> None:
    body = client.get("/api/rooms/dlx").json()
    assert body["room"]["code"] == "DLX"
    assert [p["code"] for p in body["rate_plans"]] == ["RO", "BB"]  # inactive OFF hidden (A-46)
    assert body["quotes"] is None


def test_room_detail_quotes_every_plan_with_gst_per_night(client: TestClient) -> None:
    body = client.get("/api/rooms/FST", params={**DATES, "guests": 3}).json()
    assert body["room"]["available_units"] == 3
    quotes = {q["rate_plan"]["code"]: q["price"] for q in body["quotes"]}
    nights = quotes["RO"]["lines"][0]["nights"]
    assert [(n["date"], n["rate_paise"], n["gst_rate_bp"]) for n in nights] == [
        (night.isoformat(), 1_000_000, 1_800) for night in NIGHTS
    ]
    assert quotes["BB"]["total_paise"] > quotes["RO"]["total_paise"]


def test_room_detail_unknown_code_is_404(client: TestClient) -> None:
    response = client.get("/api/rooms/PENTHOUSE")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "room_type_not_found")


def test_plan_without_rates_shows_why(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        bb = s.scalar(select(RatePlan.id).where(RatePlan.code == "BB"))
        for rate in s.scalars(select(DailyRate).where(DailyRate.rate_plan_id == bb)):
            s.delete(rate)
    quotes = {
        q["rate_plan"]["code"]: q
        for q in client.get("/api/rooms/DLX", params=DATES).json()["quotes"]
    }
    assert (
        quotes["BB"]["price"] is None and quotes["BB"]["unavailable_reason"] == "rate_unavailable"
    )


# ---------- quotes (screen 3, summary) ----------


def test_quote_prices_a_mixed_selection_with_a_promo(client: TestClient) -> None:
    body = client.post(
        "/api/quotes",
        json=stay(ln("DLX", "RO", 2, 4), ln("FST", "BB", 1, 3), promo_code=" welcome10 "),
    ).json()
    assert [(line["room_type"], line["rate_plan"], line["units"]) for line in body["lines"]] == [
        ("DLX", "RO", 2),
        ("FST", "BB", 1),
    ]
    assert body["promo"] == {"code": "WELCOME10", "percent_off": 10}
    assert (
        body["total_paise"] == body["subtotal_paise"] - body["discount_paise"] + body["gst_paise"]
    )


def test_quote_matches_the_service_and_the_room_page(client: TestClient, committed) -> None:
    api = client.post("/api/quotes", json=stay(ln("FST", "RO", 1, 2))).json()
    page = client.get("/api/rooms/FST", params={**DATES, "guests": 2}).json()
    page_ro = next(q["price"] for q in page["quotes"] if q["rate_plan"]["code"] == "RO")
    with committed() as s:
        fst = s.scalar(select(RoomType).where(RoomType.code == "FST"))
        ro_id = s.scalar(select(RatePlan.id).where(RatePlan.code == "RO"))
        service = quote_stay(
            s,
            HoldRequest(STAY, STAY + timedelta(days=2), [HoldLineRequest(fst.id, ro_id, 1, 2)]),
            now=NOW,
            rules=RULES,
        )
    assert api["total_paise"] == page_ro["total_paise"] == service.price.total_paise


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (stay(ln("PENTHOUSE")), "unknown_room_type"),
        (stay(ln("DLX", "XX")), "unknown_rate_plan"),
        (stay(ln("DLX", "OFF")), "rate_plan_inactive"),
        (stay(ln("DLX", "RO", 5, 5)), "too_many_units"),
        (stay(ln(), promo_code="FREESTAY"), "promo_not_found"),
    ],
)
def test_quote_errors(client: TestClient, body: dict, code: str) -> None:
    response = client.post("/api/quotes", json=body)
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)


def test_quote_rejects_unknown_fields(client: TestClient) -> None:
    assert client.post("/api/quotes", json={**stay(ln()), "price": 1}).status_code == 422


# ---------- lookup (screen 4, A-86) ----------


def make_booking(
    committed: sessionmaker[Session], guest_email: str = "parents@example.com"
) -> tuple[str, str]:
    """Returns (reference, account email) of a confirmed booking for someone else."""
    with committed() as s, s.begin():
        c_dlx = s.scalar(select(RoomType).where(RoomType.code == "DLX"))
        ro = s.scalar(select(RatePlan).where(RatePlan.code == "RO"))
        account = guest(s, "booker@example.com")
        result = create_hold(
            s,
            account.id,
            HoldRequest(STAY, STAY + timedelta(days=2), [HoldLineRequest(c_dlx.id, ro.id, 1, 2)]),
            now=NOW,
            rules=RULES,
        )
        set_guest_details(
            s,
            account.id,
            result.hold_id,
            name="Meera Rao",
            email=guest_email,
            phone="+91 00000 00042",
            now=NOW,
        )
        hold = s.get(Hold, result.hold_id)
        payment = Payment(
            hold_id=hold.id, idempotency_key=uuid.uuid4().hex, amount_paise=hold.total_paise
        )
        s.add(payment)
        s.flush()
        reference = confirm_booking(
            s, account.id, hold.id, payment.id, now=NOW, rules=RULES
        ).booking.reference
        return reference, account.email


def test_lookup_by_guest_email_or_account_email(client: TestClient, committed) -> None:
    reference, account_email = make_booking(committed)
    for email in ("Parents@Example.com", account_email):
        response = client.post(
            "/api/bookings/lookup", json={"reference": reference.lower(), "email": email}
        )
        assert response.status_code == 200, email
    body = response.json()
    assert (body["reference"], body["status"], body["nights"]) == (reference, "confirmed", 2)
    assert body["guest_email_masked"] == "p***@example.com"
    assert "phone" not in str(body) and "+91" not in str(body)
    assert body["lines"][0]["room_type_name"] == "DLX room"


def test_lookup_shows_cancellation(client: TestClient, committed) -> None:
    reference, account_email = make_booking(committed)
    with committed() as s, s.begin():
        user_id = s.scalar(select(User.id).where(User.email == account_email))
        cancel_booking(s, user_id, reference, now=NOW, rules=RULES)
    body = client.post(
        "/api/bookings/lookup", json={"reference": reference, "email": account_email}
    ).json()
    assert body["status"] == "cancelled" and body["cancelled_at"] is not None


def test_wrong_reference_or_email_look_the_same(client: TestClient, committed) -> None:
    reference, _ = make_booking(committed)
    attempts = [
        {"reference": reference, "email": "stranger@example.com"},
        {"reference": "BK-ZZZZZZZZ", "email": "parents@example.com"},
        {"reference": "nonsense", "email": "parents@example.com"},
    ]
    errors = [client.post("/api/bookings/lookup", json=a) for a in attempts]
    assert {r.status_code for r in errors} == {404}
    assert len({str(r.json()["error"]) for r in errors}) == 1


def test_lookup_is_rate_limited(client: TestClient) -> None:
    for _ in range(10):
        client.post(
            "/api/bookings/lookup", json={"reference": "BK-ZZZZZZZZ", "email": "x@example.com"}
        )
    refused = client.post(
        "/api/bookings/lookup", json={"reference": "BK-ZZZZZZZZ", "email": "x@example.com"}
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (429, "rate_limited")


def test_public_routes_have_readable_operation_ids(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/rooms"]["get"]["operationId"] == "search_rooms"
    assert paths["/api/rooms/{code}"]["get"]["operationId"] == "get_room"
    assert paths["/api/quotes"]["post"]["operationId"] == "quote"
    assert paths["/api/bookings/lookup"]["post"]["operationId"] == "lookup_booking"

"""Signed-in guest routes: the three-step flow, the confirmation page and cancelling (12b)."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Payment, User
from app.services import passwords
from app.services.payments.mock import MockPaymentProvider
from tests.factories import NOW, RULES, STAY, catalogue, promo

CHECK_IN, CHECK_OUT = STAY.isoformat(), (STAY + timedelta(days=2)).isoformat()
PASSWORD = "a long enough password"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(make_client, committed: sessionmaker[Session], clock: Clock) -> TestClient:
    with committed() as s, s.begin():
        catalogue(s, dlx_web=2)
        promo(s, "WELCOME10", 10)
    c = make_client(clock=clock)
    c.app.state.payment_provider = MockPaymentProvider()  # fresh gateway memory per test
    return c


def sign_up(client: TestClient, email: str = "asha@example.com") -> dict:
    """Sign up and return the headers a browser would send: the CSRF token."""
    body = {"full_name": "Asha Rao", "email": email, "password": PASSWORD, "consent": True}
    response = client.post("/api/auth/signup", json=body)
    assert response.status_code == 201
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def selection(units: int = 1, promo_code: str | None = None) -> dict:
    return {
        "check_in": CHECK_IN,
        "check_out": CHECK_OUT,
        "lines": [{"room_type": "DLX", "rate_plan": "RO", "units": units, "guests": units * 2}],
        "promo_code": promo_code,
    }


GUEST = {"name": "Meera Rao", "email": "meera@example.com", "phone": "+91 00000 00042"}


def pay(
    client: TestClient, csrf: dict, hold_id: str, simulate: str = "success", key: str | None = None
):
    headers = {**csrf, "Idempotency-Key": key or uuid.uuid4().hex}
    return client.post(
        f"/api/holds/{hold_id}/payment", json={"simulate": simulate}, headers=headers
    )


def held(client: TestClient, csrf: dict, **kwargs) -> dict:
    response = client.post("/api/holds", json=selection(**kwargs), headers=csrf)
    assert response.status_code == 201, response.json()
    return response.json()


def paid(client: TestClient, csrf: dict) -> str:
    hold = held(client, csrf)
    client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=csrf)
    return pay(client, csrf, hold["id"]).json()["booking_reference"]


# ---------- the whole journey ----------


def test_guest_journey_from_search_to_cancelled_lookup(client: TestClient) -> None:
    csrf = sign_up(client)
    rooms = client.get(
        "/api/rooms", params={"check_in": CHECK_IN, "check_out": CHECK_OUT, "guests": 2}
    ).json()
    assert next(r for r in rooms["rooms"] if r["code"] == "DLX")["available_units"] == 2
    quote = client.post("/api/quotes", json=selection(promo_code="WELCOME10")).json()

    hold = held(client, csrf, promo_code="WELCOME10")  # step 1
    assert (
        hold["status"] == "active" and hold["price"] == quote
    )  # the price shown is the price held
    assert (
        client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=csrf).json()["guest"]
        == GUEST
    )  # step 2
    payment = pay(client, csrf, hold["id"]).json()  # step 3
    assert payment["status"] == "confirmed"

    reference = payment["booking_reference"]
    booking = client.get(f"/api/bookings/{reference}").json()
    assert (booking["status"], booking["can_cancel"], booking["guest"]) == (
        "confirmed",
        True,
        GUEST,
    )
    assert booking["price"] == quote and booking["payment_reference"].startswith("MOCK-")
    assert client.get(f"/api/holds/{hold['id']}").json()["booking_reference"] == reference

    cancelled = client.post(f"/api/bookings/{reference}/cancel", headers=csrf).json()
    assert (cancelled["status"], cancelled["payment_status"], cancelled["can_cancel"]) == (
        "cancelled",
        "refunded",
        False,
    )
    looked_up = client.post(
        "/api/bookings/lookup", json={"reference": reference, "email": GUEST["email"]}
    ).json()
    assert looked_up["status"] == "cancelled"


# ---------- step 1: holds ----------


def dlx_available(client: TestClient) -> int:
    params = {"check_in": CHECK_IN, "check_out": CHECK_OUT}
    rooms = client.get("/api/rooms", params=params).json()["rooms"]
    return next(r for r in rooms if r["code"] == "DLX")["available_units"]


def test_hold_reduces_availability_and_release_gives_it_back(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf, units=2)
    assert dlx_available(client) == 0
    assert client.delete(f"/api/holds/{hold['id']}", headers=csrf).status_code == 204
    assert client.get(f"/api/holds/{hold['id']}").json()["status"] == "released"
    assert dlx_available(client) == 2


def test_sold_out_hold_is_409_with_shortfalls(client: TestClient) -> None:
    csrf = sign_up(client)
    held(client, csrf, units=2)
    response = client.post("/api/holds", json=selection(units=1), headers=csrf)
    assert response.status_code == 409
    shortfalls = response.json()["error"]["details"]["shortfalls"]
    assert [(s["date"], s["available"]) for s in shortfalls] == [
        (CHECK_IN, 0),
        ((STAY + timedelta(days=1)).isoformat(), 0),
    ]


def test_hold_with_unknown_promo_is_422(client: TestClient) -> None:
    csrf = sign_up(client)
    response = client.post("/api/holds", json=selection(promo_code="FREESTAY"), headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "promo_not_found")


def test_hold_shows_as_expired_after_ten_minutes(client: TestClient, clock: Clock) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    clock.now = NOW + timedelta(minutes=10)
    assert client.get(f"/api/holds/{hold['id']}").json()["status"] == "expired"


# ---------- step 2: guest details ----------


def test_invalid_guest_details_are_422(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    response = client.put(
        f"/api/holds/{hold['id']}/guest", json={**GUEST, "email": "nope"}, headers=csrf
    )
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_guest_email")


# ---------- step 3: payment ----------


def test_payment_needs_an_idempotency_key(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    response = client.post(f"/api/holds/{hold['id']}/payment", json={}, headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "validation_error")


def test_payment_before_guest_details_is_refused(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    response = pay(client, csrf, hold["id"])
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "guest_details_missing",
    )


def test_declined_payment_keeps_the_hold_and_a_retry_succeeds(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=csrf)
    declined = pay(client, csrf, hold["id"], simulate="decline")
    assert (declined.status_code, declined.json()["status"]) == (200, "declined")
    assert client.get(f"/api/holds/{hold['id']}").json()["status"] == "active"
    assert pay(client, csrf, hold["id"]).json()["status"] == "confirmed"


def test_double_click_returns_the_same_booking(client: TestClient, committed) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=csrf)
    key = uuid.uuid4().hex
    first, second = (
        pay(client, csrf, hold["id"], key=key).json(),
        pay(client, csrf, hold["id"], key=key).json(),
    )
    assert first == second and first["status"] == "confirmed"
    assert client.app.state.payment_provider.captured_count == 1
    with committed() as s:
        assert len(s.scalars(select(Payment)).all()) == 1


def test_payment_on_an_expired_hold_is_refused(client: TestClient, clock: Clock) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=csrf)
    clock.now = NOW + timedelta(minutes=11)
    response = pay(client, csrf, hold["id"])
    assert (response.status_code, response.json()["error"]["code"]) == (409, "hold_expired")


# ---------- confirmation page and cancelling ----------


def test_cancel_closes_the_day_before_check_in(client: TestClient, clock: Clock) -> None:
    csrf = sign_up(client)
    reference = paid(client, csrf)
    clock.now = datetime.combine(STAY, time(9), tzinfo=RULES.tz)
    assert client.get(f"/api/bookings/{reference}").json()["can_cancel"] is False
    response = client.post(f"/api/bookings/{reference}/cancel", headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "too_late_to_cancel")


def test_booking_page_shows_the_per_night_receipt(client: TestClient) -> None:
    csrf = sign_up(client)
    reference = paid(client, csrf)
    nights = client.get(f"/api/bookings/{reference}").json()["price"]["lines"][0]["nights"]
    assert [(n["date"], n["rate_paise"], n["gst_rate_bp"], n["gst_paise"]) for n in nights] == [
        (CHECK_IN, 600_000, 500, 30_000),
        ((STAY + timedelta(days=1)).isoformat(), 600_000, 500, 30_000),
    ]


# ---------- who may do what (A-43, A-77) ----------


def test_another_guests_hold_and_booking_are_not_found(client: TestClient) -> None:
    csrf = sign_up(client)
    hold = held(client, csrf)
    reference = paid(client, csrf)
    client.cookies.clear()
    other = sign_up(client, "ravi@example.com")
    assert client.get(f"/api/holds/{hold['id']}").status_code == 404
    assert (
        client.put(f"/api/holds/{hold['id']}/guest", json=GUEST, headers=other).status_code == 404
    )
    assert client.get(f"/api/bookings/{reference}").status_code == 404
    assert client.post(f"/api/bookings/{reference}/cancel", headers=other).status_code == 404


def test_every_guest_route_needs_sign_in(client: TestClient) -> None:
    hold_id = uuid.uuid4()
    routes = [
        ("post", "/api/holds", {"json": selection()}),
        ("get", f"/api/holds/{hold_id}", {}),
        ("put", f"/api/holds/{hold_id}/guest", {"json": GUEST}),
        ("delete", f"/api/holds/{hold_id}", {}),
        (
            "post",
            f"/api/holds/{hold_id}/payment",
            {"json": {}, "headers": {"Idempotency-Key": "k" * 16}},
        ),
        ("get", "/api/bookings/BK-ABCDEFGH", {}),
        ("post", "/api/bookings/BK-ABCDEFGH/cancel", {}),
    ]
    for method, path, kwargs in routes:
        response = getattr(client, method)(path, **kwargs)
        assert (response.status_code, response.json()["error"]["code"]) == (
            401,
            "not_authenticated",
        ), path


def test_staff_cannot_book(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        s.add(
            User(
                email="desk@example.com",
                password_hash=passwords.hash_password(PASSWORD),
                full_name="Desk",
                role="staff",
                team="reservations",
            )
        )
    csrf = {
        "X-CSRF-Token": client.post(
            "/api/auth/login", json={"email": "desk@example.com", "password": PASSWORD}
        ).json()["csrf_token"]
    }
    response = client.post("/api/holds", json=selection(), headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (403, "forbidden")


def test_changes_need_the_csrf_token(client: TestClient) -> None:
    sign_up(client)
    response = client.post("/api/holds", json=selection())  # signed in, but no token
    assert (response.status_code, response.json()["error"]["code"]) == (403, "csrf_failed")


def test_guest_routes_have_readable_operation_ids(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/holds"]["post"]["operationId"] == "start_booking"
    assert paths["/api/holds/{hold_id}/payment"]["post"]["operationId"] == "pay"
    assert paths["/api/bookings/{reference}/cancel"]["post"]["operationId"] == "cancel"

"""Daily booking export (A-10, A-90 to A-95, D-37)."""

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Booking, Hold, Payment, RatePlan, RoomType, User
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services import passwords
from app.services.bookings import cancel_booking, confirm_booking
from app.services.exports import COLUMNS
from app.services.holds import create_hold, set_guest_details
from app.services.quotes import HoldLineRequest, HoldRequest
from tests.factories import RULES, STAY, catalogue, guest, promo

IST = RULES.tz
DAY = date(2026, 11, 8)
PASSWORD = "a long enough password"


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=IST)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def book(
    s: Session, *, name: str, when: datetime, lines: list[tuple[str, int]], code: str | None = None
) -> tuple[int, str]:
    """Confirm a booking at `when`; returns (account id, reference)."""
    rooms = {rt.code: rt.id for rt in s.scalars(select(RoomType))}
    ro = s.scalar(select(RatePlan.id).where(RatePlan.code == "RO"))
    account = guest(s)
    request = HoldRequest(
        STAY, STAY + timedelta(days=2), [HoldLineRequest(rooms[c], ro, u, u) for c, u in lines]
    )
    hold_id = create_hold(s, account.id, request, now=when, rules=RULES, promo_code=code).hold_id
    set_guest_details(
        s,
        account.id,
        hold_id,
        name=name,
        email=f"{uuid.uuid4().hex[:6]}@example.com",
        phone="+91 00000 00042",
        now=when,
    )
    hold = s.get(Hold, hold_id)
    payment = Payment(
        hold_id=hold.id,
        idempotency_key=uuid.uuid4().hex,
        amount_paise=hold.total_paise,
        provider_reference=f"MOCK-{uuid.uuid4().hex[:8]}",
    )
    s.add(payment)
    s.flush()
    return account.id, confirm_booking(
        s, account.id, hold.id, payment.id, now=when, rules=RULES
    ).booking.reference


def staff_login(
    client: TestClient, committed, email: str, *, team: str | None, gm: bool = False
) -> None:
    with committed() as s, s.begin():
        s.add(
            User(
                email=email,
                password_hash=passwords.hash_password(PASSWORD),
                full_name="Staff",
                role="staff",
                team=team,
                is_gm=gm,
            )
        )
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )


def download(client: TestClient, day: date):
    return client.get("/api/exports/bookings.csv", params={"date": day.isoformat()})


def rows(response) -> list[dict]:
    return list(csv.DictReader(io.StringIO(response.text)))


@pytest.fixture
def reservations(client: TestClient, committed) -> TestClient:
    staff_login(client, committed, "desk@example.com", team="reservations")
    return client


# ---------- contents ----------


def test_columns_and_one_row_per_line_adding_up(reservations: TestClient, committed) -> None:
    with committed() as s, s.begin():
        catalogue(s)
        promo(s, "WELCOME10", 10)
        _, reference = book(
            s, name="Asha Rao", when=at(DAY, 10), lines=[("DLX", 2), ("FST", 1)], code="WELCOME10"
        )
        total = s.scalar(select(Booking.total_paise).where(Booking.reference == reference))
    response = download(reservations, DAY)
    assert response.text.splitlines()[0] == ",".join(COLUMNS)
    exported = rows(response)
    assert [(r["booking_id"], r["line_number"], r["status"], r["room_type"]) for r in exported] == [
        (reference, "1", "confirmed", "DLX"),
        (reference, "2", "confirmed", "FST"),
    ]
    assert sum(int(r["amount_paid_paise"]) for r in exported) == total
    first = exported[0]
    assert (first["payment_status"], first["promo_code"], first["rate_plan"]) == (
        "paid",
        "WELCOME10",
        "RO",
    )
    assert first["payment_reference"].startswith("MOCK-")
    assert first["created_at"] == "2026-11-08T10:00:00+05:30"


def test_cancellation_appears_on_its_own_day_and_old_files_never_change(
    reservations: TestClient, committed
) -> None:
    with committed() as s, s.begin():
        catalogue(s)
        user_id, reference = book(s, name="Asha Rao", when=at(DAY, 10), lines=[("DLX", 1)])
    before = download(reservations, DAY).content
    with committed() as s, s.begin():
        cancel_booking(s, user_id, reference, now=at(DAY + timedelta(days=1), 9), rules=RULES)

    assert download(reservations, DAY).content == before  # byte for byte (A-91)
    assert rows(download(reservations, DAY))[0]["status"] == "confirmed"
    [cancelled] = rows(download(reservations, DAY + timedelta(days=1)))
    assert (cancelled["booking_id"], cancelled["status"], cancelled["payment_status"]) == (
        reference,
        "cancelled",
        "refund",
    )


def test_confirmed_and_cancelled_the_same_day_gives_both_rows(
    reservations: TestClient, committed
) -> None:
    with committed() as s, s.begin():
        catalogue(s)
        user_id, reference = book(s, name="Asha Rao", when=at(DAY, 10), lines=[("DLX", 1)])
        cancel_booking(s, user_id, reference, now=at(DAY, 15), rules=RULES)
    assert [r["status"] for r in rows(download(reservations, DAY))] == ["confirmed", "cancelled"]


def test_days_are_ist_not_utc(reservations: TestClient, committed) -> None:
    with committed() as s, s.begin():
        catalogue(s)
        _, early = book(
            s, name="Early", when=at(DAY, 0, 30), lines=[("DLX", 1)]
        )  # 19:00 UTC the day before
        _, late = book(s, name="Late", when=at(DAY, 23, 50), lines=[("DLX", 1)])
    assert [r["booking_id"] for r in rows(download(reservations, DAY))] == [early, late]
    assert rows(download(reservations, DAY - timedelta(days=1))) == []


def test_formula_in_a_name_is_neutralised(reservations: TestClient, committed) -> None:
    with committed() as s, s.begin():
        catalogue(s)
        book(s, name='=HYPERLINK("http://evil.example")', when=at(DAY, 10), lines=[("DLX", 1)])
    [row] = rows(download(reservations, DAY))
    assert row["guest_name"] == '\'=HYPERLINK("http://evil.example")'
    assert row["guest_phone"] == "+91 00000 00042"  # phones are left as they are


def test_empty_day_is_just_the_header(reservations: TestClient) -> None:
    assert download(reservations, DAY).text == ",".join(COLUMNS) + "\r\n"


def test_download_headers(reservations: TestClient) -> None:
    response = download(reservations, DAY)
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"] == 'attachment; filename="bookings-2026-11-08.csv"'
    )
    assert response.headers["cache-control"] == "no-store"


def test_missing_or_bad_date_is_422(reservations: TestClient) -> None:
    assert reservations.get("/api/exports/bookings.csv").status_code == 422
    assert (
        reservations.get("/api/exports/bookings.csv", params={"date": "08-11-2026"}).status_code
        == 422
    )


def test_seeded_yesterday_has_confirmations_and_a_cancellation(
    reservations: TestClient, committed
) -> None:
    today = date(2026, 11, 7)
    with committed() as s, s.begin():
        reset_database(s)
        ctx = SeedContext(today=today, now=at(today, 10), tz=IST, gst_rule=RULES.gst_rule)
        seed(s, ctx, load_sample_enquiries())
    staff_login(reservations, committed, "desk2@example.com", team="reservations")
    exported = rows(download(reservations, today - timedelta(days=1)))
    confirmed = {r["booking_id"] for r in exported if r["status"] == "confirmed"}
    cancelled = {r["booking_id"] for r in exported if r["status"] == "cancelled"}
    assert len(confirmed) >= 3 and len(cancelled) >= 1


# ---------- who may download (A-90) ----------


@pytest.mark.parametrize(
    ("team", "gm", "status"),
    [("reservations", False, 200), (None, True, 200), ("events", False, 403)],
)
def test_staff_access(client: TestClient, committed, team, gm, status: int) -> None:
    staff_login(client, committed, "someone@example.com", team=team, gm=gm)
    assert download(client, DAY).status_code == status


def test_guests_and_signed_out_users_are_refused(client: TestClient) -> None:
    assert download(client, DAY).status_code == 401
    body = {
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "password": PASSWORD,
        "consent": True,
    }
    client.post("/api/auth/signup", json=body)
    assert download(client, DAY).status_code == 403


def test_export_operation_id(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/exports/bookings.csv"]["get"]["operationId"] == "export_bookings"

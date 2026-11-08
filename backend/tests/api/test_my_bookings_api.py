"""My bookings and checkout prefill (A-96 to A-99)."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Hold, Payment, RatePlan, RoomType, User
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services import passwords
from app.services.bookings import cancel_booking, confirm_booking
from app.services.holds import create_hold, set_guest_details
from app.services.quotes import HoldLineRequest, HoldRequest
from tests.factories import RULES, allotment, daily_rate, rate_plan, room_type

IST = RULES.tz
CREATED = datetime.combine(date(2026, 11, 7), time(10), tzinfo=IST)  # when bookings are made
VIEW = datetime.combine(date(2026, 11, 21), time(10), tzinfo=IST)  # when the list is viewed
PASSWORD = "a long enough password"


def open_stock(s: Session, first: date, nights: int) -> None:
    rt = s.scalar(select(RoomType).where(RoomType.code == "DLX")) or room_type(s, "DLX")
    rp = s.scalar(select(RatePlan).where(RatePlan.code == "RO")) or rate_plan(s, "RO")
    for i in range(nights):
        night = first + timedelta(days=i)
        allotment(s, rt, night, 10)
        daily_rate(s, rt, rp, night, 600_000)


def book(
    s: Session, user_id: int, check_in: date, nights: int, guest_email: str = "asha@example.com"
) -> str:
    rt = s.scalar(select(RoomType.id).where(RoomType.code == "DLX"))
    rp = s.scalar(select(RatePlan.id).where(RatePlan.code == "RO"))
    request = HoldRequest(
        check_in, check_in + timedelta(days=nights), [HoldLineRequest(rt, rp, 1, 2)]
    )
    hold_id = create_hold(s, user_id, request, now=CREATED, rules=RULES).hold_id
    set_guest_details(
        s,
        user_id,
        hold_id,
        name="Asha Rao",
        email=guest_email,
        phone="+91 00000 00042",
        now=CREATED,
    )
    hold = s.get(Hold, hold_id)
    payment = Payment(
        hold_id=hold.id, idempotency_key=uuid.uuid4().hex, amount_paise=hold.total_paise
    )
    s.add(payment)
    s.flush()
    return confirm_booking(
        s, user_id, hold.id, payment.id, now=CREATED, rules=RULES
    ).booking.reference


def account(s: Session, email: str, phone: str | None = "+91 00000 00007") -> int:
    user = User(
        email=email,
        password_hash=passwords.hash_password(PASSWORD),
        full_name="Asha Rao",
        role="guest",
        phone=phone,
    )
    s.add(user)
    s.flush()
    return user.id


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client(clock=lambda: VIEW)


# ---------- My bookings (A-96, A-97) ----------


def test_sections_and_order(client: TestClient, committed: sessionmaker[Session]) -> None:
    with committed() as s, s.begin():
        open_stock(s, date(2026, 11, 8), 120)
        me = account(s, "asha@example.com")
        later = book(s, me, date(2027, 2, 12), 2)
        sooner = book(s, me, date(2026, 12, 1), 2)
        staying = book(s, me, date(2026, 11, 20), 2)  # 20 to 22 Nov; viewed on 21 Nov
        old = book(s, me, date(2026, 11, 10), 2)
        older = book(s, me, date(2026, 11, 8), 1)
        cancelled_first = book(s, me, date(2026, 12, 10), 1)
        cancelled_last = book(s, me, date(2026, 12, 20), 1)
        cancel_booking(s, me, cancelled_first, now=CREATED + timedelta(days=1), rules=RULES)
        cancel_booking(s, me, cancelled_last, now=CREATED + timedelta(days=2), rules=RULES)
    login(client, "asha@example.com")

    items = client.get("/api/me/bookings").json()

    assert [(i["section"], i["reference"]) for i in items] == [
        ("upcoming", sooner),
        ("upcoming", later),
        ("current", staying),
        ("past", old),
        ("past", older),
        ("cancelled", cancelled_last),
        ("cancelled", cancelled_first),
    ]
    by_ref = {i["reference"]: i for i in items}
    assert by_ref[sooner]["can_cancel"] is True
    assert by_ref[staying]["can_cancel"] is False and by_ref[old]["can_cancel"] is False
    assert by_ref[sooner]["lines"] == [
        {
            "room_type": "DLX",
            "room_type_name": "DLX room",
            "rate_plan_name": "RO plan",
            "units": 1,
            "guests": 2,
        }
    ]
    assert by_ref[sooner]["nights"] == 2 and by_ref[sooner]["total_paise"] > 0


def test_only_this_accounts_bookings_never_matched_by_email(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        open_stock(s, date(2027, 2, 12), 2)
        me = account(s, "asha@example.com")
        someone = account(s, "someone@example.com")
        mine = book(s, me, date(2027, 2, 12), 2)
        book(s, someone, date(2027, 2, 12), 2)  # another account's booking
        book(
            s, someone, date(2027, 2, 12), 2, guest_email="asha@example.com"
        )  # names my email as guest
    login(client, "asha@example.com")
    assert [i["reference"] for i in client.get("/api/me/bookings").json()] == [mine]


def test_new_account_has_no_bookings(client: TestClient) -> None:
    body = {"full_name": "Ravi", "email": "ravi@example.com", "password": PASSWORD, "consent": True}
    client.post("/api/auth/signup", json=body)
    assert client.get("/api/me/bookings").json() == []


def test_seeded_demo_guest_sees_their_three_bookings(make_client, committed) -> None:
    today = date(2026, 11, 7)
    now = datetime.combine(today, time(10), tzinfo=IST)
    with committed() as s, s.begin():
        reset_database(s)
        seed(
            s,
            SeedContext(today=today, now=now, tz=IST, gst_rule=RULES.gst_rule),
            load_sample_enquiries(),
        )
    client = make_client(clock=lambda: now)
    login(client, "guest@example.com", "Guest-Demo-2026")
    assert sorted(i["section"] for i in client.get("/api/me/bookings").json()) == [
        "cancelled",
        "past",
        "upcoming",
    ]


def test_my_bookings_access(client: TestClient, committed) -> None:
    assert client.get("/api/me/bookings").status_code == 401
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
    login(client, "desk@example.com")
    assert client.get("/api/me/bookings").status_code == 403


def test_operation_id(client: TestClient) -> None:
    assert (
        client.get("/openapi.json").json()["paths"]["/api/me/bookings"]["get"]["operationId"]
        == "my_bookings"
    )


# ---------- checkout prefill (A-98) ----------


def start(client: TestClient, csrf: dict) -> dict:
    body = {
        "check_in": "2027-02-12",
        "check_out": "2027-02-14",
        "lines": [{"room_type": "DLX", "rate_plan": "RO", "units": 1, "guests": 2}],
    }
    response = client.post("/api/holds", json=body, headers=csrf)
    assert response.status_code == 201, response.json()
    return response.json()


def test_hold_suggests_the_accounts_details_until_guest_details_are_saved(
    client: TestClient, committed
) -> None:
    with committed() as s, s.begin():
        open_stock(s, date(2027, 2, 12), 2)
        account(s, "asha@example.com", phone="+91 00000 00007")
    csrf = login(client, "asha@example.com")
    hold = start(client, csrf)
    assert hold["guest"] is None
    assert hold["guest_suggestion"] == {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+91 00000 00007",
    }

    parents = {"name": "Meera Rao", "email": "meera@example.com", "phone": "+91 00000 00042"}
    saved = client.put(f"/api/holds/{hold['id']}/guest", json=parents, headers=csrf).json()
    assert (saved["guest"], saved["guest_suggestion"]) == (parents, None)
    me = client.get("/api/auth/me").json()
    assert (me["full_name"], me["email"], me["phone"]) == (
        "Asha Rao",
        "asha@example.com",
        "+91 00000 00007",
    )


def test_suggestion_without_a_phone(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        open_stock(s, date(2027, 2, 12), 2)
        account(s, "asha@example.com", phone=None)
    hold = start(client, login(client, "asha@example.com"))
    assert hold["guest_suggestion"]["phone"] is None

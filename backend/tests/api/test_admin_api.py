"""Admin inventory routes: access, formats and error mapping (A-100 to A-106)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditLog, RatePlan, RoomType, User
from app.services import passwords
from app.services.holds import create_hold
from tests.factories import N2, NIGHTS, NOW, RULES, STAY, catalogue, line, request

PASSWORD = "a long enough password"
RANGE = {"from_date": STAY.isoformat(), "to_date": N2.isoformat()}


@pytest.fixture
def client(make_client, committed: sessionmaker[Session]) -> TestClient:
    with committed() as s, s.begin():
        catalogue(s, dlx_web=4)
    return make_client(clock=lambda: NOW)


def login_staff(
    client: TestClient, committed, email: str, team: str | None, gm: bool = False
) -> dict:
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
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def desk(client: TestClient, committed) -> dict:
    return login_staff(client, committed, "desk@example.com", "reservations")


def test_inventory_calendar(client: TestClient, desk: dict) -> None:
    body = client.get(
        "/api/admin/inventory", params={"from": STAY.isoformat(), "to": N2.isoformat()}
    ).json()
    dlx = next(r for r in body["room_types"] if r["code"] == "DLX")
    assert [(n["date"], n["total_for_web"], n["available"]) for n in dlx["nights"]] == [
        (night.isoformat(), 4, 4) for night in NIGHTS
    ]
    assert dlx["nights"][0]["rates"]["RO"] == 600_000


def test_calendar_can_look_back_but_not_too_far(client: TestClient, desk: dict) -> None:
    past = client.get("/api/admin/inventory", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert past.status_code == 200
    long = client.get("/api/admin/inventory", params={"from": "2027-01-01", "to": "2027-03-31"})
    assert (long.status_code, long.json()["error"]["code"]) == (422, "range_too_long")


def test_set_allotment_rates_and_blackout(client: TestClient, desk: dict, committed) -> None:
    assert client.put(
        "/api/admin/allotment", json={**RANGE, "room_type": "DLX", "total_for_web": 6}, headers=desk
    ).json() == {"nights_changed": 2}
    assert client.put(
        "/api/admin/rates",
        json={**RANGE, "room_type": "DLX", "rate_plan": "RO", "price_paise": 650_000},
        headers=desk,
    ).json() == {"nights_changed": 2}
    assert client.put(
        "/api/admin/blackouts", json={**RANGE, "blackout": True}, headers=desk
    ).json() == {"nights_changed": 4, "nights_with_bookings": 0}
    night = client.get(
        "/api/admin/inventory", params={"from": STAY.isoformat(), "to": STAY.isoformat()}
    ).json()["room_types"][0]["nights"][0]
    assert (
        night["total_for_web"],
        night["rates"]["RO"],
        night["is_blackout"],
        night["available"],
    ) == (6, 650_000, True, 0)
    with committed() as s:
        assert sorted(s.scalars(select(AuditLog.action))) == [
            "set_allotment",
            "set_blackout",
            "set_rates",
        ]


def test_allotment_below_holds_is_409_with_nights(
    client: TestClient, desk: dict, committed
) -> None:
    with committed() as s, s.begin():
        c_user = s.scalar(select(User).where(User.role == "guest"))
        dlx = s.scalar(select(RoomType).where(RoomType.code == "DLX"))
        ro = s.scalar(select(RatePlan).where(RatePlan.code == "RO"))
        create_hold(s, c_user.id, request(line(dlx, ro, 3)), now=NOW, rules=RULES)
    response = client.put(
        "/api/admin/allotment", json={**RANGE, "room_type": "DLX", "total_for_web": 2}, headers=desk
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "allotment_below_commitments",
    )
    assert response.json()["error"]["details"]["nights"][0]["minimum"] == 3
    blocked = client.put("/api/admin/blackouts", json={**RANGE, "blackout": True}, headers=desk)
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "active_holds")


@pytest.mark.parametrize(
    ("path", "body", "code"),
    [
        ("/api/admin/allotment", {"room_type": "DLX", "total_for_web": 99}, "above_physical_units"),
        (
            "/api/admin/rates",
            {"room_type": "DLX", "rate_plan": "RO", "price_paise": 0},
            "invalid_price",
        ),
        ("/api/admin/blackouts", {"room_types": ["NOPE"], "blackout": True}, "unknown_room_type"),
    ],
)
def test_admin_rule_errors(
    client: TestClient, desk: dict, path: str, body: dict, code: str
) -> None:
    response = client.put(path, json={**RANGE, **body}, headers=desk)
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)


def test_past_dates_cannot_be_changed(client: TestClient, desk: dict) -> None:
    body = {
        "from_date": "2026-11-01",
        "to_date": "2026-11-02",
        "room_type": "DLX",
        "total_for_web": 1,
    }
    response = client.put("/api/admin/allotment", json=body, headers=desk)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "date_in_past")


def test_unknown_fields_are_refused(client: TestClient, desk: dict) -> None:
    body = {**RANGE, "room_type": "DLX", "total_for_web": 3, "sold": 0}
    assert client.put("/api/admin/allotment", json=body, headers=desk).status_code == 422


# ---------- access (A-100) ----------


@pytest.mark.parametrize(("team", "gm", "status"), [(None, True, 200), ("events", False, 403)])
def test_staff_access(client: TestClient, committed, team, gm, status: int) -> None:
    login_staff(client, committed, "someone@example.com", team, gm)
    assert (
        client.get(
            "/api/admin/inventory", params={"from": STAY.isoformat(), "to": N2.isoformat()}
        ).status_code
        == status
    )


def test_guests_signed_out_and_missing_csrf_are_refused(client: TestClient, committed) -> None:
    params = {"from": STAY.isoformat(), "to": N2.isoformat()}
    assert client.get("/api/admin/inventory", params=params).status_code == 401
    client.post(
        "/api/auth/signup",
        json={"full_name": "A", "email": "a@example.com", "password": PASSWORD, "consent": True},
    )
    assert client.get("/api/admin/inventory", params=params).status_code == 403
    client.cookies.clear()
    login_staff(client, committed, "desk2@example.com", "reservations")
    no_token = client.put(
        "/api/admin/allotment", json={**RANGE, "room_type": "DLX", "total_for_web": 3}
    )
    assert (no_token.status_code, no_token.json()["error"]["code"]) == (403, "csrf_failed")


def test_admin_operation_ids(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/admin/inventory"]["get"]["operationId"] == "admin_inventory"
    assert paths["/api/admin/allotment"]["put"]["operationId"] == "set_allotment"

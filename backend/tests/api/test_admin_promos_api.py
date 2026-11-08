"""Admin promo routes: formats, partial updates, fixed fields and access."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import User
from app.services import passwords
from tests.factories import NOW, promo

PASSWORD = "a long enough password"
TODAY = NOW.date()
NEW = {
    "code": "diwali15",
    "percent_off": 15,
    "valid_from": TODAY.isoformat(),
    "valid_to": (TODAY + timedelta(days=30)).isoformat(),
    "max_uses": 50,
}


@pytest.fixture
def client(make_client, committed: sessionmaker[Session]) -> TestClient:
    with committed() as s, s.begin():
        promo(s, "COFFEE20", 20, max_uses=5, used_count=5)
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
    return {
        "X-CSRF-Token": client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["csrf_token"]
    }


@pytest.fixture
def desk(client: TestClient, committed) -> dict:
    return login_staff(client, committed, "desk@example.com", "reservations")


def test_create_list_and_update(client: TestClient, desk: dict) -> None:
    created = client.post("/api/admin/promos", json=NEW, headers=desk)
    assert created.status_code == 201 and created.json()["code"] == "DIWALI15"
    codes = {p["code"]: p for p in client.get("/api/admin/promos").json()}
    assert codes["COFFEE20"]["uses_left"] == 0 and codes["COFFEE20"]["usable_today"] is False
    updated = client.patch(
        "/api/admin/promos/diwali15", json={"is_active": False}, headers=desk
    ).json()
    assert (updated["is_active"], updated["max_uses"]) == (False, 50)  # cap untouched


def test_null_removes_the_cap(client: TestClient, desk: dict) -> None:
    assert (
        client.patch("/api/admin/promos/COFFEE20", json={"max_uses": None}, headers=desk).json()[
            "max_uses"
        ]
        is None
    )


def test_code_and_percent_cannot_change(client: TestClient, desk: dict) -> None:
    for field in ({"percent_off": 50}, {"code": "FREE"}):
        response = client.patch("/api/admin/promos/COFFEE20", json=field, headers=desk)
        assert (response.status_code, response.json()["error"]["code"]) == (422, "validation_error")


def test_cap_below_uses_is_409_with_minimum(client: TestClient, desk: dict) -> None:
    response = client.patch("/api/admin/promos/COFFEE20", json={"max_uses": 4}, headers=desk)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "cap_below_uses")
    assert response.json()["error"]["details"] == {"used": 5, "reserved": 0, "minimum": 5}


@pytest.mark.parametrize(
    ("path_or_body", "status", "code"),
    [
        (("post", "/api/admin/promos", {**NEW, "code": "COFFEE20"}), 409, "promo_code_taken"),
        (("post", "/api/admin/promos", {**NEW, "percent_off": 100}), 422, "invalid_percent"),
        (("patch", "/api/admin/promos/NOPE", {"is_active": False}), 404, "promo_not_found"),
        (("patch", "/api/admin/promos/COFFEE20", {"is_active": None}), 422, "invalid_switch"),
    ],
)
def test_errors(client: TestClient, desk: dict, path_or_body, status: int, code: str) -> None:
    method, path, body = path_or_body
    response = getattr(client, method)(path, json=body, headers=desk)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)


@pytest.mark.parametrize(("team", "gm", "status"), [(None, True, 200), ("events", False, 403)])
def test_staff_access(client: TestClient, committed, team, gm, status: int) -> None:
    login_staff(client, committed, "someone@example.com", team, gm)
    assert client.get("/api/admin/promos").status_code == status


def test_guests_signed_out_and_missing_csrf(client: TestClient, committed) -> None:
    assert client.get("/api/admin/promos").status_code == 401
    login_staff(client, committed, "desk2@example.com", "reservations")
    response = client.post("/api/admin/promos", json=NEW)
    assert (response.status_code, response.json()["error"]["code"]) == (403, "csrf_failed")
    client.cookies.clear()
    client.post(
        "/api/auth/signup",
        json={"full_name": "A", "email": "a@example.com", "password": PASSWORD, "consent": True},
    )
    assert client.get("/api/admin/promos").status_code == 403


def test_operation_ids(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/admin/promos"]["get"]["operationId"] == "list_promos"
    assert paths["/api/admin/promos/{code}"]["patch"]["operationId"] == "update_promo"

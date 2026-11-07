"""Sign-up, login, sessions, CSRF and role checks (A-11, A-70 to A-78, D-33)."""

import hashlib
from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.security import CurrentUser, GmUser, GuestUser, StaffUser, require_user
from app.core.clock import utc_now
from app.db.models import User, UserSession
from app.services import passwords
from app.services.auth import SIGNUP_CONSENT_VERSION
from tests.api.conftest import FRONTEND

PASSWORD = "a long enough password"
SIGNUP = {
    "full_name": "Asha Rao",
    "email": "asha@example.com",
    "password": PASSWORD,
    "consent": True,
}


def _role_routes() -> APIRouter:
    router = APIRouter(prefix="/api/_test")
    reservations = require_user(role="staff", team="reservations")

    @router.get("/any")
    def any_user(user: CurrentUser) -> dict:
        return {"id": user.id}

    @router.get("/guest")
    def guest_only(user: GuestUser) -> dict:
        return {"ok": True}

    @router.get("/staff")
    def staff_only(user: StaffUser) -> dict:
        return {"ok": True}

    @router.get("/reservations")
    def reservations_only(user: Annotated[User, Depends(reservations)]) -> dict:
        return {"ok": True}

    @router.get("/gm")
    def gm_only(user: GmUser) -> dict:
        return {"ok": True}

    @router.post("/change")
    def change(user: CurrentUser) -> dict:
        return {"ok": True}

    return router


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client(_role_routes())


def staff(
    committed: sessionmaker[Session], email: str, *, team: str | None = None, gm: bool = False
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


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------- sign-up (A-75) ----------


def test_signup_creates_a_signed_in_guest(client: TestClient, committed) -> None:
    response = client.post("/api/auth/signup", json={**SIGNUP, "email": "  Asha@Example.com "})
    assert response.status_code == 201
    me = response.json()
    assert (me["email"], me["role"], me["team"], me["is_gm"]) == (
        "asha@example.com",
        "guest",
        None,
        False,
    )
    assert len(me["csrf_token"]) >= 32
    assert client.get("/api/auth/me").json()["id"] == me["id"]
    with committed() as s:
        user = s.get(User, me["id"])
        assert user.consent_version == SIGNUP_CONSENT_VERSION and user.consent_at is not None
        assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash


def test_session_cookie_attributes(client: TestClient) -> None:
    cookie = client.post("/api/auth/signup", json=SIGNUP).headers["set-cookie"].lower()
    for attribute in ("session=", "httponly", "secure", "samesite=lax", "path=/", "max-age=604800"):
        assert attribute in cookie
    assert "domain=" not in cookie


def test_signup_cannot_choose_a_role(client: TestClient) -> None:
    response = client.post("/api/auth/signup", json={**SIGNUP, "role": "staff", "is_gm": True})
    assert response.status_code == 422


def test_existing_email_is_reported(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post("/api/auth/signup", json={**SIGNUP, "email": "ASHA@example.com"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "email_taken")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"consent": False}, "consent_required"),
        ({"password": "short"}, "weak_password"),
        ({"email": "not-an-email"}, "invalid_email"),
        ({"full_name": "  "}, "invalid_name"),
        ({"phone": "call me"}, "invalid_phone"),
    ],
)
def test_signup_rules(client: TestClient, change: dict, code: str) -> None:
    response = client.post("/api/auth/signup", json={**SIGNUP, **change})
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)


def test_phone_is_optional(client: TestClient) -> None:
    assert client.post("/api/auth/signup", json=SIGNUP).json()["phone"] is None


# ---------- login (A-76) ----------


def test_login_with_correct_credentials(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    client.cookies.clear()
    response = login(client, " ASHA@example.com", PASSWORD)
    assert response.status_code == 200 and response.json()["email"] == "asha@example.com"


def test_wrong_email_and_wrong_password_look_the_same(client: TestClient, monkeypatch) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    client.cookies.clear()
    verifications: list[str] = []
    real_verify = passwords.verify_password
    monkeypatch.setattr(
        passwords, "verify_password", lambda h, p: verifications.append(p) or real_verify(h, p)
    )

    wrong_password = login(client, "asha@example.com", "not the password")
    unknown_email = login(client, "nobody@example.com", "not the password")

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json()["error"] == wrong_password.json()["error"]
        assert response.json()["error"]["code"] == "invalid_credentials"
    assert len(verifications) == 2  # the unknown email still costs a full verification


def test_account_without_a_usable_password_cannot_log_in(client: TestClient, committed) -> None:
    with committed() as s, s.begin():
        s.add(User(email="seeded@example.com", password_hash="!", full_name="Seeded", role="guest"))
    assert login(client, "seeded@example.com", "!").status_code == 401


# ---------- sessions (A-72) ----------


def test_only_a_hash_of_the_token_is_stored(client: TestClient, committed) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    token = client.cookies.get("session")
    with committed() as s:
        stored = s.scalar(select(UserSession.token_hash))
    assert stored == hashlib.sha256(token.encode()).hexdigest() and token not in stored


def test_every_login_starts_a_new_session(client: TestClient, committed) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    first = client.cookies.get("session")
    login(client, "asha@example.com")
    assert client.cookies.get("session") != first
    with committed() as s:
        assert s.scalar(select(func.count()).select_from(UserSession)) == 1  # old one ended


def test_logout_ends_the_session_everywhere(client: TestClient) -> None:
    csrf = client.post("/api/auth/signup", json=SIGNUP).json()["csrf_token"]
    stolen = client.cookies.get("session")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    client.cookies.set("session", stolen)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, committed) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    with committed() as s, s.begin():
        s.execute(update(UserSession).values(expires_at=utc_now() - timedelta(seconds=1)))
    response = client.get("/api/auth/me")
    assert (response.status_code, response.json()["error"]["code"]) == (401, "not_authenticated")


def test_no_cookie_is_not_authenticated(client: TestClient) -> None:
    assert client.get("/api/_test/any").status_code == 401


# ---------- CSRF (A-74) ----------


def test_state_change_needs_the_csrf_token(client: TestClient) -> None:
    csrf = client.post("/api/auth/signup", json=SIGNUP).json()["csrf_token"]
    missing = client.post("/api/_test/change")
    wrong = client.post("/api/_test/change", headers={"X-CSRF-Token": "x" * 43})
    right = client.post("/api/_test/change", headers={"X-CSRF-Token": csrf})
    assert [r.status_code for r in (missing, wrong, right)] == [403, 403, 200]
    assert missing.json()["error"]["code"] == "csrf_failed"


def test_reads_do_not_need_the_csrf_token(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    assert client.get("/api/_test/any").status_code == 200


def test_foreign_origin_is_refused_even_for_login(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    client.cookies.clear()
    evil = client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    ours = client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": PASSWORD},
        headers={"Origin": FRONTEND},
    )
    assert (evil.status_code, evil.json()["error"]["code"]) == (403, "csrf_failed")
    assert ours.status_code == 200


# ---------- roles (A-77) ----------


@pytest.mark.parametrize(
    ("who", "allowed"),
    [
        ("guest", {"any", "guest"}),
        ("reservations", {"any", "staff", "reservations"}),
        ("events", {"any", "staff"}),
        ("gm", {"any", "staff", "reservations", "gm"}),
    ],
)
def test_role_checks(client: TestClient, committed, who: str, allowed: set[str]) -> None:
    if who == "guest":
        client.post("/api/auth/signup", json=SIGNUP)
    else:
        email = f"{who}@example.com"
        staff(committed, email, team=None if who == "gm" else who, gm=who == "gm")
        assert login(client, email).status_code == 200
    for route in ("any", "guest", "staff", "reservations", "gm"):
        expected = 200 if route in allowed else 403
        assert client.get(f"/api/_test/{route}").status_code == expected, (who, route)


def test_me_without_session_is_401(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert (response.status_code, response.json()["error"]["code"]) == (401, "not_authenticated")

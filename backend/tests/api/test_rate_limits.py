"""Rate limits on sign-in routes (A-79 to A-83, D-34)."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter

PASSWORD = "a long enough password"


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def signup(client: TestClient, email: str):
    body = {"full_name": "Asha Rao", "email": email, "password": PASSWORD, "consent": True}
    return client.post("/api/auth/signup", json=body)


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_per_ip_limit(client: TestClient) -> None:
    signup(client, "asha@example.com")
    statuses = [
        login(client, f"user{i}@example.com", "wrong password!").status_code for i in range(20)
    ]
    assert set(statuses) == {401}
    refused = login(client, "asha@example.com")  # even correct credentials, from this IP
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(refused.headers["Retry-After"]) <= 900


def test_five_failures_lock_the_email_even_with_the_right_password(client: TestClient) -> None:
    signup(client, "asha@example.com")
    for _ in range(5):
        assert login(client, "asha@example.com", "wrong password!").status_code == 401
    locked = login(client, "ASHA@example.com")  # case does not dodge the lock
    assert locked.status_code == 429


def test_email_lock_does_not_affect_other_accounts(client: TestClient) -> None:
    signup(client, "asha@example.com")
    signup(client, "ravi@example.com")
    for _ in range(5):
        login(client, "asha@example.com", "wrong password!")
    assert login(client, "ravi@example.com").status_code == 200


def test_correct_login_clears_earlier_failures(client: TestClient) -> None:
    signup(client, "asha@example.com")
    for _ in range(4):
        login(client, "asha@example.com", "wrong password!")
    assert login(client, "asha@example.com").status_code == 200
    for _ in range(4):
        assert login(client, "asha@example.com", "wrong password!").status_code == 401
    assert login(client, "asha@example.com").status_code == 200


def test_signup_per_ip_limit(client: TestClient) -> None:
    for i in range(5):
        assert signup(client, f"guest{i}@example.com").status_code == 201
    refused = signup(client, "guest5@example.com")
    assert (refused.status_code, refused.json()["error"]["code"]) == (429, "rate_limited")


def test_limits_come_from_settings(make_client, monkeypatch) -> None:
    monkeypatch.setenv("RATE_SIGNUP_PER_IP", "1")
    client = make_client()
    assert signup(client, "one@example.com").status_code == 201
    assert signup(client, "two@example.com").status_code == 429


def test_refusal_is_logged_without_ip_or_email(client: TestClient, caplog) -> None:
    signup(client, "asha@example.com")
    with caplog.at_level(logging.INFO):
        for _ in range(6):
            login(client, "asha@example.com", "wrong password!")
    [record] = [r for r in caplog.records if r.getMessage() == "rate limited"]
    entry = json.loads(JsonFormatter().format(record))
    assert (entry["route"], entry["limit"]) == ("/api/auth/login", "login_failures_per_email")
    line = json.dumps(entry)
    assert "testclient" not in line and "asha" not in line  # no IP, no email (A-83)

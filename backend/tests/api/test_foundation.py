"""The web layer: health, error format, request ids, logs, CORS, one transaction per
request (A-64 to A-69, D-32)."""

import json
import logging
from datetime import date

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DbSession
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.models import RatePlan
from app.main import create_app
from app.services.errors import (
    BookingNotFound,
    CancellationNotAllowed,
    HoldNotActive,
    HoldNotFound,
    InvalidBookingRequest,
    InvalidPromoCode,
    InvalidStay,
    NotAvailable,
    PaymentMismatch,
    PaymentNotAllowed,
    Shortfall,
    StockLocked,
)

FRONTEND = "http://localhost:3000"

ERRORS = {
    "invalid_stay": (InvalidStay("check_in_in_past", "past"), 422, "check_in_in_past"),
    "invalid_request": (InvalidBookingRequest("too_many_units", "too many"), 422, "too_many_units"),
    "invalid_promo": (InvalidPromoCode("promo_expired", "expired"), 422, "promo_expired"),
    "not_available": (NotAvailable([Shortfall(7, date(2027, 2, 12), 2, 1)]), 409, "not_available"),
    "hold_not_active": (HoldNotActive("hold_expired", "expired"), 409, "hold_expired"),
    "cancel_not_allowed": (
        CancellationNotAllowed("too_late_to_cancel", "late"),
        409,
        "too_late_to_cancel",
    ),
    "payment_not_allowed": (
        PaymentNotAllowed("guest_details_missing", "details"),
        409,
        "guest_details_missing",
    ),
    "payment_mismatch": (
        PaymentMismatch("payment_not_for_hold", "mismatch"),
        409,
        "payment_not_for_hold",
    ),
    "hold_not_found": (HoldNotFound("Hold not found."), 404, "hold_not_found"),
    "booking_not_found": (BookingNotFound("Booking not found."), 404, "booking_not_found"),
    "stock_locked": (StockLocked("busy"), 503, "busy_try_again"),
}


class Guest(BaseModel):
    email: str
    nights: int


def _build_test_routes() -> APIRouter:
    router = APIRouter(prefix="/api/_test")

    @router.get("/raise/{name}")
    def raise_error(name: str) -> None:
        raise ERRORS[name][0]

    @router.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret detail asha@example.com")

    @router.get("/lookup/{reference}")
    def lookup(reference: str, email: str) -> dict:
        return {"ok": True}

    @router.post("/validate")
    def validate(body: Guest) -> dict:
        return {"ok": True}

    @router.post("/rate-plans/{code}")
    def write(code: str, db: DbSession, fail: bool = False) -> dict:
        db.add(RatePlan(code=code, name=code))
        db.flush()
        if fail:
            raise InvalidBookingRequest("rolled_back", "after a write")
        return {"ok": True}

    return router


@pytest.fixture
def client(committed: sessionmaker[Session], test_database_url: str):
    settings = Settings(database_url=test_database_url, cors_origins=FRONTEND, _env_file=None)
    app = create_app(settings, session_factory=committed)
    app.include_router(_build_test_routes())
    with TestClient(app) as test_client:
        yield test_client


# ---------- health (A-65) ----------


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(test_database_url: str) -> None:
    settings = Settings(database_url="postgresql://u:p@127.0.0.1:1/nowhere", _env_file=None)
    with TestClient(create_app(settings)) as unreachable:
        response = unreachable.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


# ---------- error format (A-64) ----------


@pytest.mark.parametrize("name", list(ERRORS))
def test_domain_errors_map_to_status_and_code(client: TestClient, name: str) -> None:
    _, status, code = ERRORS[name]
    response = client.get(f"/api/_test/raise/{name}")
    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_not_available_lists_the_shortfalls(client: TestClient) -> None:
    details = client.get("/api/_test/raise/not_available").json()["error"]["details"]
    assert details == {
        "shortfalls": [{"room_type_id": 7, "date": "2027-02-12", "requested": 2, "available": 1}]
    }


def test_busy_is_retryable(client: TestClient) -> None:
    assert client.get("/api/_test/raise/stock_locked").headers["Retry-After"] == "1"


def test_validation_errors_use_the_format_without_echoing_input(client: TestClient) -> None:
    response = client.post(
        "/api/_test/validate", json={"email": "asha@example.com", "nights": "many"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "nights"]
    assert "many" not in response.text and "asha@example.com" not in response.text


def test_unknown_route_uses_the_format(client: TestClient) -> None:
    response = client.get("/api/nowhere")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_crash_is_a_generic_500_with_details_only_in_the_log(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.INFO):
        response = client.get("/api/_test/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    [error] = [r for r in caplog.records if r.getMessage() == "unhandled error"]
    line = JsonFormatter().format(error)
    assert json.loads(line)["error_type"] == "RuntimeError"
    assert "secret" not in line and "asha@example.com" not in line  # message never logged
    assert json.loads(line)["request_id"] == response.json()["request_id"]


# ---------- request ids and logs (A-66) ----------


def test_request_id_is_generated_or_echoed(client: TestClient) -> None:
    generated = client.get("/health").headers["X-Request-ID"]
    assert len(generated) == 32
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    returned = client.get("/health", headers={"X-Request-ID": "x" * 65}).headers["X-Request-ID"]
    assert returned != "x" * 65 and len(returned) == 32


def test_access_log_has_route_template_and_no_personal_data(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.INFO):
        client.get("/api/_test/lookup/BK-7F3K9QXM?email=asha@example.com")
    [record] = [r for r in caplog.records if r.getMessage() == "request"]
    entry = json.loads(JsonFormatter().format(record))
    assert entry["route"] == "/api/_test/lookup/{reference}"
    assert (entry["method"], entry["status"]) == ("GET", 200)
    line = json.dumps(entry)
    assert "asha@example.com" not in line and "BK-7F3K9QXM" not in line and "?" not in line


def test_http_client_urls_are_not_logged(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.INFO):
        client.get("/api/_test/lookup/BK-7F3K9QXM?email=asha@example.com")
    assert not any("asha@example.com" in r.getMessage() for r in caplog.records)


def test_formatter_drops_fields_that_were_not_reviewed() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    record.email = "asha@example.com"
    assert "asha@example.com" not in JsonFormatter().format(record)


# ---------- CORS (A-68) ----------


def test_cors_allows_only_the_frontend(client: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = client.options("/health", headers={"Origin": FRONTEND, **preflight})
    assert allowed.headers["access-control-allow-origin"] == FRONTEND
    assert allowed.headers["access-control-allow-credentials"] == "true"
    refused = client.options("/health", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in refused.headers


def test_cors_origins_parse_from_a_comma_separated_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://resort.example.com/")
    settings = Settings(database_url="postgresql://u:p@h/db", _env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "https://resort.example.com"]


# ---------- one transaction per request (A-69) ----------


def test_successful_request_is_committed(
    client: TestClient, committed: sessionmaker[Session]
) -> None:
    assert client.post("/api/_test/rate-plans/KEEP").status_code == 200
    with committed() as s:
        assert s.scalar(select(RatePlan.code).where(RatePlan.code == "KEEP")) == "KEEP"


def test_failed_request_is_rolled_back(
    client: TestClient, committed: sessionmaker[Session]
) -> None:
    assert client.post("/api/_test/rate-plans/GONE?fail=true").status_code == 422
    with committed() as s:
        assert s.scalar(select(RatePlan.code).where(RatePlan.code == "GONE")) is None


# ---------- OpenAPI ----------


def test_openapi_uses_readable_operation_ids(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/health"]["get"]["operationId"] == "health"

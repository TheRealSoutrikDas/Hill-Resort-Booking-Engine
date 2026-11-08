"""Enquiry routes, part a: public form, inbox, detail and re-run (A-122 to A-125, D-43)."""

import logging
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import JsonFormatter
from app.db.models import Enquiry
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services import audit, enquiry_pipeline
from tests.api.conftest import FRONTEND
from tests.factories import RULES
from tests.fakes import StubLLMClassifier

IST = RULES.tz
RECEIVED = date(2026, 11, 5)
NOW = datetime.combine(RECEIVED, time(10), tzinfo=IST)
VILLA = "Is a villa free 14-16 Nov for 2 adults and a child?"
FORM = {"name": "Asha Rao", "email": "asha@example.com", "message": VILLA, "consent": True}


@pytest.fixture
def client(make_client, committed: sessionmaker[Session]) -> TestClient:
    with committed() as s, s.begin():
        reset_database(s)
        seed(
            s,
            SeedContext(today=RECEIVED, now=NOW, tz=IST, gst_rule=RULES.gst_rule),
            load_sample_enquiries(),
        )
    c = make_client(clock=lambda: NOW)
    c.app.state.model_backend = StubLLMClassifier()
    return c


def login(client: TestClient, email: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def as_desk(client: TestClient) -> dict:
    return login(client, "reservations@example.com", "Reservations-Demo-2026")


# ---------- public form (A-122) ----------


def test_form_returns_only_a_reference(client: TestClient, committed) -> None:
    response = client.post("/api/enquiries", json=FORM)
    assert response.status_code == 201
    assert response.json() == {
        "reference": "ENQ-5001",
        "message": "Thank you. Our team will reply to you soon.",
    }
    with committed() as s:
        enquiry = s.scalar(select(Enquiry).where(Enquiry.reference == "ENQ-5001"))
        assert (enquiry.status, enquiry.lane, enquiry.backend) == (
            "classified",
            "room_booking",
            "stub",
        )


def test_form_saves_and_routes_with_the_model_down(client: TestClient, committed) -> None:
    client.app.state.model_backend = StubLLMClassifier("timeout")
    reference = client.post("/api/enquiries", json=FORM).json()["reference"]
    with committed() as s:
        enquiry = s.scalar(select(Enquiry).where(Enquiry.reference == reference))
        assert (enquiry.lane, enquiry.is_fallback, enquiry.error) == (
            "room_booking",
            True,
            "timeout",
        )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"message": "   "}, "empty_message"),
        ({"message": "x" * 2_001}, "message_too_long"),
        ({"consent": False}, "consent_required"),
        ({"email": None}, "contact_required"),
    ],
)
def test_form_validation(client: TestClient, change: dict, code: str) -> None:
    response = client.post("/api/enquiries", json={**FORM, **change})
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)


def test_form_rejects_unknown_fields(client: TestClient) -> None:
    assert client.post("/api/enquiries", json={**FORM, "lane": "complaint"}).status_code == 422


def test_form_is_rate_limited(client: TestClient) -> None:
    client.app.state.settings.rate_enquiry_per_ip = 3  # its own limit, not another route's
    for _ in range(3):
        assert client.post("/api/enquiries", json=FORM).status_code == 201
    refused = client.post("/api/enquiries", json=FORM)
    assert (refused.status_code, refused.json()["error"]["code"]) == (429, "rate_limited")


def test_form_refuses_a_foreign_origin(client: TestClient) -> None:
    evil = client.post("/api/enquiries", json=FORM, headers={"Origin": "https://evil.example"})
    assert (evil.status_code, evil.json()["error"]["code"]) == (403, "csrf_failed")
    assert client.post("/api/enquiries", json=FORM, headers={"Origin": FRONTEND}).status_code == 201


def test_form_never_logs_the_message_or_contact(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/api/enquiries", json=FORM)
    lines = " ".join(JsonFormatter().format(r) for r in caplog.records)
    assert "villa" not in lines.lower() and "asha" not in lines.lower()


# ---------- inbox (A-123) ----------


def test_inbox_lists_newest_first_with_lane_counts(client: TestClient) -> None:
    client.post("/api/enquiries", json=FORM)
    as_desk(client)
    body = client.get("/api/enquiries").json()
    assert body["items"][0]["reference"] == "ENQ-5001"  # newest
    assert (
        body["counts"]["room_booking"] == 1 and body["counts"]["pending"] == 27
    )  # seeded, not yet run
    assert set(body["counts"]) == {
        "room_booking",
        "wedding",
        "corporate_offsite",
        "complaint",
        "unsorted",
        "pending",
        "failed",
        "replied",
    }


def test_inbox_filters(client: TestClient) -> None:
    client.post("/api/enquiries", json=FORM)
    client.post("/api/enquiries", json={**FORM, "message": "The room was dirty and the AC leaked."})
    as_desk(client)
    complaints = client.get("/api/enquiries", params={"lane": "complaint"}).json()["items"]
    assert [(i["lane"], i["gm_alert"]) for i in complaints] == [("complaint", True)]
    pending = client.get("/api/enquiries", params={"status": "pending"}).json()["items"]
    assert len(pending) == 27 and all(i["lane"] is None for i in pending)
    assert client.get("/api/enquiries", params={"lane": "spam"}).status_code == 422


def test_events_team_and_gm_see_every_lane(client: TestClient) -> None:
    client.post("/api/enquiries", json=FORM)
    for email, password in [
        ("events@example.com", "Events-Demo-2026"),
        ("gm@example.com", "GM-Demo-2026"),
    ]:
        client.cookies.clear()
        login(client, email, password)
        assert (
            client.get("/api/enquiries", params={"lane": "room_booking"}).json()["counts"][
                "room_booking"
            ]
            == 1
        )


# ---------- detail ----------


def test_detail_shows_the_message_beside_the_fields(client: TestClient) -> None:
    client.post("/api/enquiries", json=FORM)
    as_desk(client)
    body = client.get("/api/enquiries/enq-5001").json()
    assert body["message"] == VILLA
    assert body["fields"]["check_in"] == "2026-11-14" and body["fields"]["guests"] == 3
    assert (
        body["keyword_output"]["category"] == "room_booking"
        and body["model_output"]["stub"] is True
    )
    assert body["lane_reasons"] == [] and body["alert"] is None and body["can_reclassify"] is True
    assert "Plantation Villa" in body["draft_reply"]


def test_detail_explains_unsorted(client: TestClient) -> None:
    client.post("/api/enquiries", json={**FORM, "message": "Do you sell your coffee beans online?"})
    as_desk(client)
    body = client.get("/api/enquiries/ENQ-5001").json()
    assert (body["lane"], body["lane_reasons"]) == (
        "unsorted",
        ["low_confidence", "category_other"],
    )


def test_unknown_reference_is_404(client: TestClient) -> None:
    as_desk(client)
    response = client.get("/api/enquiries/ENQ-9999")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "enquiry_not_found")


# ---------- re-run (A-125) ----------


def test_retry_turns_a_failed_enquiry_into_a_classified_one(
    client: TestClient, monkeypatch
) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(enquiry_pipeline, "build_draft", broken)
    client.post("/api/enquiries", json=FORM)
    monkeypatch.undo()
    csrf = as_desk(client)
    assert client.get("/api/enquiries/ENQ-5001").json()["status"] == "failed"
    body = client.post("/api/enquiries/ENQ-5001/classify", headers=csrf).json()
    assert (body["status"], body["lane"]) == ("classified", "room_booking")
    [entry] = body["history"]
    assert (entry["action"], entry["by"], entry["old"]["status"], entry["new"]["status"]) == (
        "reclassify",
        "Reservations Desk",
        "failed",
        "classified",
    )


def test_seeded_pending_enquiry_can_be_classified(client: TestClient) -> None:
    csrf = as_desk(client)
    body = client.post("/api/enquiries/ENQ-4428/classify", headers=csrf).json()
    assert (body["lane"], body["alert"]["reason"]) == ("complaint", "complaint (keyword and model)")


def test_retry_is_refused_once_staff_have_handled_it(client: TestClient, committed) -> None:
    client.post("/api/enquiries", json=FORM)
    csrf = as_desk(client)
    with committed() as s, s.begin():  # a correction from step 21b
        audit.record(
            s,
            actor_id=2,
            entity_type="enquiry",
            entity_id="ENQ-5001",
            action="correct",
            field="category",
            old="wedding",
            new="room_booking",
            now=NOW,
        )
    response = client.post("/api/enquiries/ENQ-5001/classify", headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "already_handled")
    assert client.get("/api/enquiries/ENQ-5001").json()["can_reclassify"] is False


# ---------- access ----------


def test_staff_routes_need_staff(client: TestClient) -> None:
    routes = [
        ("get", "/api/enquiries"),
        ("get", "/api/enquiries/ENQ-4410"),
        ("post", "/api/enquiries/ENQ-4410/classify"),
    ]
    for method, path in routes:
        assert getattr(client, method)(path).status_code == 401, path
    guest = login(client, "guest@example.com", "Guest-Demo-2026")
    for method, path in routes:
        assert getattr(client, method)(path, headers=guest).status_code == 403, path


def test_retry_needs_the_csrf_token(client: TestClient) -> None:
    as_desk(client)
    response = client.post("/api/enquiries/ENQ-4410/classify")
    assert (response.status_code, response.json()["error"]["code"]) == (403, "csrf_failed")


def test_operation_ids(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/enquiries"]["post"]["operationId"] == "send_enquiry"
    assert paths["/api/enquiries"]["get"]["operationId"] == "inbox"
    assert paths["/api/enquiries/{reference}/classify"]["post"]["operationId"] == "reclassify"

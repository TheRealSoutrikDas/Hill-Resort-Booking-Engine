"""AI eval against actual eval: what the AI decided, what the GM approved (A-145, A-146,
D-47)."""

from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services.enquiry_metrics import ai_accuracy, backend_label
from tests.factories import RULES
from tests.fakes import StubLLMClassifier

IST = RULES.tz
RECEIVED = date(2026, 11, 5)
NOW = datetime.combine(RECEIVED, time(10), tzinfo=IST)
VILLA = "Is a villa free 14-16 Nov for 2 adults?"
WEDDING = "Planning our wedding in February 2027 for 150 guests."
COMPLAINT = "The room was dirty and the AC leaked all night."


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


def submit(client: TestClient, message: str) -> str:
    body = {"name": "Asha Rao", "email": "asha@example.com", "message": message, "consent": True}
    response = client.post("/api/enquiries", json=body)
    assert response.status_code == 201
    return response.json()["reference"]


def login(client: TestClient, email: str, password: str) -> dict:
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def as_desk(client: TestClient) -> dict:
    return login(client, "reservations@example.com", "Reservations-Demo-2026")


def as_gm(client: TestClient) -> dict:
    return login(client, "gm@example.com", "GM-Demo-2026")


def get(client: TestClient, reference: str) -> dict:
    return client.get(f"/api/enquiries/{reference}").json()


def verify(client: TestClient, reference: str, headers: dict):
    return client.post(f"/api/enquiries/{reference}/verify", headers=headers)


# ---------- ai_eval is the AI's decision, never changed by staff ----------


def test_pipeline_records_the_ai_decision(client: TestClient) -> None:
    ref = submit(client, VILLA)
    as_desk(client)
    body = get(client, ref)
    assert body["ai_eval"] == {
        "category": "room_booking",
        "lane": "room_booking",
        "fields": body["fields"],
        "confidence": 0.9,
        "backend": "stub",
        "is_fallback": False,
    }
    assert body["fields"]["check_in"] == "2026-11-14" and body["fields"]["guests"] == 2
    assert (body["actual_eval"], body["verified_by"], body["can_verify"]) == (None, None, True)


def test_fallback_is_recorded_in_ai_eval(client: TestClient) -> None:
    client.app.state.model_backend = StubLLMClassifier("timeout")
    ref = submit(client, COMPLAINT)
    as_desk(client)
    ai = get(client, ref)["ai_eval"]
    assert (ai["backend"], ai["is_fallback"], ai["category"]) == ("keyword", True, "complaint")


def test_staff_changes_never_touch_ai_eval(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    before = get(client, ref)["ai_eval"]
    client.patch(
        f"/api/enquiries/{ref}", json={"category": "wedding", "fields": {"guests": 4}}, headers=csrf
    )
    client.post(f"/api/enquiries/{ref}/route", json={"lane": "unsorted"}, headers=csrf)
    after = get(client, ref)
    assert after["ai_eval"] == before
    assert (after["category"], after["lane"]) == ("wedding", "unsorted")


# ---------- the GM approves (A-145) ----------


def test_gm_approves_the_classification_as_it_stands(client: TestClient) -> None:
    ref = submit(client, VILLA)
    body = verify(client, ref, as_gm(client)).json()
    assert body["actual_eval"] == {
        "category": "room_booking",
        "lane": "room_booking",
        "fields": body["ai_eval"]["fields"],
    }
    assert (body["verified_by"], body["can_verify"], body["can_act"], body["can_reclassify"]) == (
        "General Manager",
        False,
        False,
        False,
    )
    entry = body["history"][-1]
    assert (entry["action"], entry["old"]["category"], entry["new"]["category"]) == (
        "verify",
        "room_booking",
        "room_booking",
    )


def test_approval_after_a_correction_records_the_corrected_values(client: TestClient) -> None:
    ref = submit(client, WEDDING)
    client.patch(
        f"/api/enquiries/{ref}", json={"category": "corporate_offsite"}, headers=as_desk(client)
    )
    body = verify(client, ref, as_gm(client)).json()
    assert body["ai_eval"]["category"] == "wedding"
    assert body["actual_eval"]["category"] == "corporate_offsite"
    assert body["actual_eval"]["lane"] == "corporate_offsite"


def test_only_the_gm_can_approve(client: TestClient) -> None:
    ref = submit(client, VILLA)
    for email, password in (
        ("reservations@example.com", "Reservations-Demo-2026"),
        ("events@example.com", "Events-Demo-2026"),
        ("guest@example.com", "Guest-Demo-2026"),
    ):
        assert verify(client, ref, login(client, email, password)).status_code == 403, email
    client.cookies.clear()
    assert verify(client, ref, {}).status_code == 401


def test_approval_fixes_the_classification(client: TestClient) -> None:
    ref = submit(client, VILLA)
    gm = as_gm(client)
    verify(client, ref, gm)
    for method, path, body in (
        ("patch", f"/api/enquiries/{ref}", {"category": "wedding"}),
        ("post", f"/api/enquiries/{ref}/route", {"lane": "unsorted"}),
    ):
        response = getattr(client, method)(path, json=body, headers=gm)
        assert (response.status_code, response.json()["error"]["code"]) == (409, "already_verified")
    again = verify(client, ref, gm)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_verified")
    assert client.post(f"/api/enquiries/{ref}/classify", headers=gm).json()["error"]["code"] == (
        "already_handled"
    )
    reply = client.post(f"/api/enquiries/{ref}/reply", json={"text": "Thank you."}, headers=gm)
    assert reply.json()["status"] == "replied"  # replying is still allowed


def test_a_reply_is_not_an_approval(client: TestClient) -> None:
    ref = submit(client, VILLA)
    client.post(f"/api/enquiries/{ref}/reply", json={"text": "Thank you."}, headers=as_desk(client))
    body = get(client, ref)
    assert (body["actual_eval"], body["can_verify"]) == (None, True)  # A-146
    approved = verify(client, ref, as_gm(client)).json()
    assert approved["actual_eval"]["category"] == "room_booking"


def test_pending_enquiry_cannot_be_approved(client: TestClient) -> None:
    response = verify(client, "ENQ-4410", as_gm(client))
    assert (response.status_code, response.json()["error"]["code"]) == (409, "not_classified")


def test_rerun_replaces_ai_eval_before_anyone_acts(client: TestClient) -> None:
    gm = as_gm(client)
    body = client.post("/api/enquiries/ENQ-4428/classify", headers=gm).json()
    assert body["ai_eval"]["category"] == "complaint"


def test_database_refuses_a_half_recorded_approval(client: TestClient, committed) -> None:
    ref = submit(client, VILLA)
    for change in ("actual_eval = '{}'::jsonb", "verified_at = now()"):
        with committed() as s:
            with pytest.raises(IntegrityError):
                with s.begin():
                    s.execute(
                        text(f"UPDATE enquiries SET {change} WHERE reference = :r"), {"r": ref}
                    )


# ---------- accuracy on real enquiries ----------


def test_metrics_compare_ai_eval_with_actual_eval(client: TestClient) -> None:
    right = submit(client, VILLA)
    wrong = submit(client, WEDDING)
    unapproved = submit(client, "Is a deluxe room free 20-22 Dec for 2 adults?")
    client.app.state.model_backend = StubLLMClassifier("timeout")
    fallback = submit(client, COMPLAINT)
    desk = as_desk(client)
    client.patch(f"/api/enquiries/{wrong}", json={"category": "corporate_offsite"}, headers=desk)
    gm = as_gm(client)
    for ref in (right, wrong, fallback):
        assert verify(client, ref, gm).status_code == 200
    m = client.get("/api/enquiries/metrics").json()
    assert m["awaiting_approval"] == 1  # `unapproved`; seeded pending ones have no ai_eval
    assert m["ai_accuracy"] == {
        "keyword (fallback)": {
            "approved": 1,
            "category": {"count": 1, "out_of": 1, "value": 1.0},
            "lane": {"count": 1, "out_of": 1, "value": 1.0},
            "fields": {"count": 1, "out_of": 1, "value": 1.0},
        },
        "stub": {
            "approved": 2,
            "category": {"count": 1, "out_of": 2, "value": 0.5},
            "lane": {"count": 1, "out_of": 2, "value": 0.5},
            "fields": {"count": 2, "out_of": 2, "value": 1.0},
        },
    }
    assert unapproved


def test_ai_accuracy_is_pure_and_counts_field_changes() -> None:
    ai = {
        "category": "room_booking",
        "lane": "room_booking",
        "fields": {"guests": 2},
        "backend": "gemini",
        "is_fallback": False,
    }
    same = {"category": "room_booking", "lane": "room_booking", "fields": {"guests": 2}}
    more = {"category": "room_booking", "lane": "room_booking", "fields": {"guests": 3}}
    result = ai_accuracy([(ai, same), (ai, more)])
    assert list(result) == ["gemini"]
    g = result["gemini"]
    assert (g.approved, g.category.value, g.fields.count, g.fields.out_of) == (2, 1.0, 1, 2)
    assert backend_label({"backend": "keyword", "is_fallback": True}) == "keyword (fallback)"
    assert ai_accuracy([]) == {}

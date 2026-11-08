"""Enquiry routes, part b: correct, re-route, reply, GM alerts and metrics
(A-124, A-126 to A-129, D-44)."""

import logging
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.classifiers.stub import StubLLMClassifier
from app.core.logging import JsonFormatter
from app.db.models import Enquiry, User
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services.enquiry_actions import EnquiryActionRefused, reply_to_enquiry
from app.services.enquiry_inbox import get_enquiry
from tests.factories import RULES
from tests.parallel import run_in_parallel

IST = RULES.tz
RECEIVED = date(2026, 11, 5)
START = datetime.combine(RECEIVED, time(10), tzinfo=IST)
VILLA = "Is a villa free 14-16 Nov for 2 adults?"
COMPLAINT = "The room was dirty and the AC leaked all night."
SEEDED = 27  # sample enquiries, saved as pending


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(make_client, committed: sessionmaker[Session], clock: FakeClock) -> TestClient:
    with committed() as s, s.begin():
        reset_database(s)
        seed(
            s,
            SeedContext(today=RECEIVED, now=START, tz=IST, gst_rule=RULES.gst_rule),
            load_sample_enquiries(),
        )
    c = make_client(clock=clock)
    c.app.state.model_backend = StubLLMClassifier()
    return c


def submit(client: TestClient, message: str, name: str = "Asha Rao") -> str:
    body = {"name": name, "email": "asha@example.com", "message": message, "consent": True}
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


# ---------- correct (A-124) ----------


def test_category_correction_moves_lane_owner_and_draft(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    body = client.patch(f"/api/enquiries/{ref}", json={"category": "wedding"}, headers=csrf).json()
    assert (body["category"], body["lane"], body["owner_team"]) == ("wedding", "wedding", "events")
    assert "Events team" in body["draft_reply"]
    [entry] = body["history"]
    assert (entry["action"], entry["field"], entry["old"], entry["new"], entry["by"]) == (
        "correct",
        "category",
        "room_booking",
        "wedding",
        "Reservations Desk",
    )
    assert body["can_reclassify"] is False  # a re-run would overwrite the correction (A-125)
    assert body["model_output"]["category"] == "room_booking"  # kept for comparison


def test_field_correction_reprices_the_draft_in_code(client: TestClient) -> None:
    ref = submit(client, VILLA)
    expected = submit(client, "Is a villa free 14-16 Nov for 4 adults?")
    csrf = as_desk(client)
    before = get(client, ref)["draft_reply"]
    body = client.patch(
        f"/api/enquiries/{ref}", json={"fields": {"guests": 4}}, headers=csrf
    ).json()
    assert body["fields"]["guests"] == 4 and body["fields"]["check_in"] == "2026-11-14"
    assert body["draft_reply"] != before
    # Same price as an enquiry that asked for 4 guests in the first place: one price path.
    assert body["draft_reply"] == get(client, expected)["draft_reply"]
    [entry] = body["history"]
    assert (entry["field"], entry["old"], entry["new"]) == ("fields.guests", 2, 4)


def test_clearing_a_field_leaves_its_placeholder_visible(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    body = client.patch(
        f"/api/enquiries/{ref}", json={"fields": {"room_type": None}}, headers=csrf
    ).json()
    assert "room_type" not in body["fields"]
    assert "{room_type}" in body["draft_reply"] and "{price_total}" in body["draft_reply"]


@pytest.mark.parametrize(
    ("fields", "code", "bad"),
    [
        ({"guests": 0}, "invalid_fields", ["guests"]),
        ({"room_type": "villa!"}, "invalid_fields", ["room_type"]),
        ({"check_out": "2026-11-13"}, "invalid_fields", ["fields"]),  # before check-in
        (
            {"check_in": "2030-01-01", "check_out": "2030-01-03"},
            "implausible_dates",
            ["check_in", "check_out", "event_month"],
        ),
    ],
)
def test_corrections_get_the_same_checks_as_extraction(
    client: TestClient, fields: dict, code: str, bad: list
) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    response = client.patch(f"/api/enquiries/{ref}", json={"fields": fields}, headers=csrf)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["details"]["fields"] == bad
    assert get(client, ref)["history"] == []  # nothing half applied


def test_correction_with_no_change_is_refused(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    response = client.patch(
        f"/api/enquiries/{ref}",
        json={"category": "room_booking", "fields": {"guests": 2}},
        headers=csrf,
    )
    assert (response.status_code, response.json()["error"]["code"]) == (422, "no_change")


def test_correction_rejects_unknown_fields(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    for body in ({"lane": "complaint"}, {"fields": {"price_total": 1}}):
        assert client.patch(f"/api/enquiries/{ref}", json=body, headers=csrf).status_code == 422


def test_correcting_to_complaint_alerts_the_gm(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    body = client.patch(
        f"/api/enquiries/{ref}", json={"category": "complaint"}, headers=csrf
    ).json()
    assert (body["lane"], body["owner_team"]) == ("complaint", "gm")
    assert body["alert"]["reason"] == "complaint (staff)"


def test_pending_enquiry_cannot_be_corrected(client: TestClient) -> None:
    csrf = as_desk(client)
    response = client.patch("/api/enquiries/ENQ-4410", json={"category": "wedding"}, headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "not_classified")


# ---------- re-route (A-126) ----------


def test_reroute_moves_lane_and_owner_but_keeps_category(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    body = client.post(
        f"/api/enquiries/{ref}/route", json={"lane": "unsorted"}, headers=csrf
    ).json()
    assert (body["lane"], body["owner_team"], body["category"]) == (
        "unsorted",
        None,
        "room_booking",
    )
    [entry] = body["history"]
    assert (entry["action"], entry["old"], entry["new"]) == ("reroute", "room_booking", "unsorted")
    assert body["can_reclassify"] is False


def test_reroute_to_complaint_alerts_once(client: TestClient) -> None:
    ref = submit(client, COMPLAINT)  # already alerted by the pipeline
    csrf = as_desk(client)
    client.post(f"/api/enquiries/{ref}/route", json={"lane": "room_booking"}, headers=csrf)
    body = client.post(
        f"/api/enquiries/{ref}/route", json={"lane": "complaint"}, headers=csrf
    ).json()
    assert body["alert"]["reason"] == "complaint (keyword and model)"  # the original, no second
    other = submit(client, VILLA)  # no alert yet
    body = client.post(f"/api/enquiries/{other}/route", json={"lane": "complaint"}, headers=csrf)
    assert (body.json()["alert"]["reason"], body.json()["owner_team"]) == (
        "complaint (staff)",
        "gm",
    )
    assert client.get("/api/alerts").json()["open"] == 2


def test_reroute_validation(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    same = client.post(f"/api/enquiries/{ref}/route", json={"lane": "room_booking"}, headers=csrf)
    assert (same.status_code, same.json()["error"]["code"]) == (422, "no_change")
    bad = client.post(f"/api/enquiries/{ref}/route", json={"lane": "spam"}, headers=csrf)
    assert bad.status_code == 422


# ---------- reply, simulated (A-127) ----------


def test_reply_is_recorded_and_closes_the_enquiry(client: TestClient, clock: FakeClock) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    draft = get(client, ref)["draft_reply"]
    clock.now = START + timedelta(minutes=45)
    body = client.post(f"/api/enquiries/{ref}/reply", json={"text": draft}, headers=csrf).json()
    assert (body["status"], body["reply_text"], body["replied_by"]) == (
        "replied",
        draft,
        "Reservations Desk",
    )
    assert datetime.fromisoformat(body["replied_at"]) == START + timedelta(minutes=45)
    assert body["can_act"] is False and body["can_reclassify"] is False
    assert body["history"][-1]["action"] == "reply"
    assert body["history"][-1]["new"] == {"length": len(draft)}  # the text is not in the log
    counts = client.get("/api/enquiries").json()["counts"]
    assert (counts["room_booking"], counts["replied"]) == (0, 1)  # lane counts are open work


def test_staff_can_edit_the_draft_before_sending(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    text = "Dear Asha, yes we have a villa. See {our} website."  # other braces are fine
    body = client.post(f"/api/enquiries/{ref}/reply", json={"text": f"  {text}  "}, headers=csrf)
    assert body.json()["reply_text"] == text


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("   ", "empty_reply"),
        ("x" * 5_001, "reply_too_long"),
        ("Total is {price_total} for {dates}.", "unfilled_placeholder"),
    ],
)
def test_reply_validation(client: TestClient, text: str, code: str) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    response = client.post(f"/api/enquiries/{ref}/reply", json={"text": text}, headers=csrf)
    assert (response.status_code, response.json()["error"]["code"]) == (422, code)
    if code == "unfilled_placeholder":
        assert response.json()["error"]["details"] == {"placeholders": ["dates", "price_total"]}
    assert get(client, ref)["status"] == "classified"


def test_nothing_changes_after_a_reply(client: TestClient) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    client.post(f"/api/enquiries/{ref}/reply", json={"text": "Thank you."}, headers=csrf)
    attempts = [
        ("post", f"/api/enquiries/{ref}/reply", {"text": "Again"}),
        ("patch", f"/api/enquiries/{ref}", {"category": "wedding"}),
        ("post", f"/api/enquiries/{ref}/route", {"lane": "unsorted"}),
    ]
    for method, path, body in attempts:
        response = getattr(client, method)(path, json=body, headers=csrf)
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "already_replied",
        ), path
    retry = client.post(f"/api/enquiries/{ref}/classify", headers=csrf)
    assert retry.json()["error"]["code"] == "already_handled"


def test_pending_enquiry_cannot_be_replied_to(client: TestClient) -> None:
    csrf = as_desk(client)
    response = client.post("/api/enquiries/ENQ-4410/reply", json={"text": "Hi"}, headers=csrf)
    assert response.json()["error"]["code"] == "not_classified"


def test_reply_text_never_reaches_the_log(client: TestClient, caplog) -> None:
    ref = submit(client, VILLA)
    csrf = as_desk(client)
    with caplog.at_level(logging.DEBUG):
        client.post(
            f"/api/enquiries/{ref}/reply", json={"text": "Secret words here."}, headers=csrf
        )
    lines = " ".join(JsonFormatter().format(r) for r in caplog.records)
    assert "secret" not in lines.lower() and "asha" not in lines.lower()
    assert ref in lines  # the reference alone identifies it


def test_two_staff_replying_at_once_record_one_reply(
    client: TestClient, committed: sessionmaker[Session]
) -> None:
    ref = submit(client, VILLA)
    with committed() as s:
        desk, events = (
            s.scalar(select(User).where(User.email == email))
            for email in ("reservations@example.com", "events@example.com")
        )

    def task(actor: User, text: str):
        def run(session: Session) -> str:
            with session.begin():
                enquiry = get_enquiry(session, ref, lock=True)
                reply_to_enquiry(session, enquiry, actor=actor, text=text, now=START)
            return text

        return run

    outcomes = run_in_parallel(committed, [task(desk, "From desk"), task(events, "From events")])
    winners = [o.value for o in outcomes if o.error is None]
    losers = [o.error for o in outcomes if o.error is not None]
    assert len(winners) == 1 and len(losers) == 1
    assert isinstance(losers[0], EnquiryActionRefused) and losers[0].code == "already_replied"
    with committed() as s:
        enquiry = s.scalar(select(Enquiry).where(Enquiry.reference == ref))
        assert enquiry.reply_text == winners[0]


# ---------- GM alerts (A-129) ----------


def test_alert_list_and_acknowledgement(client: TestClient, clock: FakeClock) -> None:
    ref = submit(client, COMPLAINT)
    as_desk(client)
    listed = client.get("/api/alerts").json()
    assert listed["open"] == 1
    [alert] = listed["items"]
    assert (alert["reference"], alert["lane"], alert["acknowledged_at"]) == (ref, "complaint", None)
    desk = client.post(f"/api/alerts/{alert['id']}/ack", headers=as_desk(client))
    assert desk.status_code == 403  # only the GM acknowledges

    gm = as_gm(client)
    clock.now = START + timedelta(minutes=5)
    acked = client.post(f"/api/alerts/{alert['id']}/ack", headers=gm).json()
    assert acked["acknowledged_by"] == "General Manager"
    assert client.get("/api/alerts").json()["open"] == 0
    assert client.get("/api/alerts", params={"open_only": True}).json()["items"] == []
    assert get(client, ref)["alert"]["acknowledged_by"] == "General Manager"
    again = client.post(f"/api/alerts/{alert['id']}/ack", headers=gm)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_acknowledged")
    missing = client.post("/api/alerts/999999/ack", headers=gm)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "alert_not_found")


def test_open_alerts_are_listed_first(client: TestClient, clock: FakeClock) -> None:
    first = submit(client, COMPLAINT)
    clock.now = START + timedelta(minutes=1)
    second = submit(client, "Staff were rude and the food was cold.")
    gm = as_gm(client)
    newest = client.get("/api/alerts").json()["items"][0]
    client.post(f"/api/alerts/{newest['id']}/ack", headers=gm)
    assert [i["reference"] for i in client.get("/api/alerts").json()["items"]] == [first, second]


# ---------- metrics (A-128) ----------


def test_metrics_count_from_the_database(client: TestClient, clock: FakeClock) -> None:
    villa = submit(client, VILLA)
    submit(client, COMPLAINT)
    submit(client, "Do you sell your coffee beans online?")  # the pipeline sends it to Unsorted
    client.app.state.model_backend = StubLLMClassifier("timeout")
    submit(client, "Planning our wedding in February for 150 guests.")  # keyword fallback
    csrf = as_desk(client)
    client.patch(f"/api/enquiries/{villa}", json={"category": "corporate_offsite"}, headers=csrf)
    complaint = client.get("/api/enquiries", params={"lane": "complaint"}).json()["items"][0]
    client.patch(  # a field correction is not a category correction
        f"/api/enquiries/{complaint['reference']}", json={"fields": {"guests": 2}}, headers=csrf
    )
    clock.now = START + timedelta(minutes=90)
    client.post(f"/api/enquiries/{villa}/reply", json={"text": "Thank you."}, headers=csrf)

    m = client.get("/api/enquiries/metrics").json()
    assert (m["date_from"], m["date_to"]) == ("2026-10-07", "2026-11-05")  # last 30 days
    assert (m["received"], m["pending"], m["failed"], m["replied"]) == (SEEDED + 4, SEEDED, 0, 1)
    assert m["by_lane"] == {
        "room_booking": 0,
        "wedding": 1,
        "corporate_offsite": 1,
        "complaint": 1,
        "unsorted": 1,
    }
    assert m["sent_to_unsorted"] == {"count": 1, "out_of": 4, "value": 0.25}
    assert m["fallback"] == {"count": 1, "out_of": 4, "value": 0.25}
    assert m["category_corrected"] == {"count": 1, "out_of": 4, "value": 0.25}
    assert m["median_minutes_to_reply"] == 90.0


def test_metrics_for_an_empty_range(client: TestClient) -> None:
    as_desk(client)
    m = client.get("/api/enquiries/metrics", params={"from": "2026-01-01", "to": "2026-01-31"})
    body = m.json()
    assert body["received"] == 0 and body["median_minutes_to_reply"] is None
    assert body["fallback"] == {"count": 0, "out_of": 0, "value": None}


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-11-05", "to": "2026-11-01"}, {"from": "2025-01-01", "to": "2026-11-05"}],
)
def test_metrics_range_validation(client: TestClient, params: dict) -> None:
    as_desk(client)
    response = client.get("/api/enquiries/metrics", params=params)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_range")


# ---------- access ----------


def test_actions_need_staff(client: TestClient) -> None:
    ref = submit(client, COMPLAINT)
    routes = [
        ("patch", f"/api/enquiries/{ref}", {"category": "wedding"}),
        ("post", f"/api/enquiries/{ref}/route", {"lane": "unsorted"}),
        ("post", f"/api/enquiries/{ref}/reply", {"text": "Hi"}),
        ("get", "/api/enquiries/metrics", None),
        ("get", "/api/alerts", None),
        ("post", "/api/alerts/1/ack", None),
    ]

    def call(method, path, body, headers=None):
        kwargs = {"headers": headers or {}}
        if body is not None:
            kwargs["json"] = body
        return getattr(client, method)(path, **kwargs)

    client.cookies.clear()
    for method, path, body in routes:
        assert call(method, path, body).status_code == 401, path
    guest = login(client, "guest@example.com", "Guest-Demo-2026")
    for method, path, body in routes:
        assert call(method, path, body, guest).status_code == 403, path


def test_events_team_can_act_on_any_lane(client: TestClient) -> None:
    ref = submit(client, VILLA)  # a reservations lane enquiry
    csrf = login(client, "events@example.com", "Events-Demo-2026")
    response = client.post(f"/api/enquiries/{ref}/reply", json={"text": "Thank you."}, headers=csrf)
    assert response.json()["replied_by"] == "Events Team"


def test_actions_need_the_csrf_token(client: TestClient) -> None:
    ref = submit(client, VILLA)
    as_desk(client)
    response = client.patch(f"/api/enquiries/{ref}", json={"category": "wedding"})
    assert (response.status_code, response.json()["error"]["code"]) == (403, "csrf_failed")


def test_database_refuses_a_half_recorded_reply(committed: sessionmaker[Session], client) -> None:
    ref = submit(client, VILLA)
    for change in (
        "status = 'replied'",  # no reply text, time or sender
        "reply_text = 'Hi'",  # text without the rest
    ):
        with committed() as s:
            with pytest.raises(IntegrityError):
                with s.begin():
                    s.execute(
                        text(f"UPDATE enquiries SET {change} WHERE reference = :r"), {"r": ref}
                    )

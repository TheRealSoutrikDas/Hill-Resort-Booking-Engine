"""Scoring and report for the evaluation command (A-138 to A-142, D-46). No database."""

from dataclasses import replace
from datetime import date

import pytest

from app.classifiers.fields import ExtractedFields
from app.classifiers.keyword import KeywordClassifier
from app.enquiry_samples import SampleEnquiry, load_sample_enquiries
from app.eval_enquiries import evaluate, lane_ok, render, score
from app.services.enquiry_pipeline import propose
from tests.fakes import StubLLMClassifier

KEYWORD = KeywordClassifier()
SAMPLES = load_sample_enquiries()


def sample(**overrides) -> SampleEnquiry:
    base = {
        "id": "ENQ-9001",
        "source": "invented",
        "message": "Is a villa free 14-16 Nov for 2 adults and a child?",
        "expected_category": "room_booking",
        "expected_lane": "auto",
        "must_alert_gm": False,
        "expected_fields": {"check_in": "2026-11-14", "check_out": "2026-11-16", "guests": 3},
        "tags": ["clean"],
    }
    return SampleEnquiry.model_validate(base | overrides)


def proposal_for(s: SampleEnquiry, model=KEYWORD):
    return propose(s.message, date(2026, 11, 5), keyword=KEYWORD, model=model, threshold=0.7)


# ---------- lanes (A-139) ----------


@pytest.mark.parametrize(
    ("expected_lane", "lane", "ok"),
    [
        ("auto", "room_booking", True),
        ("auto", "unsorted", False),
        ("auto", "wedding", False),
        ("unsorted", "unsorted", True),
        ("unsorted", "room_booking", False),
        ("either", "unsorted", True),
        ("either", "room_booking", True),
    ],
)
def test_lane_rules(expected_lane: str, lane: str, ok: bool) -> None:
    assert lane_ok(sample(expected_lane=expected_lane), lane) is ok


# ---------- fields ----------


def test_fields_right_wrong_missing_and_extra() -> None:
    s = sample(expected_fields={"check_in": "2026-11-14", "guests": 5, "budget_inr": 9000})
    p = proposal_for(s)
    got = replace(
        p,
        final=replace(
            p.final,
            fields=ExtractedFields(check_in=date(2026, 11, 14), guests=3, nights=2),
        ),
    )
    result = score(s, got)
    assert result.fields_right == ("check_in",)
    assert result.fields_wrong == ("guests",)
    assert result.fields_missing == ("budget_inr",)
    assert result.fields_extra == ("nights",)  # shown, not counted against


# ---------- categories and alerts ----------


def test_category_is_an_exact_match_with_the_second_category_noted() -> None:
    s = sample(expected_category="wedding", secondary_category="room_booking")
    result = score(s, proposal_for(s))
    assert (result.category_ok, result.secondary_ok) == (False, True)


def test_missed_and_false_alerts() -> None:
    complaint = sample(
        message="The room was dirty.", expected_category="complaint", must_alert_gm=True
    )
    assert score(complaint, proposal_for(complaint)).alert_missed is False
    no_signal = replace(proposal_for(complaint), complaint_by=[])
    assert score(complaint, no_signal).alert_missed is True
    calm = sample()
    alerted = replace(proposal_for(calm), complaint_by=["model"])
    assert score(calm, alerted).false_alert is True


# ---------- a run and the report ----------


def test_keyword_run_on_the_sample_file() -> None:
    result = evaluate(SAMPLES, keyword=KEYWORD, model=KEYWORD, threshold=0.7, label="keyword")
    assert len(result.scores) == 27 and result.alerts_missed == []
    assert result.count(lambda s: s.must_alert) == 4


def test_model_calls_are_paced_but_keyword_runs_are_not() -> None:
    pauses: list[float] = []
    evaluate(
        SAMPLES,
        keyword=KEYWORD,
        model=KEYWORD,
        threshold=0.7,
        label="k",
        delay_s=4.5,
        sleep=pauses.append,
    )
    assert pauses == []
    evaluate(
        SAMPLES,
        keyword=KEYWORD,
        model=StubLLMClassifier(),
        threshold=0.7,
        label="stub",
        delay_s=4.5,
        sleep=pauses.append,
    )
    assert pauses == [4.5] * 26  # between calls, not before the first


def test_fallbacks_are_counted_and_keywords_still_alert() -> None:
    result = evaluate(
        SAMPLES, keyword=KEYWORD, model=StubLLMClassifier("timeout"), threshold=0.7, label="stub"
    )
    assert result.count(lambda s: s.is_fallback) == 27
    assert result.alerts_missed == []


def test_report_has_ids_but_never_message_text() -> None:
    runs = [
        evaluate(SAMPLES, keyword=KEYWORD, model=KEYWORD, threshold=0.7, label="keyword"),
        evaluate(SAMPLES, keyword=KEYWORD, model=StubLLMClassifier(), threshold=0.7, label="stub"),
    ]
    report = render(runs, SAMPLES, "data/sample_enquiries.json")
    for e in SAMPLES.enquiries:
        assert e.id in report
        if len(e.message) >= 12:  # "hi" appears inside ordinary words
            assert e.message not in report
            assert e.message[:30] not in report
    assert "| Category right | 27/27 (100%) |" in report
    assert "in-sample" in report  # the keyword figures are labelled honestly (A-144)
    assert "| Gate (no missed alert) | pass | pass |" in report


def test_report_without_a_keyword_run_has_no_in_sample_note() -> None:
    run = evaluate(SAMPLES, keyword=KEYWORD, model=StubLLMClassifier(), threshold=0.7, label="stub")
    assert "in-sample" not in render([run], SAMPLES, "x.json")

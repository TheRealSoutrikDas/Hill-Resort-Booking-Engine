"""Lane decision rules (A-115 to A-117) and draft formatting."""

from dataclasses import replace
from datetime import date

import pytest

from app.classifiers.base import OWNER_FOR, ClassificationResult
from app.classifiers.fields import ExtractedFields
from app.classifiers.templates import DRAFTS
from app.services.enquiry_drafts import format_dates, format_inr, format_month
from app.services.enquiry_lanes import decide_lane

DATED = ExtractedFields(
    check_in=date(2026, 11, 14), check_out=date(2026, 11, 16), event_month="2026-11"
)


def result(
    category: str = "room_booking",
    confidence: float = 0.9,
    fields: ExtractedFields = DATED,
    backend: str = "stub",
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        fields=fields,
        owner=OWNER_FOR[category],
        confidence=confidence,
        draft_template=DRAFTS[category],
        backend=backend,
    )


KEYWORD = result(backend="keyword")


def lane(final, keyword=KEYWORD, model="same", invalid=False, threshold=0.7):
    model = final if model == "same" else model
    return decide_lane(final, keyword, model, invalid_output=invalid, threshold=threshold)


def test_confident_agreeing_result_goes_to_its_lane() -> None:
    assert lane(result()) == ("room_booking", [])


@pytest.mark.parametrize(("confidence", "expected"), [(0.7, "room_booking"), (0.69, "unsorted")])
def test_threshold_boundary(confidence: float, expected: str) -> None:
    assert lane(result(confidence=confidence))[0] == expected


def test_invalid_output_goes_to_unsorted() -> None:
    assert lane(KEYWORD, model=None, invalid=True) == ("unsorted", ["invalid_output"])


def test_disagreement_goes_to_unsorted() -> None:
    assert lane(result("wedding", fields=DATED)) == ("unsorted", ["disagreement"])


def test_keyword_no_match_is_not_disagreement() -> None:
    no_opinion = result("other", confidence=0.3, backend="keyword")
    assert lane(result("wedding"), keyword=no_opinion) == ("wedding", [])


def test_category_other_goes_to_unsorted() -> None:
    other = result("other", confidence=0.95)
    assert lane(other, keyword=replace(other, backend="keyword"))[1] == ["category_other"]


@pytest.mark.parametrize(
    ("category", "fields", "ok"),
    [
        ("room_booking", ExtractedFields(guests=2), False),
        ("room_booking", ExtractedFields(check_in=date(2026, 12, 31)), True),
        ("wedding", ExtractedFields(guests=200), False),
        ("wedding", ExtractedFields(event_month="2027-02"), True),
        ("corporate_offsite", ExtractedFields(check_in=date(2027, 3, 10)), True),
        ("complaint", ExtractedFields(), True),
    ],
)
def test_required_fields(category: str, fields: ExtractedFields, ok: bool) -> None:
    final = result(category, fields=fields)
    reasons = lane(final, keyword=replace(final, backend="keyword"))[1]
    assert ("missing_fields" not in reasons) == ok


def test_fallback_has_no_model_so_no_disagreement() -> None:
    assert lane(KEYWORD, model=None) == ("room_booking", [])


def test_reasons_accumulate() -> None:
    weak_other = result("other", confidence=0.2)
    assert lane(weak_other, invalid=True)[1] == [
        "invalid_output",
        "low_confidence",
        "disagreement",
        "category_other",
    ]


# ---------- formatting ----------


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "Rs 0"),
        (600_000, "Rs 6,000"),
        (2_803_680, "Rs 28,036.80"),
        (15_000_000, "Rs 1,50,000"),
        (15_000_000_000, "Rs 15,00,00,000"),
    ],
)
def test_indian_grouping(paise: int, text: str) -> None:
    assert format_inr(paise) == text


def test_date_and_month_formats() -> None:
    assert format_dates(date(2026, 12, 26), date(2027, 1, 1)) == "26 Dec 2026 to 1 Jan 2027"
    assert format_month("2027-02") == "February 2027"

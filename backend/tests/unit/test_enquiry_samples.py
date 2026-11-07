import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.enquiry_samples import SampleEnquiryFile, load_sample_enquiries

# The client's own samples, copied from the brief. If the file and this table ever
# differ, the brief is correct and the file must be fixed.
BRIEF_TABLE = {
    "ENQ-4410": (
        "Venue for my sister's wedding in Feb 2027, about 250 guests, 2 nights",
        "wedding",
    ),
    "ENQ-4411": ("Is a villa free 14-16 Nov for 2 adults and a child?", "room_booking"),
    "ENQ-4412": ("Team of 45 wants a January offsite with a conference hall", "corporate_offsite"),
}


@pytest.fixture(scope="module")
def samples() -> SampleEnquiryFile:
    return load_sample_enquiries()


def test_file_loads_with_all_enquiries(samples: SampleEnquiryFile) -> None:
    assert len(samples.enquiries) == 27


def test_brief_samples_match_the_brief_exactly(samples: SampleEnquiryFile) -> None:
    by_id = {e.id: e for e in samples.enquiries}
    for enquiry_id, (message, category) in BRIEF_TABLE.items():
        assert by_id[enquiry_id].source == "brief"
        assert by_id[enquiry_id].message == message
        assert by_id[enquiry_id].expected_category == category
    assert {e.id for e in samples.enquiries if e.source == "brief"} == set(BRIEF_TABLE)


def test_every_category_and_special_case_is_covered(samples: SampleEnquiryFile) -> None:
    categories = {e.expected_category for e in samples.enquiries}
    assert categories == {"room_booking", "wedding", "corporate_offsite", "complaint", "other"}
    assert any(e.expected_lane == "unsorted" for e in samples.enquiries)
    assert any(e.must_alert_gm for e in samples.enquiries)
    assert any("prompt_injection" in e.tags for e in samples.enquiries)


def test_engagement_enquiry_has_event_month(samples: SampleEnquiryFile) -> None:
    enquiry = next(e for e in samples.enquiries if e.id == "ENQ-4422")
    assert enquiry.expected_fields.event_month == "2027-01"


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "samples.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal(**enquiry_overrides: object) -> dict:
    enquiry = {
        "id": "ENQ-9000",
        "source": "invented",
        "message": "Villa for two?",
        "expected_category": "room_booking",
        "expected_lane": "auto",
        "must_alert_gm": False,
        "expected_fields": {},
    }
    enquiry.update(enquiry_overrides)
    return {"_readme": "x", "default_received_on": "2026-11-05", "enquiries": [enquiry]}


def test_minimal_valid_file_loads(tmp_path: Path) -> None:
    assert len(load_sample_enquiries(_write(tmp_path, _minimal())).enquiries) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_category": "spam"},
        {"message": "   "},
        {"expected_fields": {"guest": 2}},  # misspelt field name
        {"expected_fields": {"event_month": "2027-13"}},
        {"id": "4410"},
        {"surprise": True},
    ],
)
def test_invalid_entries_fail_loudly(tmp_path: Path, overrides: dict) -> None:
    with pytest.raises(ValidationError):
        load_sample_enquiries(_write(tmp_path, _minimal(**overrides)))


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    data = _minimal()
    data["enquiries"].append(dict(data["enquiries"][0]))
    with pytest.raises(ValidationError):
        load_sample_enquiries(_write(tmp_path, data))

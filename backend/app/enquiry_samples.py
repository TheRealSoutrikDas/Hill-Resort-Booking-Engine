"""Loader for backend/data/sample_enquiries.json.

The file is the evaluation set for the enquiry classifier and the source of seeded
enquiries. ENQ-4410 to ENQ-4412 are the client's own samples; the rest are invented
(A-32). The loader validates the whole file, so a typo fails loudly instead of skewing
the evaluation.
"""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import EnquiryCategory

SAMPLE_ENQUIRIES_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_enquiries.json"


class ExpectedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_in: date | None = None
    check_out: date | None = None
    event_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    guests: int | None = Field(default=None, gt=0)
    nights: int | None = Field(default=None, gt=0)
    budget_inr: int | None = Field(default=None, gt=0)


class SampleEnquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ENQ-[0-9]{4,}$")
    source: Literal["brief", "invented"]
    message: str
    expected_category: EnquiryCategory
    # auto: routed to its category's lane; unsorted: must land in Unsorted; either: both fine.
    expected_lane: Literal["auto", "unsorted", "either"]
    must_alert_gm: bool
    expected_fields: ExpectedFields
    secondary_category: EnquiryCategory | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # Empty messages are a validation test case, never sample data.
        if not value.strip():
            raise ValueError("sample message must not be blank")
        return value


class SampleEnquiryFile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    readme: str = Field(alias="_readme")
    default_received_on: date
    enquiries: list[SampleEnquiry]

    @field_validator("enquiries")
    @classmethod
    def _unique_ids(cls, value: list[SampleEnquiry]) -> list[SampleEnquiry]:
        ids = [e.id for e in value]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate enquiry ids: {duplicates}")
        return value


def load_sample_enquiries(path: Path = SAMPLE_ENQUIRIES_PATH) -> SampleEnquiryFile:
    return SampleEnquiryFile.model_validate_json(path.read_text(encoding="utf-8"))

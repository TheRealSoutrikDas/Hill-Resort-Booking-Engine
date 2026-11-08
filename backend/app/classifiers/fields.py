"""Fields extracted from an enquiry, checked in code (brief: "the model's fields are
checked, not trusted"). Shared by the keyword and LLM backends."""

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_DAYS_AHEAD = 730  # two years (A-108)


class ExtractedFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_in: date | None = None
    check_out: date | None = None
    event_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    guests: int | None = Field(default=None, ge=1, le=1_000)
    nights: int | None = Field(default=None, ge=1, le=60)
    budget_inr: int | None = Field(default=None, ge=1, le=1_000_000_000)
    # A hint for the draft's {room_type}, as a room type code (A-113).
    room_type: str | None = Field(default=None, pattern=r"^[A-Z]{2,8}$")

    @model_validator(mode="after")
    def _stay_order(self) -> "ExtractedFields":
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


def keep_plausible(fields: ExtractedFields, received_on: date) -> ExtractedFields:
    """Drop dates outside [received_on - 1 day, received_on + 2 years], and a check-out
    with no check-in. Implausible values are dropped, never guessed (brief)."""
    earliest = received_on - timedelta(days=1)
    latest = received_on + timedelta(days=MAX_DAYS_AHEAD)
    data = fields.model_dump()
    for key in ("check_in", "check_out"):
        if data[key] is not None and not earliest <= data[key] <= latest:
            data[key] = None
    if data["check_in"] is None:
        data["check_out"] = None
    if data["event_month"] is not None:
        year, month = (int(p) for p in data["event_month"].split("-"))
        first = date(year, month, 1)
        if not date(earliest.year, earliest.month, 1) <= first <= latest:
            data["event_month"] = None
    return ExtractedFields(**data)

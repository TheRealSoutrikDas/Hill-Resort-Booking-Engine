"""The enquiry classifier interface (brief, D-41).

Every backend (keyword now, LLM in step 22) implements `classify(message, received_on)`
and returns a `ClassificationResult`. The model proposes; code decides: lanes, prices,
alerts and sending are never taken from a result's text (step 20).
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.classifiers.fields import ExtractedFields
from app.db.models.enums import EnquiryCategory, OwnerTeam

# Owner team per category (A-109). `other` has no owner: it goes to Unsorted.
OWNER_FOR: dict[str, str | None] = {
    EnquiryCategory.ROOM_BOOKING: OwnerTeam.RESERVATIONS,
    EnquiryCategory.WEDDING: OwnerTeam.EVENTS,
    EnquiryCategory.CORPORATE_OFFSITE: OwnerTeam.EVENTS,
    EnquiryCategory.COMPLAINT: OwnerTeam.GM,
    EnquiryCategory.OTHER: None,
}


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    fields: ExtractedFields
    owner: str | None
    confidence: float  # 0 to 1
    draft_template: str  # plain text with {placeholders}; prices are filled in code
    backend: str
    is_fallback: bool = False
    error: str | None = None
    # True when complaint words were seen, even if another category won. The GM alert
    # uses this, so it never depends on the model being available (A-110).
    complaint_signal: bool = False
    # What the backend actually returned, kept for comparison when staff correct it.
    raw_output: dict | None = None


class EnquiryClassifier(Protocol):
    name: str

    def classify(self, message: str, received_on: date) -> ClassificationResult: ...

"""Lane decision, in code (brief: "Decide the lane in code"; A-115 to A-117, D-42).

The model proposes a category; this function decides where the enquiry goes. It is
pure: same inputs, same lane, so every rule has its own test.
"""

from app.classifiers.base import ClassificationResult
from app.classifiers.fields import ExtractedFields
from app.classifiers.keyword import CONFIDENCE_NONE
from app.db.models.enums import EnquiryCategory, Lane

LANE_FOR = {
    EnquiryCategory.ROOM_BOOKING: Lane.ROOM_BOOKING,
    EnquiryCategory.WEDDING: Lane.WEDDING,
    EnquiryCategory.CORPORATE_OFFSITE: Lane.CORPORATE_OFFSITE,
    EnquiryCategory.COMPLAINT: Lane.COMPLAINT,
    EnquiryCategory.OTHER: Lane.UNSORTED,
}

# Reasons an enquiry goes to Unsorted (stored in enquiries.lane_reasons).
INVALID_OUTPUT = "invalid_output"
LOW_CONFIDENCE = "low_confidence"
DISAGREEMENT = "disagreement"
CATEGORY_OTHER = "category_other"
MISSING_FIELDS = "missing_fields"


def has_required_fields(category: str, fields: ExtractedFields) -> bool:
    """A-116: a room booking needs a check-in date; a wedding or offsite needs an event
    month or a date; complaints and other need nothing."""
    if category == EnquiryCategory.ROOM_BOOKING:
        return fields.check_in is not None
    if category in (EnquiryCategory.WEDDING, EnquiryCategory.CORPORATE_OFFSITE):
        return fields.event_month is not None or fields.check_in is not None
    return True


def decide_lane(
    final: ClassificationResult,
    keyword: ClassificationResult,
    model: ClassificationResult | None,
    *,
    invalid_output: bool,
    threshold: float,
) -> tuple[str, list[str]]:
    """(lane, reasons). Any reason sends the enquiry to Unsorted, which the GM sees."""
    reasons = []
    if invalid_output:
        reasons.append(INVALID_OUTPUT)
    if final.confidence < threshold:
        reasons.append(LOW_CONFIDENCE)
    # A-117: the keyword backend's no-match "other" is no opinion, not disagreement.
    keyword_has_opinion = keyword.confidence > CONFIDENCE_NONE
    if model is not None and keyword_has_opinion and model.category != keyword.category:
        reasons.append(DISAGREEMENT)
    if final.category == EnquiryCategory.OTHER:
        reasons.append(CATEGORY_OTHER)
    if not has_required_fields(final.category, final.fields):
        reasons.append(MISSING_FIELDS)
    return (Lane.UNSORTED if reasons else LANE_FOR[final.category]), reasons

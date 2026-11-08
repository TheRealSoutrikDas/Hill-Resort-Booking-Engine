"""The keyword classifier: always available, and the fallback when the model is not
(brief, A-109 to A-111, D-41).

It always performs the complaint check: `complaint_signal` is set by problem words in
English, Hinglish, Hindi and Kannada, and the verb "complain", but not the noun
"complaint" alone, so a message that only asks to be "marked as a complaint" does not
alert the GM, and no phrase added
to a real complaint can switch the signal off (A-110).
"""

import re
from datetime import date

from app.classifiers.base import OWNER_FOR, ClassificationResult
from app.classifiers.extract import extract_fields
from app.classifiers.templates import DRAFTS
from app.db.models.enums import EnquiryCategory

# Latin keywords match whole words; Indic keywords match as substrings, because Python's
# word boundaries do not work with Devanagari and Kannada vowel signs.
KEYWORDS: dict[str, tuple[str, ...]] = {
    EnquiryCategory.ROOM_BOOKING: (
        "room",
        "cottage",
        "cottages",
        "rooms",
        "villa",
        "villas",
        "suite",
        "stay",
        "night",
        "nights",
        "availability",
        "available",
        "free",
        "rate",
        "rates",
        "price",
        "tariff",
        "book",
        "booking",
        "check-in",
        "check in",
        "kamra",
        "chahiye",
        "कमरा",
        "कमरे",
        "ಕೋಣೆ",
    ),
    EnquiryCategory.WEDDING: (
        "wedding",
        "marriage",
        "shaadi",
        "reception",
        "engagement",
        "sangeet",
        "mehendi",
        "haldi",
        "bride",
        "groom",
        "lawn",
        "ceremony",
        "शादी",
        "ಮದುವೆ",
    ),
    EnquiryCategory.CORPORATE_OFFSITE: (
        "team",
        "offsite",
        "off-site",
        "retreat",
        "conference",
        "workshop",
        "training",
        "corporate",
        "company",
        "startup",
        "outing",
        "leadership",
        "projector",
        "seminar",
        "meeting",
    ),
}

COMPLAINT_WORDS: tuple[str, ...] = (
    "complain",
    "complained",
    "complaining",
    "dirty",
    "filthy",
    "unclean",
    "stained",
    "noise",
    "not working",
    "wasn't working",
    "didn't work",
    "broken",
    "leak",
    "leaked",
    "leaking",
    "rude",
    "disappointed",
    "disappointing",
    "terrible",
    "worst",
    "awful",
    "unacceptable",
    "charged twice",
    "double charged",
    "overcharged",
    "refund",
    "smell",
    "smelly",
    "cockroach",
    "bugs",
    "noisy",
    "nobody answered",
    "no one answered",
    "poor service",
    "bad service",
    "ganda",
    "gandi",
    "kharab",
    "bekar",
    "bakwas",
    "गंदगी",
    "गंदा",
    "गंदी",
    "खराब",
    "कोई मदद नहीं",
    "ಕೊಳಕು",
    "ಕೆಟ್ಟ",
    "ಸಹಾಯ ಮಾಡಲಿಲ್ಲ",
)

CONFIDENCE_CLEAR = 0.9
CONFIDENCE_COMPETING = 0.6
CONFIDENCE_NONE = 0.3
_EVENTS = (EnquiryCategory.WEDDING, EnquiryCategory.CORPORATE_OFFSITE)


def _hits(text: str, words: tuple[str, ...]) -> int:
    count = 0
    for word in words:
        if word.isascii():
            count += bool(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text))
        else:
            count += word in text
    return count


def complaint_signal(message: str) -> bool:
    return _hits(message.lower(), COMPLAINT_WORDS) > 0


def categorise(message: str) -> tuple[str, float, bool]:
    """(category, confidence, complaint_signal)."""
    text = message.lower()
    complaint = _hits(text, COMPLAINT_WORDS) > 0
    if complaint:  # a complaint inside a booking request is still a complaint (A-110)
        return EnquiryCategory.COMPLAINT, CONFIDENCE_CLEAR, True
    scores = {category: _hits(text, words) for category, words in KEYWORDS.items()}
    events = {c: scores[c] for c in _EVENTS if scores[c] > 0}
    if events:
        # Weddings and offsites naturally mention rooms and nights, so room words
        # count as part of the event.
        best = max(events, key=lambda c: (events[c], c == EnquiryCategory.WEDDING))
        confidence = CONFIDENCE_COMPETING if len(events) > 1 else CONFIDENCE_CLEAR
        return best, confidence, False
    if scores[EnquiryCategory.ROOM_BOOKING] > 0:
        return EnquiryCategory.ROOM_BOOKING, CONFIDENCE_CLEAR, False
    return EnquiryCategory.OTHER, CONFIDENCE_NONE, False


class KeywordClassifier:
    name = "keyword"

    def classify(self, message: str, received_on: date) -> ClassificationResult:
        category, confidence, complaint = categorise(message)
        return ClassificationResult(
            category=category,
            fields=extract_fields(message, received_on),
            owner=OWNER_FOR[category],
            confidence=confidence,
            draft_template=DRAFTS[category],
            backend=self.name,
            complaint_signal=complaint,
        )

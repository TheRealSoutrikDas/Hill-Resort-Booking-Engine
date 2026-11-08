"""The enquiry pipeline (brief: "Pipeline (services/enquiry_pipeline.py)"; D-42).

1. Validate and SAVE the enquiry as pending before any model call.
2. Run the keyword classifier (it always performs the complaint check).
3. Ask the model backend, outside any database transaction. Timeout or provider error:
   use the keyword result, marked as a fallback. Output still invalid after one retry:
   keyword result, and Unsorted.
4. Decide the lane in code.
5. Raise a GM alert for any complaint, whatever the lane or confidence.
6. Fill the draft's placeholders from the rate table in code.
7. Store everything. A crash after step 1 leaves the enquiry "failed", never lost.

Like checkout, these functions run their own short transactions, so they take a
session factory. Only the message text is ever given to a model backend.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.classifiers.base import ClassificationResult, EnquiryClassifier
from app.classifiers.errors import ClassifierError, InvalidModelOutput
from app.core.config import Settings
from app.core.logging import exception_fields
from app.db.models import Enquiry, GmAlert, User
from app.db.models.enquiry import ENQUIRY_REFERENCE_SEQUENCE
from app.db.models.enums import EnquiryCategory, EnquiryStatus, OwnerTeam
from app.services.enquiry_drafts import build_draft
from app.services.enquiry_lanes import decide_lane
from app.services.errors import InvalidEnquiry
from app.services.quotes import HoldRules
from app.services.validation import (
    is_valid_email,
    is_valid_name,
    is_valid_phone,
    normalize_email,
    normalize_name,
    normalize_phone,
)

logger = logging.getLogger("app.enquiries")

ENQUIRY_CONSENT_VERSION = "enquiry-v1"
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PipelineOutcome:
    """The brief's classification response: category, fields, owner, confidence,
    backend, is_fallback, lane, gm_alert (plus identity and status)."""

    enquiry_id: int
    reference: str
    status: str
    category: str | None
    fields: dict
    owner: str | None
    confidence: float | None
    backend: str | None
    is_fallback: bool
    lane: str | None
    gm_alert: bool
    error: str | None


def _result_dict(result: ClassificationResult) -> dict:
    return {
        "category": result.category,
        "confidence": result.confidence,
        "owner": result.owner,
        "complaint_signal": result.complaint_signal,
        "fields": result.fields.model_dump(mode="json", exclude_none=True),
    }


def _outcome(session: Session, enquiry: Enquiry) -> PipelineOutcome:
    has_alert = (
        session.scalar(
            select(func.count()).select_from(GmAlert).where(GmAlert.enquiry_id == enquiry.id)
        )
        > 0
    )
    return PipelineOutcome(
        enquiry_id=enquiry.id,
        reference=enquiry.reference,
        status=enquiry.status,
        category=enquiry.category,
        fields=enquiry.fields or {},
        owner=enquiry.owner_team,
        confidence=float(enquiry.confidence) if enquiry.confidence is not None else None,
        backend=enquiry.backend,
        is_fallback=enquiry.is_fallback,
        lane=enquiry.lane,
        gm_alert=has_alert,
        error=enquiry.error,
    )


# ---------- step 1: validate and save ----------


def save_enquiry(
    factory: sessionmaker[Session],
    *,
    message: str,
    contact_name: str,
    contact_email: str | None,
    contact_phone: str | None,
    consent: bool,
    settings: Settings,
    now: datetime,
    channel: str = "web",
) -> int:
    """Validate the form (A-114) and save the enquiry as pending. Returns its id."""
    message = message.strip()
    if not message:
        raise InvalidEnquiry("empty_message", "Please write your message.")
    if len(message) > settings.enquiry_max_length:
        raise InvalidEnquiry(
            "message_too_long",
            f"Please keep your message under {settings.enquiry_max_length} characters.",
        )
    if not consent:
        raise InvalidEnquiry("consent_required", "Please agree to how we use your details.")
    name = normalize_name(contact_name)
    if not is_valid_name(name):
        raise InvalidEnquiry("invalid_name", "Please tell us your name.")
    email = normalize_email(contact_email) if contact_email and contact_email.strip() else None
    phone = normalize_phone(contact_phone) if contact_phone and contact_phone.strip() else None
    if email is None and phone is None:
        raise InvalidEnquiry(
            "contact_required", "Please give an email or a phone number so we can reply."
        )
    if email is not None and not is_valid_email(email):
        raise InvalidEnquiry("invalid_email", "Please check your email address.")
    if phone is not None and not is_valid_phone(phone):
        raise InvalidEnquiry("invalid_phone", "Please check your phone number.")

    with factory() as session, session.begin():
        enquiry = Enquiry(
            reference=func.concat("ENQ-", ENQUIRY_REFERENCE_SEQUENCE.next_value()),
            channel=channel,
            message=message,
            contact_name=name,
            contact_email=email,
            contact_phone=phone,
            consent_at=now,
            consent_version=ENQUIRY_CONSENT_VERSION,
            received_at=now,
            status=EnquiryStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        session.add(enquiry)
        session.flush()
        return enquiry.id


# ---------- steps 2 to 7 ----------


def _ask_model(
    model: EnquiryClassifier, message: str, received_on
) -> tuple[ClassificationResult | None, str | None, bool]:
    """(result, error code, output was invalid). Never raises: every failure falls back."""
    try:
        return model.classify(message, received_on), None, False
    except InvalidModelOutput as exc:
        return None, exc.code, True
    except ClassifierError as exc:
        return None, exc.code, False
    except Exception as exc:  # an unexpected provider library error is still a fallback
        logger.warning("model backend raised unexpectedly", extra=exception_fields(exc))
        return None, "provider_error", False


@dataclass(frozen=True)
class Proposal:
    """Pipeline steps 2 to 5 for one message, before anything is stored. The evaluation
    command uses the same function, so it measures the real rules (D-46)."""

    keyword: ClassificationResult
    model: ClassificationResult | None
    error: str | None
    invalid_output: bool
    final: ClassificationResult
    is_fallback: bool
    lane: str
    reasons: list[str]
    complaint_by: list[str]  # which checks saw a complaint; non-empty means a GM alert


def complaint_sources(
    keyword_result: ClassificationResult, model_result: ClassificationResult | None
) -> list[str]:
    """Step 5: the GM alert never depends on the model alone (A-110)."""
    seen = (
        ("keyword", keyword_result.complaint_signal),
        ("model", model_result is not None and model_result.category == EnquiryCategory.COMPLAINT),
    )
    return [source for source, hit in seen if hit]


def propose(
    message: str,
    received_on,
    *,
    keyword: EnquiryClassifier,
    model: EnquiryClassifier,
    threshold: float,
) -> Proposal:
    keyword_result = keyword.classify(message, received_on)  # step 2
    model_result, error, invalid = None, None, False
    if model.name != keyword.name:  # step 3: only the message text is sent
        model_result, error, invalid = _ask_model(model, message, received_on)
    final = model_result or keyword_result
    lane, reasons = decide_lane(  # step 4
        final, keyword_result, model_result, invalid_output=invalid, threshold=threshold
    )
    return Proposal(
        keyword=keyword_result,
        model=model_result,
        error=error,
        invalid_output=invalid,
        final=final,
        is_fallback=model.name != keyword.name and model_result is None,
        lane=lane,
        reasons=reasons,
        complaint_by=complaint_sources(keyword_result, model_result),
    )


def ai_eval_record(p: Proposal) -> dict:
    return {
        "category": p.final.category,
        "lane": p.lane,
        "fields": p.final.fields.model_dump(mode="json", exclude_none=True),
        "confidence": round(p.final.confidence, 3),
        "backend": p.final.backend,
        "is_fallback": p.is_fallback,
    }


def run_pipeline(
    factory: sessionmaker[Session],
    enquiry_id: int,
    *,
    keyword: EnquiryClassifier,
    model: EnquiryClassifier,
    settings: Settings,
    clock: Clock,
) -> PipelineOutcome:
    """Classify a saved enquiry. Also used to re-run a failed or corrected one."""
    rules = HoldRules.from_settings(settings)
    try:
        with factory() as session:
            enquiry = session.get(Enquiry, enquiry_id)
            message, received_at = enquiry.message, enquiry.received_at
        received_on = received_at.astimezone(rules.tz).date()

        p = propose(
            message,
            received_on,
            keyword=keyword,
            model=model,
            threshold=settings.classifier_confidence_threshold,
        )
        keyword_result, model_result, error = p.keyword, p.model, p.error
        final, is_fallback, lane, reasons, complaint_by = (
            p.final,
            p.is_fallback,
            p.lane,
            p.reasons,
            p.complaint_by,
        )

        with factory() as session, session.begin():
            now = clock()
            enquiry = session.get(Enquiry, enquiry_id, with_for_update=True)
            gm_id = session.scalar(select(User.id).where(User.is_gm))
            enquiry.category = final.category
            enquiry.fields = final.fields.model_dump(mode="json", exclude_none=True)
            enquiry.owner_team = final.owner
            enquiry.assigned_user_id = gm_id if final.owner == OwnerTeam.GM else None  # A-119
            enquiry.confidence = Decimal(str(round(final.confidence, 3)))
            enquiry.backend = final.backend
            enquiry.is_fallback = is_fallback
            enquiry.lane = lane
            enquiry.lane_reasons = reasons
            enquiry.keyword_output = _result_dict(keyword_result)
            enquiry.model_output = (
                model_result.raw_output or _result_dict(model_result)
                if model_result
                else ({"error": error} if error else None)
            )
            enquiry.draft_reply = build_draft(  # step 6
                session,
                final.draft_template,
                final.fields,
                enquiry.contact_name,
                now=now,
                rules=rules,
            )
            enquiry.error = error
            # The AI's own decision, kept unchanged for comparison with the GM's (A-145).
            enquiry.ai_eval = ai_eval_record(p)
            enquiry.status = EnquiryStatus.CLASSIFIED  # step 7
            enquiry.classified_at = now
            enquiry.updated_at = now
            if (
                complaint_by
                and session.scalar(select(GmAlert.id).where(GmAlert.enquiry_id == enquiry_id))
                is None
            ):
                session.add(
                    GmAlert(
                        enquiry_id=enquiry_id,
                        reason=f"complaint ({' and '.join(complaint_by)})",
                        created_at=now,
                    )
                )
            session.flush()
            return _outcome(session, enquiry)
    except Exception as exc:
        # Never lose the enquiry: keep it, marked failed, for the retry button.
        logger.error("enquiry pipeline failed", extra=exception_fields(exc))
        with factory() as session, session.begin():
            enquiry = session.get(Enquiry, enquiry_id, with_for_update=True)
            enquiry.status = EnquiryStatus.FAILED
            enquiry.error = f"pipeline_error:{type(exc).__name__}"
            enquiry.updated_at = clock()
            session.flush()
            return _outcome(session, enquiry)


def submit_enquiry(
    factory: sessionmaker[Session],
    *,
    message: str,
    contact_name: str,
    contact_email: str | None,
    contact_phone: str | None,
    consent: bool,
    keyword: EnquiryClassifier,
    model: EnquiryClassifier,
    settings: Settings,
    clock: Clock,
    channel: str = "web",
) -> PipelineOutcome:
    """The public form: save first, then classify (brief)."""
    enquiry_id = save_enquiry(
        factory,
        message=message,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        consent=consent,
        settings=settings,
        now=clock(),
        channel=channel,
    )
    return run_pipeline(
        factory, enquiry_id, keyword=keyword, model=model, settings=settings, clock=clock
    )


def classify_pending(
    factory: sessionmaker[Session],
    *,
    keyword: EnquiryClassifier,
    model: EnquiryClassifier,
    settings: Settings,
    clock: Clock,
    delay_s: float = 0.0,
    sleep: Callable[[float], None] | None = None,
) -> list[PipelineOutcome]:
    """Run every pending enquiry through the pipeline, oldest first (seed --classify,
    A-143). Model calls are spaced by `delay_s` to respect provider limits (A-141)."""
    with factory() as session:
        ids = list(
            session.scalars(
                select(Enquiry.id)
                .where(Enquiry.status == EnquiryStatus.PENDING)
                .order_by(Enquiry.received_at, Enquiry.id)
            )
        )
    outcomes = []
    for index, enquiry_id in enumerate(ids):
        if index and delay_s and model.name != keyword.name and sleep is not None:
            sleep(delay_s)
        outcomes.append(
            run_pipeline(
                factory, enquiry_id, keyword=keyword, model=model, settings=settings, clock=clock
            )
        )
    return outcomes

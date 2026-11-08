"""Staff actions on an enquiry: correct, re-route, reply, and acknowledging GM alerts
(A-124, A-126, A-127, A-129, D-44).

Each action locks the enquiry row first, so two staff members acting at once are
applied one after the other, and the second sees the first one's result. Every change
is written to the audit log with its old and new value. Those audit rows also stop a
re-run from overwriting staff work (A-125).
"""

import logging
import re
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classifiers.base import OWNER_FOR
from app.classifiers.fields import ExtractedFields, keep_plausible
from app.classifiers.templates import DRAFTS, PLACEHOLDERS
from app.db.models import Enquiry, GmAlert, User
from app.db.models.enums import EnquiryCategory, EnquiryStatus, Lane, OwnerTeam
from app.services import audit
from app.services.enquiry_drafts import build_draft
from app.services.enquiry_inbox import AUDIT_ENTITY
from app.services.enquiry_lanes import LANE_FOR
from app.services.errors import DomainError
from app.services.quotes import HoldRules

logger = logging.getLogger("app.enquiries")

MAX_REPLY_LENGTH = 5_000  # A-127
ALERT_ENTITY = "gm_alert"
# Owner per lane, for re-routing (A-126). Unsorted belongs to nobody; the GM sees it.
OWNER_FOR_LANE: dict[str, str | None] = {
    Lane.ROOM_BOOKING: OwnerTeam.RESERVATIONS,
    Lane.WEDDING: OwnerTeam.EVENTS,
    Lane.CORPORATE_OFFSITE: OwnerTeam.EVENTS,
    Lane.COMPLAINT: OwnerTeam.GM,
    Lane.UNSORTED: None,
}
# Only the template placeholders count: other braces in a reply are left alone.
_UNFILLED = re.compile(r"\{(" + "|".join(sorted(PLACEHOLDERS)) + r")\}")


class InvalidEnquiryAction(DomainError):
    """The change itself is not acceptable (422). `code` says why."""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class EnquiryActionRefused(DomainError):
    """The enquiry is not in a state that allows this action (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AlertNotFound(DomainError):
    """No GM alert with this id."""


class AlertAlreadyAcknowledged(DomainError):
    code = "already_acknowledged"


def _require_open(enquiry: Enquiry) -> None:
    """Staff act on classified enquiries that have not been replied to yet."""
    if enquiry.status == EnquiryStatus.REPLIED:
        raise EnquiryActionRefused("already_replied", "This enquiry has already been replied to.")
    if enquiry.status != EnquiryStatus.CLASSIFIED:
        raise EnquiryActionRefused(
            "not_classified", "This enquiry has not been classified yet; re-run it first."
        )


def _assign(session: Session, enquiry: Enquiry, owner: str | None) -> None:
    """A-119: GM-owned enquiries go to the GM account; teams own their lane."""
    enquiry.owner_team = owner
    enquiry.assigned_user_id = (
        session.scalar(select(User.id).where(User.is_gm)) if owner == OwnerTeam.GM else None
    )


def _ensure_alert(session: Session, enquiry: Enquiry, reason: str, now: datetime) -> None:
    """Anything staff put in the complaint lane alerts the GM, once per enquiry."""
    if session.scalar(select(GmAlert.id).where(GmAlert.enquiry_id == enquiry.id)) is None:
        session.add(GmAlert(enquiry_id=enquiry.id, reason=reason, created_at=now))


# ---------- correct (A-124) ----------


def correct_enquiry(
    session: Session,
    enquiry: Enquiry,
    *,
    actor: User,
    category: str | None,
    field_changes: dict,
    now: datetime,
    rules: HoldRules,
) -> list[str]:
    """Apply a staff correction. `field_changes` holds only the fields being changed
    (None clears one). Returns the names of what changed."""
    _require_open(enquiry)
    old_fields = dict(enquiry.fields or {})
    merged = {**old_fields, **{k: v for k, v in field_changes.items()}}
    merged = {k: v for k, v in merged.items() if v is not None}
    try:
        fields = ExtractedFields(**merged)
    except ValidationError as exc:
        names = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]}) or ["fields"]
        raise InvalidEnquiryAction(
            "invalid_fields", "Please check the corrected fields.", {"fields": names}
        ) from exc
    received_on = enquiry.received_at.astimezone(rules.tz).date()
    if keep_plausible(fields, received_on) != fields:  # same checks as extraction
        raise InvalidEnquiryAction(
            "implausible_dates",
            "Dates must be within two years of when the enquiry arrived.",
            {"fields": ["check_in", "check_out", "event_month"]},
        )
    new_fields = fields.model_dump(mode="json", exclude_none=True)
    new_category = category or enquiry.category

    changed: list[str] = []
    if new_category != enquiry.category:
        audit.record(
            session,
            actor_id=actor.id,
            entity_type=AUDIT_ENTITY,
            entity_id=enquiry.reference,
            action="correct",
            field="category",
            old=enquiry.category,
            new=new_category,
            now=now,
        )
        enquiry.category = new_category
        # A-109 via the category's lane. `lane_reasons` stays as the pipeline's record.
        enquiry.lane = LANE_FOR[new_category]
        _assign(session, enquiry, OWNER_FOR[new_category])
        changed.append("category")
    for key in sorted(set(old_fields) | set(new_fields)):
        if old_fields.get(key) != new_fields.get(key):
            audit.record(
                session,
                actor_id=actor.id,
                entity_type=AUDIT_ENTITY,
                entity_id=enquiry.reference,
                action="correct",
                field=f"fields.{key}",
                old=old_fields.get(key),
                new=new_fields.get(key),
                now=now,
            )
            changed.append(f"fields.{key}")
    if not changed:
        raise InvalidEnquiryAction("no_change", "Nothing was changed.")

    enquiry.fields = new_fields
    enquiry.draft_reply = build_draft(  # prices worked out again in code
        session, DRAFTS[new_category], fields, enquiry.contact_name, now=now, rules=rules
    )
    if enquiry.category == EnquiryCategory.COMPLAINT:
        _ensure_alert(session, enquiry, "complaint (staff)", now)
    enquiry.updated_at = now
    session.flush()
    return changed


# ---------- re-route (A-126) ----------


def reroute_enquiry(
    session: Session, enquiry: Enquiry, *, actor: User, lane: str, now: datetime
) -> None:
    """Move the enquiry to another lane. The category is left as it was, so the history
    shows both what was classified and where staff put it."""
    _require_open(enquiry)
    if lane == enquiry.lane:
        raise InvalidEnquiryAction("no_change", "The enquiry is already in that lane.")
    audit.record(
        session,
        actor_id=actor.id,
        entity_type=AUDIT_ENTITY,
        entity_id=enquiry.reference,
        action="reroute",
        field="lane",
        old=enquiry.lane,
        new=lane,
        now=now,
    )
    enquiry.lane = lane
    _assign(session, enquiry, OWNER_FOR_LANE[lane])
    if lane == Lane.COMPLAINT:
        _ensure_alert(session, enquiry, "complaint (staff)", now)
    enquiry.updated_at = now
    session.flush()


# ---------- reply, simulated (A-127) ----------


def reply_to_enquiry(
    session: Session, enquiry: Enquiry, *, actor: User, text: str, now: datetime
) -> None:
    """Record the reply a staff member chose to send. Nothing is delivered (brief)."""
    _require_open(enquiry)
    text = text.strip()
    if not text:
        raise InvalidEnquiryAction("empty_reply", "Please write the reply.")
    if len(text) > MAX_REPLY_LENGTH:
        raise InvalidEnquiryAction(
            "reply_too_long", f"Please keep the reply under {MAX_REPLY_LENGTH} characters."
        )
    unfilled = sorted(set(_UNFILLED.findall(text)))
    if unfilled:
        raise InvalidEnquiryAction(
            "unfilled_placeholder",
            "Please fill in or remove the placeholders before sending.",
            {"placeholders": unfilled},
        )
    enquiry.reply_text = text
    enquiry.replied_at = now
    enquiry.replied_by = actor.id
    enquiry.status = EnquiryStatus.REPLIED
    enquiry.updated_at = now
    audit.record(
        session,
        actor_id=actor.id,
        entity_type=AUDIT_ENTITY,
        entity_id=enquiry.reference,
        action="reply",
        new={"length": len(text)},  # the text itself stays on the enquiry, not the log
        now=now,
    )
    session.flush()
    # The reference only: never the reply or the contact details (brief).
    logger.info(
        "enquiry reply recorded (simulated, not sent)", extra={"reference": enquiry.reference}
    )


# ---------- GM alerts (A-129) ----------


def acknowledge_alert(session: Session, alert_id: int, *, actor: User, now: datetime) -> GmAlert:
    alert = session.scalar(
        select(GmAlert)
        .where(GmAlert.id == alert_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if alert is None:
        raise AlertNotFound("No alert with that id.")
    if alert.acknowledged_at is not None:
        raise AlertAlreadyAcknowledged("This alert has already been acknowledged.")
    alert.acknowledged_at = now
    alert.acknowledged_by = actor.id
    audit.record(
        session,
        actor_id=actor.id,
        entity_type=ALERT_ENTITY,
        entity_id=str(alert.id),
        action="acknowledge",
        now=now,
    )
    session.flush()
    return alert

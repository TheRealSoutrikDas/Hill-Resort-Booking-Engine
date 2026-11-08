"""Enquiry routes (brief): the public form, the staff inbox, detail and re-run (21a).

The public form returns only a reference; classification is for staff (A-122). All
staff can read every lane (A-123). Corrections, re-route and replies are in 21b.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AppSettings, Clock, DbSession, KeywordBackend, ModelBackend, SessionFactory
from app.api.errors import ErrorResponse
from app.api.ratelimit import limit_per_ip
from app.api.security import StaffUser
from app.db.models import Enquiry, GmAlert, User
from app.db.models.enums import EnquiryStatus, Lane
from app.services import audit
from app.services.enquiry_inbox import (
    AUDIT_ENTITY,
    ReclassifyNotAllowed,
    can_reclassify,
    get_enquiry,
    history,
)
from app.services.enquiry_pipeline import run_pipeline, submit_enquiry

router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])

STAFF_ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
MAX_LIST = 200
SNIPPET = 140


# ---------- public form ----------


class EnquiryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    # Generous here so the service can give its friendly "too long" message (A-114).
    message: str = Field(max_length=10_000)
    consent: bool


class EnquiryReceived(BaseModel):
    reference: str
    message: str


@router.post(
    "",
    status_code=201,
    response_model=EnquiryReceived,
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(limit_per_ip("enquiry"))],
)
def send_enquiry(
    body: EnquiryIn,
    factory: SessionFactory,
    keyword: KeywordBackend,
    model: ModelBackend,
    settings: AppSettings,
    clock: Clock,
) -> EnquiryReceived:
    """Public enquiry form: saved first, then classified; only the reference comes back."""
    outcome = submit_enquiry(
        factory,
        message=body.message,
        contact_name=body.name,
        contact_email=body.email,
        contact_phone=body.phone,
        consent=body.consent,
        keyword=keyword,
        model=model,
        settings=settings,
        clock=clock,
    )
    return EnquiryReceived(
        reference=outcome.reference, message="Thank you. Our team will reply to you soon."
    )


# ---------- staff inbox ----------


class InboxItem(BaseModel):
    reference: str
    received_at: datetime
    channel: str
    contact_name: str | None
    snippet: str
    status: str
    category: str | None
    lane: str | None
    owner_team: str | None
    confidence: float | None
    backend: str | None
    is_fallback: bool
    gm_alert: bool


class Inbox(BaseModel):
    counts: dict[str, int]  # per lane, plus "pending" and "failed"
    items: list[InboxItem]


def _alerted(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return set(db.scalars(select(GmAlert.enquiry_id).where(GmAlert.enquiry_id.in_(ids))))


def _item(e: Enquiry, alerted: set[int]) -> InboxItem:
    snippet = e.message if len(e.message) <= SNIPPET else e.message[: SNIPPET - 1] + "…"
    return InboxItem(
        reference=e.reference,
        received_at=e.received_at,
        channel=e.channel,
        contact_name=e.contact_name,
        snippet=snippet,
        status=e.status,
        category=e.category,
        lane=e.lane,
        owner_team=e.owner_team,
        confidence=float(e.confidence) if e.confidence is not None else None,
        backend=e.backend,
        is_fallback=e.is_fallback,
        gm_alert=e.id in alerted,
    )


@router.get("", response_model=Inbox, responses=STAFF_ERRORS)
def inbox(
    user: StaffUser,
    db: DbSession,
    lane: Lane | None = None,
    status: Annotated[EnquiryStatus | None, Query()] = None,
) -> Inbox:
    """Newest first, filtered by lane or status, with counts for the lane tabs."""
    counts = {lane_value.value: 0 for lane_value in Lane} | {"pending": 0, "failed": 0}
    by_lane = (
        select(Enquiry.lane, func.count())
        .where(Enquiry.status == EnquiryStatus.CLASSIFIED)
        .group_by(Enquiry.lane)
    )
    for lane_value, count in db.execute(by_lane):
        counts[lane_value] = count
    for status_value in (EnquiryStatus.PENDING, EnquiryStatus.FAILED):
        counts[status_value.value] = db.scalar(
            select(func.count()).select_from(Enquiry).where(Enquiry.status == status_value)
        )

    stmt = select(Enquiry).order_by(Enquiry.received_at.desc(), Enquiry.id.desc()).limit(MAX_LIST)
    if lane is not None:
        stmt = stmt.where(Enquiry.lane == lane)
    if status is not None:
        stmt = stmt.where(Enquiry.status == status)
    enquiries = list(db.scalars(stmt))
    alerted = _alerted(db, [e.id for e in enquiries])
    return Inbox(counts=counts, items=[_item(e, alerted) for e in enquiries])


# ---------- detail ----------


class AlertOut(BaseModel):
    id: int
    reason: str
    created_at: datetime
    acknowledged_at: datetime | None


class HistoryEntry(BaseModel):
    at: datetime
    by: str
    action: str
    field: str | None
    old: Any
    new: Any


class EnquiryDetail(InboxItem):
    message: str  # the original message, shown beside the extracted fields
    contact_email: str | None
    contact_phone: str | None
    consent_at: datetime | None
    fields: dict
    lane_reasons: list[str]
    keyword_output: dict | None
    model_output: dict | None  # kept unchanged for comparison with corrections
    draft_reply: str | None  # plain text; rendered as text, never HTML
    error: str | None
    classified_at: datetime | None
    alert: AlertOut | None
    history: list[HistoryEntry]
    can_reclassify: bool


def detail(db: Session, enquiry: Enquiry) -> EnquiryDetail:
    alert = db.scalar(select(GmAlert).where(GmAlert.enquiry_id == enquiry.id))
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.role == "staff"))}
    base = _item(enquiry, {enquiry.id} if alert else set())
    return EnquiryDetail(
        **base.model_dump(),
        message=enquiry.message,
        contact_email=enquiry.contact_email,
        contact_phone=enquiry.contact_phone,
        consent_at=enquiry.consent_at,
        fields=enquiry.fields or {},
        lane_reasons=enquiry.lane_reasons or [],
        keyword_output=enquiry.keyword_output,
        model_output=enquiry.model_output,
        draft_reply=enquiry.draft_reply,
        error=enquiry.error,
        classified_at=enquiry.classified_at,
        alert=AlertOut(
            id=alert.id,
            reason=alert.reason,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
        )
        if alert
        else None,
        history=[
            HistoryEntry(
                at=h.created_at,
                by=names.get(h.actor_user_id, "staff"),
                action=h.action,
                field=h.field,
                old=h.old_value,
                new=h.new_value,
            )
            for h in history(db, enquiry)
        ],
        can_reclassify=can_reclassify(db, enquiry),
    )


@router.get("/{reference}", response_model=EnquiryDetail, responses=STAFF_ERRORS)
def get_enquiry_detail(reference: str, user: StaffUser, db: DbSession) -> EnquiryDetail:
    """The original message beside the extracted fields, both outputs, draft and history."""
    return detail(db, get_enquiry(db, reference))


# ---------- re-run (retry) ----------


@router.post("/{reference}/classify", response_model=EnquiryDetail, responses=STAFF_ERRORS)
def reclassify(
    reference: str,
    user: StaffUser,
    factory: SessionFactory,
    keyword: KeywordBackend,
    model: ModelBackend,
    settings: AppSettings,
    clock: Clock,
) -> EnquiryDetail:
    """Re-run the pipeline: the retry for failed enquiries. Refused once staff have
    corrected, re-routed or replied, so a re-run never wipes their work (A-125)."""
    with factory() as session, session.begin():
        enquiry = get_enquiry(session, reference, lock=True)
        if not can_reclassify(session, enquiry):
            raise ReclassifyNotAllowed(
                "This enquiry has been handled by staff; correct it instead."
            )
        enquiry_id = enquiry.id
        before = {"status": enquiry.status, "category": enquiry.category, "lane": enquiry.lane}
    outcome = run_pipeline(
        factory, enquiry_id, keyword=keyword, model=model, settings=settings, clock=clock
    )
    with factory() as session, session.begin():
        enquiry = session.get(Enquiry, enquiry_id)
        audit.record(
            session,
            actor_id=user.id,
            entity_type=AUDIT_ENTITY,
            entity_id=enquiry.reference,
            action="reclassify",
            old=before,
            new={"status": outcome.status, "category": outcome.category, "lane": outcome.lane},
            now=clock(),
        )
        session.flush()
        return detail(session, enquiry)

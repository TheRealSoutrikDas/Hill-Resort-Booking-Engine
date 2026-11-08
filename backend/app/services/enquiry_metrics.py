"""Enquiry metrics for the inbox dashboard (A-128, D-44).

Every number is counted from the database over enquiries received in the date range
(business dates, IST). Rates come with their numerator and denominator so a reader can
see how small a sample is. Nothing here is estimated.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Enquiry
from app.db.models.enums import EnquiryStatus, Lane
from app.services.enquiry_inbox import AUDIT_ENTITY
from app.services.errors import DomainError

DEFAULT_DAYS = 30
MAX_DAYS = 366


class InvalidMetricsRange(DomainError):
    code = "invalid_range"


@dataclass(frozen=True)
class Rate:
    count: int
    out_of: int

    @property
    def value(self) -> float | None:
        return round(self.count / self.out_of, 3) if self.out_of else None


@dataclass(frozen=True)
class AiAccuracy:
    """The AI's own decision (`ai_eval`) against what the GM approved (`actual_eval`),
    over approved enquiries for one backend (A-145)."""

    approved: int
    category: Rate
    lane: Rate
    fields: Rate  # all fields exactly as approved


@dataclass(frozen=True)
class EnquiryMetrics:
    date_from: date
    date_to: date
    received: int
    by_lane: dict[str, int]
    pending: int
    failed: int
    replied: int
    sent_to_unsorted: Rate  # by the pipeline, before any staff change
    fallback: Rate  # the model was down or its output was invalid
    category_corrected: Rate  # staff changed the category
    median_minutes_to_reply: float | None
    awaiting_approval: int  # classified by the AI, not yet approved by the GM
    ai_accuracy: dict[str, AiAccuracy]  # by backend; a fallback counts as "keyword (fallback)"


def resolve_range(date_from: date | None, date_to: date | None, today: date) -> tuple[date, date]:
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_DAYS - 1)
    if date_from > date_to:
        raise InvalidMetricsRange("The start date must not be after the end date.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise InvalidMetricsRange(f"Please choose at most {MAX_DAYS} days.")
    return date_from, date_to


def enquiry_metrics(
    session: Session, date_from: date, date_to: date, tz: ZoneInfo
) -> EnquiryMetrics:
    start = datetime.combine(date_from, time.min, tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    in_range = and_(Enquiry.received_at >= start, Enquiry.received_at < end)
    handled = Enquiry.status.in_((EnquiryStatus.CLASSIFIED, EnquiryStatus.REPLIED))

    def count(*where) -> int:
        return session.scalar(select(func.count()).select_from(Enquiry).where(in_range, *where))

    by_lane = {lane.value: 0 for lane in Lane}
    for lane, n in session.execute(
        select(Enquiry.lane, func.count()).where(in_range, handled).group_by(Enquiry.lane)
    ):
        by_lane[lane] = n
    classified = count(handled)

    corrected = session.scalar(
        select(func.count(func.distinct(Enquiry.id)))
        .select_from(Enquiry)
        .join(
            AuditLog,
            and_(
                AuditLog.entity_type == AUDIT_ENTITY,
                AuditLog.entity_id == Enquiry.reference,
                AuditLog.action == "correct",
                AuditLog.field == "category",
            ),
        )
        .where(in_range, handled)
    )
    minutes = (func.extract("epoch", Enquiry.replied_at - Enquiry.received_at) / 60).label("m")
    median = session.scalar(
        select(func.percentile_cont(0.5).within_group(cast(minutes, Float))).where(
            in_range, Enquiry.status == EnquiryStatus.REPLIED
        )
    )
    approved = session.execute(
        select(Enquiry.ai_eval, Enquiry.actual_eval).where(
            in_range, Enquiry.verified_at.is_not(None), Enquiry.ai_eval.is_not(None)
        )
    ).all()
    awaiting = count(handled, Enquiry.ai_eval.is_not(None), Enquiry.verified_at.is_(None))
    return EnquiryMetrics(
        date_from=date_from,
        date_to=date_to,
        received=count(),
        by_lane=by_lane,
        pending=count(Enquiry.status == EnquiryStatus.PENDING),
        failed=count(Enquiry.status == EnquiryStatus.FAILED),
        replied=count(Enquiry.status == EnquiryStatus.REPLIED),
        sent_to_unsorted=Rate(
            count(handled, func.jsonb_array_length(Enquiry.lane_reasons) > 0), classified
        ),
        fallback=Rate(count(handled, Enquiry.is_fallback.is_(True)), classified),
        category_corrected=Rate(corrected, classified),
        median_minutes_to_reply=round(median, 1) if median is not None else None,
        awaiting_approval=awaiting,
        ai_accuracy=ai_accuracy(approved),
    )


def backend_label(ai_eval: dict) -> str:
    backend = ai_eval.get("backend") or "unknown"
    return f"{backend} (fallback)" if ai_eval.get("is_fallback") else backend


def ai_accuracy(rows) -> dict[str, AiAccuracy]:
    """Pure: [(ai_eval, actual_eval), ...] to accuracy per backend."""
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for ai, actual in rows:
        groups.setdefault(backend_label(ai), []).append((ai, actual))
    result = {}
    for label, pairs in sorted(groups.items()):
        n = len(pairs)

        def matches(key: str, pairs=pairs) -> int:
            return sum(1 for ai, actual in pairs if ai.get(key) == actual.get(key))

        result[label] = AiAccuracy(
            approved=n,
            category=Rate(matches("category"), n),
            lane=Rate(matches("lane"), n),
            fields=Rate(matches("fields"), n),
        )
    return result

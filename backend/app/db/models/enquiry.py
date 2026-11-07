"""Enquiries, GM alerts and the audit log of staff corrections."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._columns import created_at_column, updated_at_column
from app.db.models.enums import (
    EnquiryCategory,
    EnquiryChannel,
    EnquiryStatus,
    Lane,
    OwnerTeam,
    values_check,
)


class Enquiry(Base):
    """Saved with status pending before any model call, so a failure never loses it."""

    __tablename__ = "enquiries"
    __table_args__ = (
        values_check("channel", EnquiryChannel),
        values_check("status", EnquiryStatus),
        values_check("category", EnquiryCategory),
        values_check("lane", Lane),
        values_check("owner_team", OwnerTeam),
        CheckConstraint("reference ~ '^ENQ-[0-9]{4,}$'", name="reference_format"),
        CheckConstraint("message ~ '\\S'", name="message_not_blank"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"
        ),
        # The website form requires consent; enquiries logged from other channels do not
        # pass through it.
        CheckConstraint(
            "channel <> 'web' OR (consent_at IS NOT NULL AND consent_version IS NOT NULL)",
            name="web_consent",
        ),
        Index("ix_enquiries_lane_received_at", "lane", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True)
    channel: Mapped[str] = mapped_column(String(16), server_default=EnquiryChannel.WEB.value)
    message: Mapped[str] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(16), server_default=EnquiryStatus.PENDING.value, index=True
    )
    category: Mapped[str | None] = mapped_column(String(32))
    lane: Mapped[str | None] = mapped_column(String(32))
    owner_team: Mapped[str | None] = mapped_column(String(16))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    # Which classifier produced the result (for example llm or keyword). Not a CHECK,
    # because the clearly labelled stub backend writes its own name during the build.
    backend: Mapped[str | None] = mapped_column(String(16))
    is_fallback: Mapped[bool] = mapped_column(Boolean, server_default=false())
    # Extracted fields after validation in code (check_in, guests, budget_inr, ...).
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Raw outputs kept for comparison when staff correct a classification.
    model_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    keyword_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    draft_reply: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class GmAlert(Base):
    """In-app alert for the GM, raised for every complaint. One per enquiry, so re-running
    the pipeline cannot raise a duplicate."""

    __tablename__ = "gm_alerts"
    __table_args__ = (
        CheckConstraint(
            "(acknowledged_at IS NULL) = (acknowledged_by IS NULL)", name="acknowledged_pair"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[int] = mapped_column(ForeignKey("enquiries.id"), unique=True)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    """Who changed what, when, from which value to which. Written by staff actions."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    field: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()

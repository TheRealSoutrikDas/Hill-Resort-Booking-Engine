"""What the website sells: room types, rate plans, nightly rates, web allotment, promos."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._columns import created_at_column, updated_at_column
from app.db.models.enums import RoomKind, values_check


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (
        values_check("kind", RoomKind),
        CheckConstraint("total_units > 0", name="total_units_positive"),
        CheckConstraint("max_guests > 0", name="max_guests_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    # Physical stock at the resort. The web allotment per night is a share of this.
    total_units: Mapped[int] = mapped_column(Integer)
    max_guests: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class RatePlan(Base):
    __tablename__ = "rate_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class DailyRate(Base):
    """Pre-tax price for one unit of a room type, on one rate plan, for one night.

    No row means that room type and plan are not sellable that night.
    """

    __tablename__ = "daily_rates"
    __table_args__ = (CheckConstraint("price_paise > 0", name="price_positive"),)

    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), primary_key=True)
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    price_paise: Mapped[int] = mapped_column(BigInteger)


class Allotment(Base):
    """Web stock for one room type on one night. These rows are what booking locks.

    available = total_for_web - sold - active hold units, or 0 when blacked out.
    """

    __tablename__ = "allotments"
    __table_args__ = (
        CheckConstraint("total_for_web >= 0", name="total_for_web_non_negative"),
        CheckConstraint("sold >= 0", name="sold_non_negative"),
        # Backstop for the service rule; overselling fails here even if code is wrong.
        CheckConstraint("sold <= total_for_web", name="sold_within_allotment"),
    )

    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_for_web: Mapped[int] = mapped_column(Integer)
    sold: Mapped[int] = mapped_column(Integer, server_default="0")
    is_blackout: Mapped[bool] = mapped_column(Boolean, server_default=false())
    updated_at: Mapped[datetime] = updated_at_column()


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("code = upper(code)", name="code_uppercase"),
        CheckConstraint("percent_off BETWEEN 1 AND 100", name="percent_off_range"),
        CheckConstraint("valid_to >= valid_from", name="valid_range"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="max_uses_positive"),
        CheckConstraint("used_count >= 0", name="used_count_non_negative"),
        CheckConstraint("max_uses IS NULL OR used_count <= max_uses", name="within_max_uses"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    percent_off: Mapped[int] = mapped_column(Integer)
    # Inclusive date range, compared with the booking date in IST.
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = created_at_column()

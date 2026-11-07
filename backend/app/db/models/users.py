"""Accounts. Guests and staff share one table; the GM is a flagged staff account."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, String, false, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._columns import created_at_column
from app.db.models.enums import StaffTeam, UserRole, values_check


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        values_check("role", UserRole),
        values_check("team", StaffTeam),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Guests have no team and are never GM. Staff need a team unless they are the GM.
        CheckConstraint(
            "(role = 'guest' AND team IS NULL AND NOT is_gm)"
            " OR (role = 'staff' AND (team IS NOT NULL OR is_gm))",
            name="role_team_gm",
        ),
        # Exactly one account can carry the GM flag, so "assign to GM" is unambiguous.
        Index("uq_users_single_gm", "is_gm", unique=True, postgresql_where=text("is_gm")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(16))
    team: Mapped[str | None] = mapped_column(String(16))
    is_gm: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = created_at_column()

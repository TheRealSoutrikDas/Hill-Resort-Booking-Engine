import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db.base import Base

EXPECTED_TABLES = {
    "allotments",
    "audit_log",
    "booking_items",
    "bookings",
    "daily_rates",
    "enquiries",
    "gm_alerts",
    "hold_item_nights",
    "hold_items",
    "holds",
    "payments",
    "promo_codes",
    "rate_plans",
    "room_types",
    "users",
}


def test_connects_to_postgres_16_or_newer(engine: Engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT current_setting('server_version_num')::int")).scalar()
    assert version >= 160000


def test_session_timezone_is_utc(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("SHOW timezone")).scalar() == "UTC"


def test_migrations_upgrade_downgrade_round_trip(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())

    command.downgrade(alembic_config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    command.upgrade(alembic_config, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_models_match_migrations(schema: Engine) -> None:
    """Fails if someone edits a model without writing a migration (or the reverse)."""
    with schema.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    assert diff == []


def test_require_account_migration_refuses_rows_without_an_account(
    alembic_config: Config, schema: Engine
) -> None:
    """Migration 0003 must stop with instructions, not guess an owner (A-43)."""
    command.downgrade(alembic_config, "0002")
    try:
        with schema.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO holds (check_in, check_out, subtotal_paise, tax_paise,"
                    " total_paise, expires_at)"
                    " VALUES ('2027-02-12', '2027-02-13', 100, 5, 105, now())"
                )
            )
        with pytest.raises(RuntimeError, match="1 holds have no user_id"):
            command.upgrade(alembic_config, "head")
    finally:
        with schema.begin() as conn:
            conn.execute(text("DELETE FROM holds"))
        command.upgrade(alembic_config, "head")

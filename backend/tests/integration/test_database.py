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

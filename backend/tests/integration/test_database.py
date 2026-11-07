from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text


def test_connects_to_postgres_16_or_newer(engine: Engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT current_setting('server_version_num')::int")).scalar()
    assert version >= 160000


def test_session_timezone_is_utc(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("SHOW timezone")).scalar() == "UTC"


def test_migrations_upgrade_downgrade_round_trip(alembic_config: Config, engine: Engine) -> None:
    # Becomes the full schema round trip once the first migration exists (step 2b).
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert "alembic_version" in inspect(engine).get_table_names()

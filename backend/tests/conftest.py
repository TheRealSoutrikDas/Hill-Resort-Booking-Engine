"""Shared test fixtures.

Integration tests run against a real PostgreSQL database named by TEST_DATABASE_URL.
The name must end in _test, so a misconfigured URL can never wipe development data.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ENV_FILES, normalize_database_url
from app.db.session import create_db_engine
from app.services import passwords

BACKEND_DIR = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = BACKEND_DIR / "tests" / "integration"


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_ignore_empty=True, extra="ignore")

    test_database_url: str | None = None


@pytest.fixture(autouse=True, scope="session")
def cheap_password_hashing() -> None:
    """Production argon2 takes about 170 ms per hash, on purpose. Tests use the same
    algorithm with minimal cost so the suite stays fast (D-33)."""
    passwords.use_hasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark everything under tests/integration so `pytest -m "not integration"` works."""
    for item in items:
        if INTEGRATION_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    raw = _TestSettings().test_database_url
    if not raw:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Start Postgres with `docker compose up -d` "
            "and set TEST_DATABASE_URL in .env (see README).",
            pytrace=False,
        )
    url = normalize_database_url(raw)
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.fail(
            f"Refusing to run: test database name {name!r} does not end in _test.",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    eng = create_db_engine(test_database_url)
    yield eng
    eng.dispose()


def make_alembic_config(test_database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # configparser treats % as interpolation, so escape it in passwords.
    cfg.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def alembic_config(test_database_url: str) -> Config:
    return make_alembic_config(test_database_url)


@pytest.fixture(scope="session")
def schema(test_database_url: str, engine: Engine) -> Engine:
    """Rebuild the test schema from migrations once per run, so tests always see
    exactly what `alembic upgrade head` produces (not what the models claim)."""
    cfg = make_alembic_config(test_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def db(schema: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test."""
    with schema.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            trans.rollback()


@pytest.fixture
def committed(schema: Engine) -> Iterator[sessionmaker[Session]]:
    """Sessions that really commit, for tests that need a second connection to see the
    data (row locks, races). Every table is emptied afterwards."""
    from app.seed.build import reset_database

    factory = sessionmaker(bind=schema, expire_on_commit=False)
    try:
        yield factory
    finally:
        with factory() as s, s.begin():
            reset_database(s)

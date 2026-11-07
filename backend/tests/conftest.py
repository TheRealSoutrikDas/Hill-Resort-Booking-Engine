"""Shared test fixtures.

Integration tests run against a real PostgreSQL database named by TEST_DATABASE_URL.
The name must end in _test, so a misconfigured URL can never wipe development data.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, make_url

from app.core.config import ENV_FILES, normalize_database_url
from app.db.session import create_db_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = BACKEND_DIR / "tests" / "integration"


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    test_database_url: str | None = None


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


@pytest.fixture
def alembic_config(test_database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # configparser treats % as interpolation, so escape it in passwords.
    cfg.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg

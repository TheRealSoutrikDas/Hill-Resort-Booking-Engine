"""Application settings, read from environment variables.

In development the values come from the repo root .env file (commands run from backend/).
In production the hosting provider sets real environment variables and no .env file exists.
"""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILES = ("../.env", ".env")

_POSTGRES_PREFIXES = ("postgres://", "postgresql://", "postgresql+psycopg://")


def normalize_database_url(url: str) -> str:
    """Return a SQLAlchemy URL that uses the psycopg 3 driver.

    Managed providers often hand out postgres:// or postgresql:// URLs. Without the
    +psycopg suffix SQLAlchemy would look for psycopg2, which is not installed.
    """
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise ValueError("Database URL must be a PostgreSQL URL (postgresql://...)")


class Settings(BaseSettings):
    # env_ignore_empty: a blank line such as BUSINESS_TIMEZONE= in .env counts as unset,
    # so the default applies (and a blank required value fails as missing).
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_ignore_empty=True, extra="ignore")

    database_url: str
    business_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("business_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

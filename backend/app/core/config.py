"""Application settings, read from environment variables.

In development the values come from the repo root .env file (commands run from backend/).
In production the hosting provider sets real environment variables and no .env file exists.
"""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
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

    # Booking rules (A-38, A-39, A-41).
    # Check-in may be any day from today up to booking_horizon_days - 1 days ahead,
    # so the window is booking_horizon_days days long including today.
    booking_horizon_days: int = Field(default=180, gt=0)
    max_stay_nights: int = Field(default=14, gt=0)
    # How long a booking waits for another booking's row lock before giving up.
    lock_timeout_ms: int = Field(default=5_000, gt=0)

    # GST on room nights (A-08). Tested per room per night on the price actually charged:
    # at or below the threshold the low rate applies, above it the high rate.
    # Rates are in basis points (500 = 5%). Verify against current CBIC notifications.
    gst_slab_threshold_paise: int = Field(default=750_000, gt=0)
    gst_rate_low_bp: int = Field(default=500, ge=0, le=10_000)
    gst_rate_high_bp: int = Field(default=1_800, ge=0, le=10_000)

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

    @model_validator(mode="after")
    def _check_gst_rates(self) -> "Settings":
        if self.gst_rate_low_bp > self.gst_rate_high_bp:
            raise ValueError("gst_rate_low_bp must not exceed gst_rate_high_bp")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

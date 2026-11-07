import pytest
from pydantic import ValidationError

from app.core.config import Settings, normalize_database_url


@pytest.mark.parametrize(
    "raw",
    [
        "postgres://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
    ],
)
def test_normalize_database_url_uses_psycopg3(raw: str) -> None:
    assert normalize_database_url(raw) == "postgresql+psycopg://u:p@host:5432/db"


def test_normalize_database_url_rejects_non_postgres() -> None:
    with pytest.raises(ValueError):
        normalize_database_url("sqlite:///local.db")


def test_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_defaults_to_ist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    monkeypatch.delenv("BUSINESS_TIMEZONE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.business_timezone == "Asia/Kolkata"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_reject_unknown_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    monkeypatch.setenv("BUSINESS_TIMEZONE", "Mars/Olympus_Mons")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_optional_setting_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # .env.example lists every variable with an empty value; blank must mean "use the default".
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    monkeypatch.setenv("BUSINESS_TIMEZONE", "")
    monkeypatch.setenv("LOG_LEVEL", "")
    settings = Settings(_env_file=None)
    assert settings.business_timezone == "Asia/Kolkata"
    assert settings.log_level == "INFO"


def test_blank_required_setting_is_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_blank_values_in_env_file_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    for name in ("DATABASE_URL", "BUSINESS_TIMEZONE", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://u:p@host:5432/db\nBUSINESS_TIMEZONE=\nLOG_LEVEL=\n"
    )
    settings = Settings(_env_file=env_file)
    assert settings.business_timezone == "Asia/Kolkata"
    assert settings.log_level == "INFO"


def test_gst_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    for name in ("GST_SLAB_THRESHOLD_PAISE", "GST_RATE_LOW_BP", "GST_RATE_HIGH_BP"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.gst_slab_threshold_paise == 750_000
    assert (settings.gst_rate_low_bp, settings.gst_rate_high_bp) == (500, 1_800)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GST_SLAB_THRESHOLD_PAISE", "0"),
        ("GST_RATE_HIGH_BP", "10001"),
        ("GST_RATE_LOW_BP", "-1"),
        ("GST_RATE_LOW_BP", "2000"),  # low rate above the high rate
    ],
)
def test_invalid_gst_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_booking_rule_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    for name in (
        "BOOKING_HORIZON_DAYS",
        "MAX_STAY_NIGHTS",
        "LOCK_TIMEOUT_MS",
        "MAX_UNITS_PER_BOOKING",
        "HOLD_TTL_MINUTES",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert (settings.booking_horizon_days, settings.max_stay_nights) == (180, 14)
    assert settings.lock_timeout_ms == 5_000
    assert (settings.max_units_per_booking, settings.hold_ttl_minutes) == (4, 10)

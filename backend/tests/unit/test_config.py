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

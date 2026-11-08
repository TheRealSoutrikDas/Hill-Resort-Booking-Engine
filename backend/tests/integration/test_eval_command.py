"""The evaluation command end to end, and seed --classify (A-140, A-143, D-46)."""

from datetime import date, datetime, time

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.eval_enquiries as eval_module
from app.classifiers.keyword import KeywordClassifier
from app.core.config import Settings
from app.db.models import Enquiry, GmAlert
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, reset_database, seed
from app.services.enquiry_pipeline import classify_pending
from tests.factories import RULES
from tests.fakes import StubLLMClassifier

IST = RULES.tz
RECEIVED = date(2026, 11, 5)
NOW = datetime.combine(RECEIVED, time(10), tzinfo=IST)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="postgresql://u:p@localhost/x_test", _env_file=None)


def test_keyword_command_writes_the_report_and_passes(settings, tmp_path, capsys) -> None:
    out = tmp_path / "eval" / "keyword.md"
    code = eval_module.main(["--backend", "keyword", "--out", str(out)], settings=settings)
    assert code == 0
    report = out.read_text()
    assert report == capsys.readouterr().out.rstrip("\n") + "\n"
    assert "| Lane right | 27/27 (100%) |" in report


def test_both_runs_two_columns_with_pacing(settings, capsys) -> None:
    pauses: list[float] = []
    code = eval_module.main(
        ["--backend", "both", "--delay", "2"],
        settings=settings,
        model_override=StubLLMClassifier(),
        sleep=pauses.append,
    )
    assert code == 0 and pauses == [2.0] * 26
    assert "| | keyword | stub |" in capsys.readouterr().out


def test_gate_fails_when_a_required_alert_is_missed(settings, monkeypatch, capsys) -> None:
    class DeafKeywords(KeywordClassifier):
        def classify(self, message, received_on):
            result = super().classify(message, received_on)
            return result.__class__(**{**result.__dict__, "complaint_signal": False})

    monkeypatch.setattr(eval_module, "KeywordClassifier", DeafKeywords)
    code = eval_module.main(["--backend", "keyword"], settings=settings)
    captured = capsys.readouterr()
    assert code == 1
    assert (
        "required GM alerts not raised for ENQ-4428, ENQ-4429, ENQ-4430, ENQ-4431" in captured.err
    )
    assert "**fail**" in captured.out


def test_gemini_without_a_key_explains_itself(settings, capsys) -> None:
    assert eval_module.main(["--backend", "gemini"], settings=settings) == 2
    assert "needs LLM_API_KEY" in capsys.readouterr().err


# ---------- seed --classify ----------


@pytest.fixture
def seeded(committed: sessionmaker[Session]) -> sessionmaker[Session]:
    with committed() as s, s.begin():
        reset_database(s)
        seed(
            s,
            SeedContext(today=RECEIVED, now=NOW, tz=IST, gst_rule=RULES.gst_rule),
            load_sample_enquiries(),
        )
    return committed


def test_classify_pending_fills_the_inbox(seeded, test_database_url) -> None:
    settings = Settings(database_url=test_database_url, _env_file=None)
    outcomes = classify_pending(
        seeded,
        keyword=KeywordClassifier(),
        model=KeywordClassifier(),
        settings=settings,
        clock=lambda: NOW,
    )
    assert len(outcomes) == 27
    with seeded() as s:
        pending = s.scalar(
            select(func.count()).select_from(Enquiry).where(Enquiry.status == "pending")
        )
        alerts = s.scalar(select(func.count()).select_from(GmAlert))
        drafts = s.scalar(
            select(func.count()).select_from(Enquiry).where(Enquiry.draft_reply.is_not(None))
        )
    assert (pending, alerts, drafts) == (0, 4, 27)
    again = classify_pending(
        seeded,
        keyword=KeywordClassifier(),
        model=KeywordClassifier(),
        settings=settings,
        clock=lambda: NOW,
    )
    assert again == []  # only pending enquiries are run


def test_classify_pending_paces_model_calls(seeded, test_database_url) -> None:
    settings = Settings(database_url=test_database_url, _env_file=None)
    pauses: list[float] = []
    classify_pending(
        seeded,
        keyword=KeywordClassifier(),
        model=StubLLMClassifier(),
        settings=settings,
        clock=lambda: NOW,
        delay_s=4.5,
        sleep=pauses.append,
    )
    assert pauses == [4.5] * 26

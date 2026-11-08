"""Request dependencies: settings, and one database transaction per request (A-69)."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.classifiers.base import EnquiryClassifier
from app.core.config import Settings
from app.services.payments.provider import PaymentProvider
from app.services.quotes import HoldRules


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_now(request: Request) -> datetime:
    """The current time from the app's clock (D-22): real in production, fixed in tests."""
    return request.app.state.clock()


def get_rules(request: Request) -> HoldRules:
    return HoldRules.from_settings(request.app.state.settings)


def get_clock(request: Request) -> Callable[[], datetime]:
    return request.app.state.clock


def get_payment_provider_dep(request: Request) -> PaymentProvider:
    return request.app.state.payment_provider


def get_keyword_classifier(request: Request) -> EnquiryClassifier:
    return request.app.state.keyword_classifier


def get_model_backend_dep(request: Request) -> EnquiryClassifier:
    """The model classifier chosen by CLASSIFIER_BACKEND (A-113); swapped in tests."""
    return request.app.state.model_backend


def get_session_factory_dep(request: Request) -> sessionmaker[Session]:
    """For code that manages its own transactions, such as checkout (D-31)."""
    return request.app.state.session_factory


def get_db(request: Request) -> Iterator[Session]:
    """One transaction per request: committed when the route returns, rolled back if
    it raises. Services never commit themselves."""
    with request.app.state.session_factory() as session, session.begin():
        yield session


# Route parameter types, e.g. `def route(db: DbSession)`.
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory_dep)]
Now = Annotated[datetime, Depends(get_now)]
Rules = Annotated[HoldRules, Depends(get_rules)]
Clock = Annotated[Callable[[], datetime], Depends(get_clock)]
Provider = Annotated[PaymentProvider, Depends(get_payment_provider_dep)]
KeywordBackend = Annotated[EnquiryClassifier, Depends(get_keyword_classifier)]
ModelBackend = Annotated[EnquiryClassifier, Depends(get_model_backend_dep)]

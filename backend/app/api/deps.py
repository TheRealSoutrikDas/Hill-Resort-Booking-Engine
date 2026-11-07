"""Request dependencies: settings, and one database transaction per request (A-69)."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


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

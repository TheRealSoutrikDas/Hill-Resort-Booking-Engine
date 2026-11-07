"""Builds the real app against the test database for API tests."""

from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app

FRONTEND = "http://localhost:3000"


@pytest.fixture
def make_client(
    committed: sessionmaker[Session], test_database_url: str
) -> Iterator[Callable[..., TestClient]]:
    """make_client(extra_router=None) -> a TestClient over HTTPS, so Secure cookies flow."""
    clients: list[TestClient] = []

    def build(extra_router: APIRouter | None = None) -> TestClient:
        settings = Settings(database_url=test_database_url, cors_origins=FRONTEND, _env_file=None)
        app = create_app(settings, session_factory=committed)
        if extra_router is not None:
            app.include_router(extra_router)
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)

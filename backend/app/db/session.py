"""Database engine and session factory.

Created lazily so that importing this module never needs a database or settings.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_db_engine(url: str) -> Engine:
    return create_engine(
        url,
        # Drops dead connections from the pool instead of failing a request.
        pool_pre_ping=True,
        # Timestamps are stored as timestamptz; a fixed session timezone keeps
        # what the database returns independent of server settings.
        # connect_timeout: an unreachable database fails in seconds (for /health) instead
        # of hanging a request.
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 5},
    )


@lru_cache
def get_engine() -> Engine:
    return create_db_engine(get_settings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    # expire_on_commit=False keeps loaded objects readable after commit,
    # for example when a route returns a booking it just confirmed.
    return sessionmaker(bind=get_engine(), expire_on_commit=False)

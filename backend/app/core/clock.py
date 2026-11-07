"""The one production clock.

Services take `now` as a parameter instead of reading the time themselves, so tests can
create holds that are already expired without sleeping (docs/DECISIONS.md D-22).
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)

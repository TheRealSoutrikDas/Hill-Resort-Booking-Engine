"""Helpers for concurrency tests: run tasks at the same instant on separate database
connections, and check that stock is consistent afterwards (D-29)."""

import threading
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Allotment, Booking
from app.services.availability import held_units


@dataclass
class Outcome:
    value: object = None
    error: BaseException | None = None


def run_in_parallel(
    factory: sessionmaker[Session],
    tasks: Sequence[Callable[[Session], object]],
    timeout_s: float = 30.0,
) -> list[Outcome]:
    """Run each task in its own thread with its own session (so its own connection).

    A barrier releases all tasks at the same instant. Each task manages its own
    transactions, like separate HTTP requests would. Returns one Outcome per task, in
    order. Fails the test if any task is still running after `timeout_s`, so a deadlock
    or a hang shows up as a failure instead of blocking CI.
    """
    barrier = threading.Barrier(len(tasks))
    outcomes: list[Outcome | None] = [None] * len(tasks)

    def run(index: int, task: Callable[[Session], object]) -> None:
        with factory() as session:
            try:
                barrier.wait(timeout=timeout_s)
                outcomes[index] = Outcome(value=task(session))
            except BaseException as exc:  # recorded and asserted on by the test
                outcomes[index] = Outcome(error=exc)

    threads = [threading.Thread(target=run, args=(i, t)) for i, t in enumerate(tasks)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout_s)
    hung = [i for i, thread in enumerate(threads) if thread.is_alive()]
    assert not hung, f"tasks {hung} still running after {timeout_s}s (deadlock or hang?)"
    return [o for o in outcomes if o is not None]


def assert_stock_consistent(session: Session, now: datetime) -> None:
    """The overbooking invariants, checked on every allotment row:

    - 0 <= sold <= total_for_web
    - sold + active hold units <= total_for_web (on nights that are not blacked out)
    - sold equals the units of confirmed bookings on that night
    """
    rows = session.scalars(select(Allotment)).all()
    held = held_units(
        session, {r.room_type_id for r in rows}, sorted({r.stay_date for r in rows}), now
    )
    confirmed: Counter[tuple[int, object]] = Counter()
    for booking in session.scalars(select(Booking).where(Booking.status == "confirmed")):
        for item in booking.items:
            for i in range((booking.check_out - booking.check_in).days):
                confirmed[(item.room_type_id, booking.check_in + timedelta(days=i))] += item.units

    for row in rows:
        key = (row.room_type_id, row.stay_date)
        assert 0 <= row.sold <= row.total_for_web, f"{key}: sold {row.sold}"
        if not row.is_blackout:
            assert row.sold + held[key] <= row.total_for_web, (
                f"{key}: sold {row.sold} + held {held[key]} > {row.total_for_web}"
            )
        assert row.sold == confirmed[key], f"{key}: sold {row.sold}, bookings {confirmed[key]}"

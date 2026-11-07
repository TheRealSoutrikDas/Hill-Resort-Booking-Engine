"""Seed the database with deterministic demo data.

    python -m app.seed --reset                 # empty all tables, then seed
    python -m app.seed --reset --today 2026-11-07   # pretend today is that date

Run `alembic upgrade head` first. Without --reset the command refuses to touch a
database that already has data. Everything happens in one transaction: if anything
fails, nothing is written.
"""

import argparse
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.enquiry_samples import load_sample_enquiries
from app.seed.build import SeedContext, SeedError, database_has_data, reset_database, seed
from app.services.pricing import GstRule

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="empty all tables before seeding")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        help="business date to seed relative to (YYYY-MM-DD); default is today",
    )
    return parser.parse_args(argv)


def check_schema_is_current(engine: Engine) -> None:
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise SeedError(
            f"database schema is at {current or 'nothing'}, code expects {head}. "
            "Run `alembic upgrade head` first."
        )


def build_context(today: date | None) -> SeedContext:
    settings = get_settings()
    tz = ZoneInfo(settings.business_timezone)
    if today is None:
        now = datetime.now(UTC)
        today = now.astimezone(tz).date()
    else:
        now = datetime.combine(today, time(10, 0), tzinfo=tz).astimezone(UTC)
    return SeedContext(today=today, now=now, tz=tz, gst_rule=GstRule.from_settings(settings))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engine = get_engine()
    target = engine.url.render_as_string(hide_password=True)
    try:
        check_schema_is_current(engine)
        ctx = build_context(args.today)
        samples = load_sample_enquiries()
        with Session(engine) as session, session.begin():
            if database_has_data(session):
                if not args.reset:
                    raise SeedError("database already has data; use --reset to replace it")
                reset_database(session)
            summary = seed(session, ctx, samples)
    except SeedError as exc:
        print(f"Seed failed, nothing was written: {exc}", file=sys.stderr)
        return 1

    print(f"Seeded {target} for {ctx.today.isoformat()} ({ctx.tz.key})")
    print(
        f"  accounts: {summary.demo_accounts} demo (guest, 2 staff, GM) + "
        f"{summary.booking_guest_accounts} booking guests"
    )
    print(f"  keys: {summary.room_units} rooms + {summary.villa_units} villas")
    print(f"  daily rates: {summary.rate_rows}, allotment rows: {summary.allotment_rows}")
    print(
        f"  bookings: {summary.bookings_confirmed} confirmed, "
        f"{summary.bookings_cancelled} cancelled"
    )
    print(f"  enquiries: {summary.enquiries} (pending until the pipeline exists)")
    print(f"  one unit left (Family Suite): Fri {summary.one_left_friday} and Sat")
    print(f"  sold out (all room types): Fri {summary.sold_out_friday} and Sat")
    print(f"  blackout: 3 nights from Mon {summary.blackout_start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

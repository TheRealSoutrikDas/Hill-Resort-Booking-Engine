# Decisions

What was chosen, why, and what was rejected. Feeds the Technical Design Document.

## D-01 Two deployables plus managed Postgres

- Chosen: Next.js frontend, FastAPI backend, managed PostgreSQL.
- Why: small surface to deploy and explain. Overbooking protection needs only Postgres row locks.
- Rejected: Redis, message queues, microservices. Extra infrastructure that no requirement needs.

## D-02 The website sells an allotment; the reservation system stays the system of record

- Chosen: admin-set web allotment per room type per night, daily CSV export with payment status.
- Why: matches the brief's boundary and avoids a two-way integration.
- Rejected: replacing the reservation system or building a channel manager (out of scope).

## D-03 Overbooking protection with row locks and holds

- Chosen: lock allotment rows for every night of the stay, ordered by date, with `SELECT ... FOR UPDATE`; 10-minute holds; expired holds ignored lazily.
- Why: correct under concurrency and simple to reason about. Locking in date order avoids deadlocks between overlapping stays.
- Rejected: optimistic version counters (retry storms on the last unit), external locks (extra infrastructure).

## D-04 Money as integer paise

- Why: no floating point rounding errors; one documented rounding rule for GST.

## D-05 Enquiry AI: hosted LLM behind an adapter, keyword classifier as fallback

- Chosen: one LLM call returning validated JSON; the keyword classifier runs on every enquiry and always performs the complaint check.
- Why: the model proposes, code decides. Lanes, prices, alerts and sending never depend on model text.
- Rejected: model-decided routing, auto-sent replies.

## D-06 Enquiry categories beyond the brief

- Chosen: `complaint` and `other`, added to the brief's wedding, room booking and corporate offsite.
- Why: the router must handle complaints and needs somewhere to put out-of-scope messages.

## D-07 Synchronous SQLAlchemy 2.0 with psycopg 3

- Chosen: SQLAlchemy 2.0 ORM with sync sessions and the psycopg 3 driver.
- Why: `SELECT ... FOR UPDATE` inside a plain transaction is the easiest version to read and explain. FastAPI runs sync endpoints in a threadpool, which is enough at this scale, and the concurrency test can use plain threads.
- Rejected: async SQLAlchemy (more moving parts for no load requirement), psycopg2 (older driver), SQLAlchemy 2.1 (newer line; 2.0 is the mature one).

## D-08 Separate test database with a name guard

- Chosen: integration tests use `TEST_DATABASE_URL`, and the suite refuses to run unless the database name ends in `_test`.
- Why: the concurrency and migration tests create and drop data. A wrong URL must never reach development or production data.
- Rejected: SQLite for tests (no `FOR UPDATE` row locks, so it cannot prove the overbooking guarantee), sharing the development database.

## D-09 Fixed constraint naming convention

- Chosen: one naming convention on the shared metadata for primary keys, foreign keys, unique, check and index names. Unique constraints are named after all their columns, so two multi-column constraints on one table cannot clash.
- Why: migrations get the same names on every machine, and later migrations can alter or drop a constraint by name.

## D-10 Database URL normalised to psycopg 3

- Chosen: `postgres://` and `postgresql://` URLs are rewritten to `postgresql+psycopg://` in settings.
- Why: managed providers hand out plain URLs; without the driver suffix SQLAlchemy would look for psycopg2.

## D-11 Status and category columns are text with CHECK constraints

- Chosen: `varchar` plus `CHECK (col IN (...))`, generated from Python `StrEnum` classes in one module.
- Why: adding a value is a one-line migration, and the allowed values sit next to the code that uses them.
- Rejected: Postgres ENUM types (awkward to change inside migrations).

## D-12 Bookings have lines, and prices are snapshotted per night

- Chosen: `holds` and `bookings` carry the stay and the totals; `hold_items` and `booking_items` carry the lines; `hold_item_nights` stores each line's per-unit tariff, GST and GST rate for every night.
- Why: one booking can mix room types (A-13), GST is charged per night on that night's tariff, and the receipt must show exactly what was charged even if rates change later. `booking_items.hold_item_id` links each line to its night snapshot, so nothing is copied twice.
- Rejected: one room type per booking (rejected by the client), a JSON price blob (cannot be checked by the database).

## D-13 Database constraints back up every critical service rule

- Chosen: constraints that make the worst failures impossible even if service code has a bug:
  - `sold <= total_for_web` and `sold >= 0` on allotments (no overselling, no negative stock after cancellation)
  - one booking per hold, one booking per payment, unique idempotency key, at most one captured payment per hold (no double booking or double charge)
  - totals must equal subtotal minus discount plus tax (no inconsistent money)
  - promo `used_count <= max_uses`, one GM account, one GM alert per enquiry, consent required on web enquiries
- Why: services check these rules first and return friendly errors; the database is the last line. Each constraint has an integration test.

## D-14 Booking references are random, with uniqueness from the database

- Chosen: `BK-` plus 8 characters from `secrets` over a 31-character alphabet (about 850 billion codes), a UNIQUE constraint, and up to 5 retries on collision. A CHECK constraint enforces the format.
- Why: the database guarantees uniqueness; random codes cannot be guessed, which matters because booking lookup is by reference plus email.
- Rejected: hashing (a shortened hash can still collide and needs a unique constraint anyway), encoding the numeric id with Sqids (reveals booking count and order, and is not meant for security).

## D-15 Export is one row per booking line

- Chosen: the brief's columns plus `line_number`, one row per line.
- Why: a reservation system usually stores each room as its own line, so the file imports without manual splitting.

## D-16 Migrations are autogenerated, reviewed, and checked against the models in CI

- Chosen: `alembic revision --autogenerate`, then a hand review; a test compares the migrated schema with the models and fails on any difference. `alembic check` does the same from the command line.
- Why: a model change without a migration (or the reverse) is caught before merge. The comparison covers tables, columns, types, indexes, unique constraints and foreign keys; CHECK constraints are not compared by Alembic, so the constraint tests cover them.

## D-17 Pricing is calculated per unit per night in integer paise

- Chosen: pure functions in `app/services/pricing.py`. Each unit-night gets its discount, taxable value, GST rate and GST; line and stay totals are sums of those, multiplied by units. Rounding is half up to the paise with integer arithmetic.
- Why: GST is tested per room per night, so per unit-night is the natural unit. Because every total is an exact sum, `total = subtotal - discount + tax` always holds, which the database also enforces.
- Rejected: rounding once on the stay total (would hide which slab each night used), floating point (rounding drift).

## D-18 Pricing core built before the seed

- Chosen: the pure pricing functions and the reference generator moved from stage 3 into step 3a.
- Why: the seed creates paid bookings, and their amounts must come from the real pricing rules, never from guessed numbers. Promo validity rules and the API stay in stage 3.

## D-19 Discount stored per night and per line (migration 0002)

- Chosen: `discount_paise` on `hold_item_nights`, `hold_items` and `booking_items`, with CHECK constraints, added by a second migration.
- Why: the GST slab is chosen after the discount (A-08), so a night's GST is only explainable next to its discount, and the per-line export amount must be exact. The constraints were written by hand because Alembic autogenerate does not detect CHECK constraints added to existing tables.

## D-20 Seed design

- Chosen: one command, one transaction. Every number lives in `app/seed/plan.py`. Bookings are planned in memory first, so allotments are written with matching `sold` counts. Every booking is priced with the real pricing functions. A self-check compares `sold` with the confirmed bookings and promo `used_count` with promo bookings before commit. A fixed random seed and dates relative to today make it deterministic for a given date.
- Safety: refuses to run if the schema is not at the latest migration, and refuses to replace existing data without `--reset`. If anything fails, nothing is written.
- Rejected: SQL fixture files (cannot stay relative to today), a fake-data library (another dependency, and less control over deliberate states).

## D-21 Allotment row locks are the single gate for every stock change

- Chosen: every write that changes stock (create hold, convert hold, cancel, admin allotment change) first runs `lock_allotments`: `SELECT ... FOR UPDATE` on the allotment rows for every room type and night it touches, ordered by room type and then date. Only after the lock does it count active holds and check stock.
- Why it prevents overbooking: concurrent requests for the same nights queue on the row lock. Under READ COMMITTED each statement sees everything committed before it starts, so the hold count, run as its own statement after the lock, includes the holds of every request that held the lock first.
- Why that order: bookings can mix room types (A-13). If every writer locks in the same order, two writers can never each hold a row the other is waiting for, so there are no deadlocks. (The brief said "ordered by date"; ordering by room type first keeps that within each room type.)
- Lock timeout: `SET LOCAL lock_timeout` (A-41) so a stuck transaction makes others fail fast with a retryable error instead of hanging.
- Stale reads: the locking query reloads row values (`populate_existing`), so the ORM never returns numbers it read before the lock was taken. A test proves this.
- Rejected: SERIALIZABLE isolation with retries (correct, but harder to explain and every caller must retry), optimistic version counters (retry storms on the last unit), application-level locks (do not work across server instances).

## D-22 Services take `now` as a parameter

- Chosen: one production clock (`app/core/clock.py`); services receive `now` from the caller.
- Why: hold expiry and "today in IST" are testable without sleeping or patching time.
- Rejected: the database's `now()` inside queries (consistent across servers, but hard to control in tests). Clock skew between app servers is negligible against a 10-minute hold.

## D-23 Shared test builders

- Chosen: `backend/tests/factories.py` holds small row builders used by all integration tests; pytest puts `backend/` on the import path (`pythonpath`).
- Why: steps 4 to 7 need the same rooms, allotments and holds; one copy keeps the tests short and consistent.


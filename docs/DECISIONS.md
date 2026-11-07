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

- Chosen: one naming convention on the shared metadata for primary keys, foreign keys, unique, check and index names.
- Why: migrations get the same names on every machine, and later migrations can alter or drop a constraint by name.

## D-10 Database URL normalised to psycopg 3

- Chosen: `postgres://` and `postgresql://` URLs are rewritten to `postgresql+psycopg://` in settings.
- Why: managed providers hand out plain URLs; without the driver suffix SQLAlchemy would look for psycopg2.

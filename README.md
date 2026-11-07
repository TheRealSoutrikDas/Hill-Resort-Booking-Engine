# Hill Resort Direct Booking

Direct-booking website and AI enquiry inbox for a coffee-estate resort in
Chikkamagaluru, Karnataka (64 rooms, 12 villas, event lawns). Take-home project.

Status: project skeleton. Each section is filled in as its stage lands.

## What it does

To be written.

## Architecture

- `frontend/`: Next.js (TypeScript). The browser calls the API through Next.js rewrites.
- `backend/`: FastAPI (Python), layered as routes, services, database.
- PostgreSQL with Alembic migrations.
- Two deployables plus managed Postgres. No Redis, queues or microservices.

## Repository layout

```
backend/     FastAPI app, Alembic migrations, tests, evaluation data
frontend/    Next.js app
docs/        ASSUMPTIONS.md, DECISIONS.md, photo sources
.github/     CI workflow and pull request template
deployment.md
docker-compose.yml
.env.example
```

## Local setup

Needs Docker, Python 3.12 or newer, and (from stage 6) Node 22.

```bash
cp .env.example .env        # fill in POSTGRES_*, DATABASE_URL and TEST_DATABASE_URL
docker compose up -d        # Postgres 16 on 127.0.0.1:5432, plus <POSTGRES_DB>_test
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
```

Example `.env` values for local development only:

```
POSTGRES_USER=resort
POSTGRES_PASSWORD=resort_dev
POSTGRES_DB=resort
DATABASE_URL=postgresql+psycopg://resort:resort_dev@localhost:5432/resort
TEST_DATABASE_URL=postgresql+psycopg://resort:resort_dev@localhost:5432/resort_test
```

The test database is created only on the first start of an empty volume. If you
started Postgres before this existed, reset it with `docker compose down -v`
(this deletes local data).

## Run the API

From `backend/`, with Postgres running and migrations applied:

```bash
uvicorn app.main:create_app --factory --reload   # http://localhost:8000
curl localhost:8000/health                        # {"status":"ok","database":"ok"}
```

Interactive API docs are at `http://localhost:8000/docs`. Logs are JSON lines on
stdout and never contain personal data.

## Seed data

Run from `backend/` after `alembic upgrade head`:

```bash
python -m app.seed --reset                    # empty all tables, then load demo data
python -m app.seed --reset --today 2026-11-07 # as if today were that date
```

Loads 76 keys (64 rooms, 12 villas), nightly rates and web allotment from 60 days ago
to 180 days ahead, 3 promo codes, 40 bookings, 4 demo accounts (guest, 2 staff, GM)
plus one account per booking guest (booking requires an account), and the 27 sample
enquiries. It also creates three states to demonstrate: a Family Suite with one unit
left, a sold-out weekend and a three-night blackout (dates are printed at the end).
All numbers are in `backend/app/seed/plan.py`; all personal data is invented.

Without `--reset` the command refuses to touch a database that has data. It runs in
one transaction and checks its own output before committing.

## Tests

Run from `backend/`:

```bash
pytest                        # everything; integration tests need TEST_DATABASE_URL
pytest -m "not integration"   # unit tests only, no database
ruff check . && ruff format --check .
```

Integration tests run against real PostgreSQL and refuse any database whose name
does not end in `_test`. Each run rebuilds the test schema from the migrations.

The concurrency tests (`tests/integration/test_concurrency.py`) run every scenario 5
times by default, with 10 parallel guests on separate connections. For a longer soak:

```bash
CONCURRENCY_ROUNDS=50 pytest tests/integration/test_concurrency.py
```

## Migrations

Run from `backend/`:

```bash
alembic upgrade head                                 # apply all migrations
alembic downgrade -1                                 # undo the latest one
alembic upgrade head --sql                           # print the SQL without running it
alembic check                                        # fail if models and migrations differ
alembic revision --autogenerate -m "describe change" # new migration; always review it
```

If an upgrade stops with instructions (for example migration 0003 on a database seeded
before accounts were required), rebuild the development database:

```bash
alembic downgrade base && alembic upgrade head && python -m app.seed --reset
```

## Enquiry evaluation

`python -m app.eval_enquiries` (stage 5).

## Documentation

- [Assumptions](docs/ASSUMPTIONS.md)
- [Decisions](docs/DECISIONS.md)
- [Photo sources](docs/PHOTO_SOURCES.md)
- [Deployment](deployment.md)

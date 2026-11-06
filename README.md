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

To be written (stage 1, step 2).

## Seed data

`python -m app.seed --reset` (stage 1, step 3).

## Tests

To be written.

## Enquiry evaluation

`python -m app.eval_enquiries` (stage 5).

## Documentation

- [Assumptions](docs/ASSUMPTIONS.md)
- [Decisions](docs/DECISIONS.md)
- [Photo sources](docs/PHOTO_SOURCES.md)
- [Deployment](deployment.md)

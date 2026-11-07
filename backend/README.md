# Backend

FastAPI app, layered as routes, services, database.

```
app/api/            HTTP routes (thin: validate, call a service, shape the response)
app/services/       Business logic, testable without HTTP: pricing, dates, availability
                    (stock and row locks), rates, promos, quotes, holds, bookings; later
                    payments and the enquiry pipeline
app/db/             SQLAlchemy base, session and models (users, inventory, booking, enquiry)
app/schemas/        Pydantic request and response models
app/classifiers/    EnquiryClassifier interface and backends (keyword, llm)
app/core/           Settings, logging, security, error format
app/seed/           Demo data: plan.py (all numbers), build.py (writes rows), __main__.py (CLI)
app/enquiry_samples.py  Validated loader for data/sample_enquiries.json
alembic/            Migrations
tests/unit/         Fast tests, no database
tests/integration/  Tests against real Postgres, including the concurrency test
data/               sample_enquiries.json (evaluation set and seed source)
```

Setup and test commands are in the root README. Run all backend commands from this folder.

# Backend

FastAPI app, layered as routes, services, database.

```
app/api/            HTTP routes (thin: validate, call a service, shape the response)
app/services/       Business logic (allotment, holds, pricing, enquiry pipeline), testable without HTTP
app/db/             SQLAlchemy models and session
app/schemas/        Pydantic request and response models
app/classifiers/    EnquiryClassifier interface and backends (keyword, llm)
app/core/           Settings, logging, security, error format
alembic/            Migrations
tests/unit/         Fast tests, no database
tests/integration/  Tests against real Postgres, including the concurrency test
data/               sample_enquiries.json (evaluation set and seed source)
```

Setup instructions arrive in stage 1, step 2.

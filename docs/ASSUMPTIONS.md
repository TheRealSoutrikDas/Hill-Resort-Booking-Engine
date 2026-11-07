# Assumptions

Every choice the brief does not state. Status is one of: Proposed, Confirmed, Changed, Open.

| ID | Area | Assumption | Status |
|----|------|------------|--------|
| A-01 | Repo | `sample_enquiries.json` lives at `backend/data/sample_enquiries.json`. | Confirmed |
| A-02 | Tooling | Python 3.12 and Node 22 LTS. | Confirmed |
| A-03 | Tooling | Backend dependencies in `pyproject.toml` with pinned versions, installed with pip. | Confirmed |
| A-04 | Tooling | Frontend package manager is npm. | Confirmed |
| A-05 | Tooling | Lint with ruff (backend) and the Next.js ESLint config (frontend). | Confirmed |
| A-06 | Workflow | The initial skeleton commit goes straight to `main`; all later work uses feature branches and PRs. | Confirmed |
| A-07 | AI | LLM provider and model. Proposed in stage 5. | Open |
| A-08 | Pricing | GST slab thresholds and rounding rule. Proposed in stage 3. | Open |
| A-09 | Seed | Room types, rate plans, rates, allotment fraction, blackout dates, promo codes, booking count. Proposed in stage 1, step 3. | Open |
| A-10 | Export | CSV column layout as listed in the brief. | Open, to confirm |
| A-11 | Auth | Browser calls the API through Next.js rewrites so the session cookie is first-party. | Open, confirm before stage 4 |
| A-12 | Auth | Guest checkout plus optional sign up; earlier guest bookings are never attached by email automatically. | Open, confirm before stage 4 |
| A-13 | Booking | One booking is one room unit. Two rooms means two bookings. | Proposed |
| A-14 | Promo | Promo codes are percent-off only. | Proposed |
| A-15 | Pricing | Rate plans are shared across room types and priced per room type per date. A missing rate means that night is not sellable. | Proposed |
| A-16 | Booking | `guests` is one count checked against the room type's `max_guests`; no adults and children split. | Proposed |
| A-17 | Booking | Booking reference is a random 8-character code without ambiguous characters, for example `BK-7F3K9QXM`. | Proposed |
| A-18 | Database | PostgreSQL 16 locally, in CI and in production. The `postgres:16` image tag follows minor releases. | Proposed |
| A-19 | Auth | The GM account may have no team. | Proposed |
| A-20 | Promo | `used_count` goes up only on a confirmed booking; a cancellation does not give the use back. | Proposed |
| A-21 | Local dev | Local Postgres listens on 127.0.0.1:5432 only. | Proposed |
| A-22 | Tests | Tests use a separate database named `<POSTGRES_DB>_test`, and refuse any name without the `_test` suffix. | Proposed |
| A-23 | Tooling | Direct dependencies are pinned exactly; transitive ones are not locked. A lock file is a possible later step. | Proposed |
| A-24 | Tooling | New dependency versions must be at least two weeks old when added. | Proposed |

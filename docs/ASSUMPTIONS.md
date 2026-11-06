# Assumptions

Every choice the brief does not state. Status is one of: Proposed, Confirmed, Changed, Open.

| ID | Area | Assumption | Status |
|----|------|------------|--------|
| A-01 | Repo | `sample_enquiries.json` lives at `backend/data/sample_enquiries.json`. | Proposed |
| A-02 | Tooling | Python 3.12 and Node 22 LTS. | Proposed |
| A-03 | Tooling | Backend dependencies in `pyproject.toml` with pinned versions, installed with pip. | Proposed |
| A-04 | Tooling | Frontend package manager is npm. | Proposed |
| A-05 | Tooling | Lint with ruff (backend) and the Next.js ESLint config (frontend). | Proposed |
| A-06 | Workflow | The initial skeleton commit goes straight to `main`; all later work uses feature branches and PRs. | Proposed |
| A-07 | AI | LLM provider and model. Proposed in stage 5. | Open |
| A-08 | Pricing | GST slab thresholds and rounding rule. Proposed in stage 3. | Open |
| A-09 | Seed | Room types, rate plans, rates, allotment fraction, blackout dates, promo codes, booking count. Proposed in stage 1, step 3. | Open |
| A-10 | Export | CSV column layout as listed in the brief. | Open, to confirm |
| A-11 | Auth | Browser calls the API through Next.js rewrites so the session cookie is first-party. | Open, confirm before stage 4 |
| A-12 | Auth | Guest checkout plus optional sign up; earlier guest bookings are never attached by email automatically. | Open, confirm before stage 4 |

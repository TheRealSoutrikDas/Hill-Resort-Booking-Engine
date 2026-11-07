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
| A-08 | Pricing | GST per room per night on the value actually charged (after promo discount): at or below Rs 7,500 is 5%, above is 18% (Notification 15/2025-CT(Rate), from 22 Sep 2025). Exactly Rs 7,500 is 5%. No exempt slab below Rs 1,000. Breakfast on the B&B plan is part of the room value. Discount and GST are rounded half up to the paise, once per unit-night. Threshold and rates are config values. | Proposed, client to verify the after-discount basis |
| A-09 | Seed | Room types, rate plans, rates, allotment fraction, blackout dates, promo codes, booking count. Proposed in stage 1, step 3. | Open |
| A-10 | Export | Brief's column layout, one CSV row per booking line, plus a `line_number` column. `booking_id` repeats across a booking's lines; amount and tax columns are per line. | Confirmed |
| A-11 | Auth | Browser calls the API through Next.js rewrites so the session cookie is first-party. | Open, confirm before stage 4 |
| A-12 | Auth | Guest checkout plus optional sign up; earlier guest bookings are never attached by email automatically. | Open, confirm before stage 4 |
| A-13 | Booking | One booking is one guest's purchase of any mix of room types and units. | Changed (was: one booking is one unit) |
| A-13a | Booking | One stay per booking: every line shares the same check-in and check-out. Different dates means separate bookings. | Confirmed |
| A-13b | Booking | A line is a room type, a rate plan, a number of units and a guest count; guests must not exceed units x `max_guests`. | Confirmed |
| A-13c | Booking | Cancellation is for the whole booking; no partial cancellation. | Confirmed |
| A-13d | Promo | A promo code applies to the whole booking and counts as one use. | Confirmed |
| A-14 | Promo | Promo codes are percent-off only. | Confirmed |
| A-15 | Pricing | Rate plans are shared across room types and priced per room type per date. A missing rate means that night is not sellable. | Confirmed |
| A-16 | Booking | `guests` is one count per line; no adults and children split. | Confirmed |
| A-17 | Booking | Booking reference is `BK-` plus 8 random characters from 31 unambiguous ones (no I, L, O, 0, 1). Uniqueness comes from a UNIQUE constraint; the service retries on a collision. | Confirmed |
| A-18 | Database | PostgreSQL 16 locally, in CI and in production. The `postgres:16` image tag follows minor releases. | Confirmed |
| A-19 | Auth | The GM account may have no team. | Confirmed |
| A-20 | Promo | `used_count` goes up only on a confirmed booking; a cancellation does not give the use back. | Confirmed |
| A-21 | Local dev | Local Postgres listens on 127.0.0.1:5432 only. | Proposed |
| A-22 | Tests | Tests use a separate database named `<POSTGRES_DB>_test`, and refuse any name without the `_test` suffix. | Proposed |
| A-23 | Tooling | Direct dependencies are pinned exactly; transitive ones are not locked. A lock file is a possible later step. | Proposed |
| A-24 | Tooling | New dependency versions must be at least two weeks old when added. | Proposed |
| A-25 | Booking | At most 4 units per booking (`MAX_UNITS_PER_BOOKING`, enforced in the service). Larger groups use the enquiry form. | Confirmed |
| A-26 | Auth | Exactly one account carries the GM flag, enforced by a partial unique index. | Confirmed |
| A-27 | Enquiries | Channels are web, email, whatsapp and phone. Only the web form exists; the others mark seeded or manually logged enquiries. | Confirmed |
| A-28 | Enquiries | Consent timestamp and version are required for web enquiries only, since other channels never pass through the form. | Confirmed |
| A-29 | Payments | A hold may have several payment attempts (for example a failure, then a retry), but at most one that captured money. | Confirmed |
| A-30 | Enquiries | Enquiry references are `ENQ-` plus at least 4 digits, matching the client's samples (ENQ-4410). | Confirmed |
| A-31 | Promo | A promo's valid_from and valid_to dates are inclusive and compared with the booking date in IST. | Confirmed |

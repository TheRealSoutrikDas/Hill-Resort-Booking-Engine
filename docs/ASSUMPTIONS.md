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
| A-08 | Pricing | GST per room per night on the value actually charged (after promo discount): at or below Rs 7,500 is 5%, above is 18% (Notification 15/2025-CT(Rate), from 22 Sep 2025). Exactly Rs 7,500 is 5%. No exempt slab below Rs 1,000. Breakfast on the B&B plan is part of the room value. Discount and GST are rounded half up to the paise, once per unit-night. Threshold and rates are config values. | Confirmed |
| A-09 | Seed | Values in `backend/app/seed/plan.py`: Deluxe Room 30, Estate View Room 22, Family Suite 12, Plantation Villa 8, Pool Villa 4; weekday room-only rates Rs 6,000 / 8,000 / 10,000 / 14,000 / 20,500, Fri and Sat nights +20%, 20 Dec to 5 Jan +40% (year average Rs 9,468); Bed and Breakfast +Rs 1,200; web allotment 25% (8/6/3/2/1); sold-out weekend about 2 weeks ahead, Family Suite with 1 unit left about 1 week ahead, 3 blackout nights about 5 weeks ahead; WELCOME10 valid, MONSOON15 expired, COFFEE20 cap reached; 40 bookings (8 past, 28 upcoming, 4 cancelled); 1 demo guest, 2 staff, 1 GM, plus one guest account per invented booking guest (37) because booking requires an account (A-43). | Confirmed |
| A-10 | Export | Brief's column layout, one CSV row per booking line, plus a `line_number` column. `booking_id` repeats across a booking's lines; amount and tax columns are per line. | Confirmed |
| A-11 | Auth | Browser calls the API through Next.js rewrites so the session cookie is first-party. | Open, confirm before stage 4 |
| A-12 | Auth | Superseded by A-43: signing in is required to book. Sign-up details are settled at the auth checkpoint. | Changed |
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
| A-29 | Payments | A hold may have several payment attempts, but at most one that paid for the booking (status succeeded). Extra captured payments are refunded (A-50). Was: at most one that captured money, which contradicted A-50 (see D-28). | Changed |
| A-30 | Enquiries | Enquiry references are `ENQ-` plus at least 4 digits, matching the client's samples (ENQ-4410). | Confirmed |
| A-31 | Promo | A promo's valid_from and valid_to dates are inclusive and compared with the booking date in IST. | Confirmed |
| A-32 | Enquiries | In `sample_enquiries.json`, ENQ-4410 to ENQ-4412 are the client's samples; all others are invented for the demo. ENQ-4422 gained `event_month` 2027-01 (client approved). | Confirmed |
| A-33 | Payments | A cancelled booking is fully refunded; no cancellation fee. | Confirmed |
| A-34 | Seed | Every seeded account (demo accounts and booking guests) gets an unusable password marker until stage 4 sets real password hashes. | Proposed |
| A-35 | Seed | Seeded enquiries get a channel by position (web, email, whatsapp, web, phone, repeating), invented contact details, and are received over the last 72 hours. | Proposed |
| A-36 | Seed | `--today` lets the seed run as if on a given date, for repeatable demos and tests. | Proposed |
| A-37 | Availability | A night with no allotment row is not sellable online (0 available). | Confirmed |
| A-38 | Booking | Check-in can be any day from today (IST) to 179 days ahead: a 180-day window including today (`BOOKING_HORIZON_DAYS`). | Confirmed |
| A-39 | Booking | Maximum stay is 14 nights (`MAX_STAY_NIGHTS`); longer stays use the enquiry form. | Confirmed |
| A-40 | Booking | Same-day check-in is allowed when stock is available. | Confirmed |
| A-41 | Booking | A booking waits at most 5 seconds for another booking's row lock (`LOCK_TIMEOUT_MS`), then fails with "please try again" and holds nothing. | Confirmed |
| A-42 | Booking | Each booking line needs at least one guest per unit. | Confirmed |
| A-43 | Auth | Signing in is required to book (client decision, D-24). Every hold and booking belongs to an account; only that account can add guest details to, pay for or release its hold. Another account's hold is reported as not found. Guest name, email and phone on the booking are prefilled from the account and stay editable. | Confirmed |
| A-44 | Booking | A guest can release a hold (go back or change rooms); the stock frees immediately. A converted hold cannot be released. | Confirmed |
| A-45 | Pricing | The price is fixed when the hold is created; rate changes during the 10 minutes do not affect it. | Confirmed |
| A-46 | Booking | An inactive rate plan cannot be booked, even if rates exist for it. | Confirmed |
| A-47 | Promo | Promo codes are added to hold creation in step 9; step 5 holds carry no discount. | Confirmed |
| A-48 | Booking | Lookup by reference plus email stays (brief screen 4) but is view only; cancelling requires signing in as the account that booked. | Proposed |
| A-49 | Booking | Guest details are checked for shape only: a name, an email in the form name@domain.tld (stored lowercase, not verified), and a phone of 8 to 20 digits and spaces with an optional leading +. | Proposed |
| A-50 | Payments | When payment was taken but the booking fails (expired hold with stock gone, released hold, missing guest details, or a second payment for an already-paid hold), the payment is marked `refund_pending` and the hold is released so it cannot be retried. | Confirmed |
| A-51 | Booking | A guest can cancel online until the day before check-in (IST); from check-in day they contact the resort. | Confirmed |
| A-52 | Payments | Cancelling marks the payment `refund_pending`; the mock provider completes the refund in step 10. | Confirmed |
| A-53 | Booking | Only the account that made a booking can cancel it; staff cancellations are not part of the brief's admin screens. | Confirmed |
| A-54 | Promo | A hold reserves one use of its promo code, like it reserves rooms: a code with N uses left can be on at most N active holds. The use is counted when the booking is confirmed (A-20). | Confirmed |
| A-55 | Promo | A code's dates and on/off switch are checked when the hold is created; if the code expires or is switched off during the 10 minutes, the guest keeps the discount (A-45). | Confirmed |
| A-56 | Promo | If a hold expired and its code's last use was taken meanwhile, confirmation fails and the payment is refunded (as with stock, A-50). | Confirmed |
| A-57 | Promo | Codes are trimmed and case-insensitive; one code per booking. | Confirmed |
| A-58 | Promo | Error messages say why a code cannot be used (not found, switched off, not started, expired, used up); promo codes are not secrets. | Confirmed |
| A-59 | Payments | In test mode the payment step lets the guest pick the simulated outcome (success, decline, timeout), like a gateway's test cards. | Confirmed |
| A-60 | Payments | A payment can only start on an active hold with guest details; an expired hold means starting again. The brief's expired-hold case still occurs when the hold expires during the charge. | Confirmed |
| A-61 | Payments | The browser makes a new idempotency key for each deliberate click on Pay; a double click or automatic retry reuses it. A declined or timed-out attempt is final for its key. | Confirmed |
| A-62 | Payments | A mock timeout means "not charged". A real gateway's timeout means "unknown"; a real integration would ask the gateway what happened to the key before retrying. Known limit of the mock. | Confirmed |
| A-63 | Payments | Refunds are processed straight away through the mock and end `refunded`; if a refund call fails the payment stays `refund_pending` and can be retried. | Confirmed |
| A-64 | API | Every error uses `{"error": {"code", "message", "details"}, "request_id"}`. Statuses: 422 validation and invalid stay, request or promo; 409 not available, hold not active, cancellation, payment not allowed or mismatched; 404 hold or booking not found; 503 busy (with Retry-After); 500 anything unexpected, with no internal details. | Confirmed |
| A-65 | API | `/health` checks the database with `SELECT 1` and returns 503 if it is unreachable. | Confirmed |
| A-66 | Logging | Logs are JSON lines on stdout, with route templates instead of real paths; never bodies, query strings, names, emails or phones; errors as exception type and code locations, without the message. | Confirmed |
| A-67 | API | Business routes live under `/api/...`; `/health` stays at the root for the hosting platform. | Confirmed |
| A-68 | API | CORS allows only the configured frontend origins (`CORS_ORIGINS`), with credentials. | Confirmed |
| A-69 | API | One database transaction per request: committed when the route succeeds, rolled back on any error. Checkout manages its own (D-31). | Confirmed |

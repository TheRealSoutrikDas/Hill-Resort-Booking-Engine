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

## D-24 Signing in is required to book (scope change from the brief)

- Chosen: by client decision, a guest must be signed in to start a booking. The brief allowed guest checkout without an account.
- Why: the client sees an account as the standard security for a booking system, and wants every booking tied to an owner.
- Trade-offs accepted: forced sign-up can lower checkout conversion, which works against the direct-share goal (12% to 20%). Without email verification (out of scope), an account does not prove the guest owns the email. Mitigation: the frontend sends a signed-out guest to login or sign-up and straight back to the selected rooms.
- Alternative considered: guest checkout with the hold bound to an httpOnly cookie token, which gives most of the protection without sign-up friction.
- Consequences:
  - `holds.user_id` and `bookings.user_id` are NOT NULL (migration 0003).
  - The seed gives every invented booking guest an account.
  - Auth (stage 4) is built before the booking APIs (steps 12 and 13).
  - Lookup by reference plus email becomes view only (A-48).
  - Cut line, in order: My bookings page, home page extras, promo usage caps. Sign-up can no longer be cut.

## D-25 Migrations stop rather than guess

- Chosen: migration 0003 checks for holds or bookings without an account and stops with instructions instead of altering the column.
- Why: there is no correct owner to invent for existing rows. On a development database the fix is to rebuild it; production data would need an agreed backfill plan. A test proves the migration refuses such rows.

## D-26 Hold creation keeps the locked part as short as possible

- Chosen: `create_hold` runs in a fixed order: date and line rules (no database), then room types, rate plans and rates (plain reads), then `lock_and_check`, then price and insert. The caller commits straight after.
- Why: a bad request is rejected without taking any lock, and rates are not stock, so they do not need the stock lock. Only "check stock, write hold" happens while other bookings for those nights wait.
- Guest details and release lock only the hold row (`SELECT ... FOR UPDATE` on the hold), so a double click on the same hold runs one request after the other.
- Release does not take the allotment locks: it only frees stock, so a check running at the same moment can at worst see slightly less stock than there is, never more.
- Ownership: every hold lookup filters by the signed-in account; another account's hold is "not found" (A-43). A test proves this, and removing the filter makes it fail.

## D-27 Confirmation returns an outcome instead of raising when money was taken

- Chosen: `confirm_booking` returns either a confirmed booking or a failure code with the payment marked `refund_pending`. The caller commits in both cases. It raises only when nothing should be saved (another account's hold, a payment for another hold, a payment that never went through, a lock timeout).
- Why: when the provider has taken money but no booking can be made, the refund mark must survive. An exception would roll the transaction back and lose it.
- Rules (from the brief and A-50): an active hold, or an expired hold whose stock is still free, is confirmed; an expired hold whose stock is gone fails. The same payment twice returns the same booking (double submit); a different payment for an already-paid hold is refunded.
- Locking: allotment rows first, then the hold or booking row, the same order as every other writer (D-21). Hold and payment are reloaded after the locks, since they may have changed while waiting.
- Booking references: each insert attempt runs in a savepoint, so a duplicate reference only undoes that attempt and the next random reference is tried (D-14). A test forces a collision.
- Cancellation: allotment rows, then the booking row; `sold` goes down on every night, the payment is marked for refund, and cancelling twice is harmless.

## D-28 Migration 0004: one succeeded payment per hold

- Found: the step 6 tests showed that the payment index from migration 0001 (at most one payment per hold in succeeded, refund_pending or refunded, from A-29) refused to record the refund that A-50 requires for a second payment from another browser tab.
- Chosen: the partial unique index now covers only `status = 'succeeded'`, the payment that paid for the booking. One booking per hold is still guaranteed by the unique `bookings.hold_id` and `bookings.payment_id`.
- Why a new migration, not an edit of 0001: 0001 is already merged and applied; migrations are never rewritten once shared.

## D-29 Concurrency is tested with real threads against real Postgres

- Chosen: `tests/integration/test_concurrency.py`. Each simulated guest runs in its own thread on its own database connection; a barrier releases them at the same instant. Each scenario runs 5 rounds by default (`CONCURRENCY_ROUNDS`), and after each one a check confirms that `sold` never exceeds the web allotment, `sold` plus active holds never exceeds it, and `sold` equals the confirmed booking units on every night.
- Scenarios: 10 guests for the last unit (hold only, and the full flow to a booking); a 3-night stay with one tight night, including guests who avoid that night; an expired hold's owner racing new guests; the same payment submitted 10 times; two payments from two tabs; mixed-room bookings in opposite line orders; cancelling the last unit while others book.
- Evidence they have teeth: 450 of 450 passed over 50 rounds. With `FOR UPDATE` removed, 27 of 45 failed across 6 scenarios. The expired-hold race went both ways over 40 rounds (owner 17, new guest 23), so both branches are exercised.
- Defence in depth, measured: double submits still produced one booking with only the hold row lock, or only the allotment lock. With both removed, the unique constraints refused the second booking.
- Honest limit: the deadlock test also passes without the `ORDER BY` in the lock query, because Postgres usually scans these rows in a consistent order anyway. The `ORDER BY` makes that order a guarantee rather than a property of the query plan.
- Rejected: SQLite for these tests (no row locks, so it cannot show the guarantee), and asserting on timings (flaky; the tests assert only on counts).

## D-30 Promo uses are reserved like stock, and quotes share the hold's code path

- Promo uses: `uses left = max_uses - used_count - active holds using the code`. Creating a hold locks the promo row (`SELECT ... FOR UPDATE`) and checks a use is left, so the second guest learns the code is used up before paying, not after. Confirmation counts the use (A-20); an expired or released hold gives it back lazily, exactly like stock. The database check `used_count <= max_uses` is the backstop.
- Lock order, extended for every writer: allotment rows, then the promo row, then the hold or booking row (D-21).
- Rejected: checking the cap only at confirmation (a guest could pay and then be refused for a reason they could not see).
- Quotes: `quote_stay` validates the request, checks the catalogue, applies the promo and prices the stay without locks or writes. `create_hold` calls it, then locks and writes. The price shown on the room page and the price held therefore come from one code path; a test asserts they are equal, with and without a promo.
- Test evidence: removing the use reservation, the use count, the "leave this hold out" rule or the promo row lock each makes tests fail. The race test gives every guest a different night, so the allotment lock cannot hide a missing promo lock.

## D-31 Payments: a gateway adapter, and no gateway call inside a transaction

- Adapter: `PaymentProvider` has `charge` and `refund`. `MockPaymentProvider` simulates success, decline and timeout, and like a real gateway remembers each idempotency key, so a repeated key returns the first result and never charges twice. A real gateway would be a second implementation selected by `PAYMENT_PROVIDER`.
- Checkout (`pay_for_hold`) runs as three short transactions: record a `pending` payment and commit; call the gateway outside any transaction; record the result (captured goes to `confirm_booking`). A slow gateway therefore never holds row locks while other guests wait, and the attempt is on record before any money moves. Because it owns its transactions, checkout takes a session factory, unlike the other services.
- Double clicks: the same key finds the earlier payment and returns its result (or "processing"). Three layers stop a second charge: the lookup after locking the hold row, the unique `payments.idempotency_key`, and the gateway's own key memory.
- After capture, if confirmation fails (D-27), the refund is processed straight away. A lock timeout while recording a capture is retried; if it keeps failing the payment stays `pending` with the money at the gateway, which a real system would settle from the gateway's records.
- Known limits, accepted for a simulation: the mock's key memory is per process; a mock timeout means "not charged" (A-62).
- Test evidence: removing the expiry check, the guest-details check, the refund after a failed confirmation, or the same-key lookup each makes tests fail. Ten parallel clicks with one key charge once and create one booking.

## D-32 Web layer: app factory, one error format, safe structured logs

- App: `create_app(settings, session_factory)` in `app/main.py`, run with `uvicorn app.main:create_app --factory`. Tests build their own app with test settings; nothing connects to a database at import time.
- Errors: one JSON shape for every failure. Domain errors map to fixed statuses in one table (`app/api/errors.py`). Validation errors keep FastAPI's field locations but never echo submitted values. Unexpected errors become a generic 500 inside the request middleware, so the response and the log line share the request id.
- Logs: JSON lines on stdout. The access line has the route template, not the real path or query string. Only reviewed fields are written; anything else passed to a log call is dropped. Errors log the exception type and code locations but not the message, because database errors can quote values such as emails. HTTP client libraries are kept at WARNING because they log full URLs. The request id is stamped on each record when it is created.
- Requests: one transaction per request via the `DbSession` dependency; `SessionFactory` for code that manages its own transactions.
- Dependencies (A-24, versions at least two weeks old): `fastapi` 0.162.0 and `uvicorn` 0.54.0 (plain, without the `[standard]` extras). Dev only: `httpx2` 2.16.0 for FastAPI's test client. The approved plan said `httpx`, but Starlette 1.10 deprecates using `httpx` in its test client in favour of `httpx2`; `httpx2` was checked in a clean environment before adopting it.
- Rejected: a logging library such as structlog (the standard library plus a small formatter is enough and easy to review), and Starlette's default 500 page (it would not carry the request id or the error format).

## D-33 Auth: database sessions, an HttpOnly cookie, three CSRF layers, one role dependency

- Sessions: a random 32-byte token in the cookie; the `sessions` table stores only its SHA-256 hash, so a copy of the table does not hand out live sessions. A new session at every login (no session fixation); logout deletes the row, so a stolen cookie stops working at once. Expired sessions are ignored lazily, like holds.
- Rejected: JWTs (cannot be revoked at logout without extra machinery, and need signing keys) and an auth framework (more to explain than the ~150 lines here).
- Passwords: argon2id with the library's recommended defaults; length rules only. An unknown email still costs one verification against a dummy hash, so response time does not reveal which emails have accounts.
- CSRF: SameSite=Lax; an Origin check on state-changing requests (through the Next.js proxy the Origin is the site's own, listed in `CORS_ORIGINS`); and a per-session token sent in `X-CSRF-Token`, compared in constant time. Login and sign-up have no session yet, so the first two layers cover them.
- Roles: one dependency, `require_user(role, team, gm)`, with ready-made `CurrentUser`, `GuestUser`, `StaffUser`, `GmUser`. Sign-up's request model forbids extra fields, so no request can set a role, team or GM flag.
- Tests use argon2 with minimal cost parameters (same algorithm) because the production defaults take about 170 ms per hash; production is unchanged.
- Test evidence: removing the CSRF check, the dummy verification, the extra-field ban, the session rotation, the Origin check, the token hashing or the team check each makes tests fail.
- Dependency: `argon2-cffi` 25.1.0.

## D-34 In-memory sliding-window rate limits

- Chosen: `SlidingWindowLimiter` keeps, per key, the times of recent attempts within the window: exact, with no burst at window edges. A lock makes it safe across threads; at most 10,000 keys, least recently used dropped first, so a flood of fake IPs cannot exhaust memory.
- Applied: per client IP on login and sign-up now, and on booking lookup and enquiries when those routes are built (one dependency, `limit_per_ip(name)`). Failed logins are also limited per account email (hashed), checked before the password is verified so a locked account cannot be guessed at all.
- Limits: per process and lost on restart, accepted because the brief allows in-memory limits; the deployment runs one instance with one worker (deployment.md), which the mock gateway already requires.
- Client IP: `request.client.host`, which uvicorn sets from X-Forwarded-For only for trusted proxy addresses.
- Rejected: `slowapi` (a library for about 60 lines of explainable code); fixed one-minute counters (allow double bursts at the boundary); Redis (out of scope).
- Test evidence: removing the per-IP login limit, the email lock check, the clearing on success, the email normalisation, the memory cap or the LRU ordering each makes tests fail.

## D-35 Public booking routes (step 12a)

- Routes: `GET /api/rooms` (search), `GET /api/rooms/{code}` (detail with a quote per active plan), `POST /api/quotes` (a whole selection with an optional promo), `POST /api/bookings/lookup` (view only, rate limited).
- Every price comes from `quote_stay`, so the room page, the summary and the hold agree; a test compares all three for one selection.
- The API speaks in codes and integer paise (A-84, A-89). A rate plan that is not on sale for the dates appears with no price and a reason code, so the page can say why.
- Lookup accepts the guest email or the account email, never puts the email in a URL, masks it in the answer and omits the phone. A wrong reference and a wrong email return the same 404. A malformed reference is rejected before the query; that is an optimisation only, since the query would return the same 404.
- Routes read the time from the app's clock (`Now` dependency, D-22), so API tests run against fixed dates.

## D-36 Signed-in guest routes (step 12b)

- The three-step flow: `POST /api/holds` (rooms and price, held 10 minutes), `PUT /api/holds/{id}/guest` (who is staying), `POST /api/holds/{id}/payment` (pay, with a required `Idempotency-Key` header). Plus `GET /api/holds/{id}` for page reloads, `DELETE /api/holds/{id}` to release, `GET /api/bookings/{reference}` for the confirmation page and receipt, and `POST /api/bookings/{reference}/cancel`.
- All use `GuestUser`: signed out is 401, staff 403, a missing CSRF token 403, another guest's hold or booking 404.
- Holds and bookings show prices read from the stored per-night rows, never recalculated, so a later rate change cannot alter a receipt (A-45). A test checks that the quote, the hold and the booking show the same price.
- A hold past its expiry is reported as `expired` (its stored status stays `active`; expiry is lazy).
- The confirmation page says whether online cancellation is still open (`can_cancel`, closing the day before check-in, A-51).
- The payment provider lives on the app state, so tests give each app a fresh mock.
- Honest note on payment: the sign-in check reads the session in a short read-only transaction that stays open while the gateway is called. It holds no row locks, so nothing waits on it; the rule in D-31 (no gateway call while holding locks) still holds.
- Test evidence: making the routes accept any signed-in user, reporting expired holds as active, always offering cancellation, making the idempotency key optional, or computing the receipt's taxable amount without the discount each makes tests fail.

## D-37 The daily export records events, so a day's file never changes

- Chosen: `GET /api/exports/bookings.csv?date=YYYY-MM-DD` lists, one row per booking line, the bookings confirmed and the bookings cancelled on that IST date. Each row's status and payment status are that day's event (`confirmed` and `paid`, or `cancelled` and `refund`).
- Why: the brief asks for the same file on re-download and for cancelled bookings to show as cancelled in the next export. Showing current status would rewrite past files whenever a booking is cancelled, and the reservation system could import a change twice. With events, every past day's file is fixed; a test downloads a day, cancels the booking the next day, and checks the first file is byte for byte unchanged.
- Rows are sorted by event time, event, booking, line; days are IST via `day_bounds`.
- Safety: spreadsheet formula injection is neutralised in free-text cells (name, email); phones are already limited to digits, spaces and a leading `+`. `Cache-Control: no-store` because the file holds personal data. Access is the reservations team and the GM only.
- Test evidence: using current status, current payment status, UTC days, no neutralising, an unstable order, any staff team, or a cacheable response each makes tests fail.

## D-38 My bookings and checkout prefill

- `GET /api/me/bookings` returns the account's bookings with a `section` (upcoming, current, past, cancelled) already worked out on the server, so the frontend's tabs need no date logic and agree with the server's idea of "today" in IST.
- Ownership, not email: the list is `bookings.user_id = this account`. A booking made by another account that names this account's email as the guest's is not shown, which is the brief's "do not attach old bookings automatically, since the email is unverified". A test proves it.
- Prefill: the hold response carries the account's name, email and phone as `guest_suggestion` until guest details are saved, so booking step 2 opens filled in without another request. The details remain editable, and saving them never writes to the account.
- Test evidence: matching bookings by email, dropping the current section, reversing the past or cancelled order, keeping the suggestion after details are saved, or allowing cancellation during a stay each makes tests fail.

## D-39 Admin inventory changes go through the same locks as bookings

- Routes: `GET /api/admin/inventory` (calendar: allotment, sold, held, available, blackout and rates per night), `PUT /api/admin/rates`, `PUT /api/admin/allotment`, `PUT /api/admin/blackouts`. Reservations team and GM only.
- Allotment: missing nights are inserted first (`ON CONFLICT DO NOTHING`), then every night is locked with `lock_allotments`, in the same order as bookings (D-21). Only then are sold and active holds counted, so a guest's hold cannot slip in between the check and the change. Any night below sold plus holds rejects the whole change with per-night details (brief rule).
- Blackouts lock the same rows and are refused while a guest holds rooms on those nights, because that guest would otherwise pay and be refunded (D-27). Confirmed bookings stay.
- Rates are upserted; holds and bookings keep their stored prices (A-45). Optional weekdays let one call set weekend prices.
- Every change writes one `audit_log` row with the old and new values.
- Concurrency: a new scenario cuts the allotment while 9 guests race for holds; over 40 rounds the admin won 26 times and the guests 14, and the stock invariants held every time.
- Test evidence: ignoring holds, skipping the row lock, dropping the physical cap, ignoring holds on blackout, ignoring weekdays, allowing past nights, admitting the events team or skipping the audit each makes tests fail.

## D-40 Admin promo codes

- Routes: `GET /api/admin/promos` (each code with uses, uses reserved by active holds, uses left and whether it works today), `POST /api/admin/promos`, `PATCH /api/admin/promos/{code}`. Reservations team and GM only.
- Code and percent never change once created: the update model forbids those fields, so reports and past bookings stay clear. Only the switch, end date and cap change, and only the fields sent are changed (`max_uses: null` removes the cap).
- Lowering the cap locks the promo row, the same lock a hold takes to reserve a use (D-30), then refuses any cap below uses plus reserved uses (A-105). A new concurrency scenario lowers a cap while 9 guests reserve uses on different nights; over 40 rounds the admin won 37 times and the guests 3, and uses plus reservations never exceeded the cap.
- Every create and every real change is audited with old and new values; an update that changes nothing writes no audit row.
- Test evidence: ignoring reserved uses, skipping the row lock, allowing 100%, failing to remove a cap, accepting a percent change silently, or auditing a no-op each makes tests fail.

## D-41 Classifier interface and the keyword classifier

- Interface: `EnquiryClassifier.classify(message, received_on) -> ClassificationResult` with category, fields, owner, confidence, draft template, backend, `is_fallback`, error, plus `complaint_signal`. Backends are chosen by `CLASSIFIER_BACKEND` from step 20.
- Fields are an `ExtractedFields` model with range checks, and `keep_plausible` drops dates outside a two-year window (and a check-out whose check-in was dropped). The LLM's fields go through the same checks in step 22.
- Extraction is rule-based (A-108): ranges, single dates, relative days, bare months, guests (adults plus children, people words in four languages, team of, couple, room for N), nights, budgets in lakh and crore, and a room type hint. Unrecognised text leaves fields empty, never guessed.
- Categories by keyword lists; weddings and offsites outrank room words because events mention rooms and nights; a complaint always wins. The complaint check uses problem words, so the injection sample does not alert the GM, and an injection phrase cannot suppress a real complaint's alert.
- Draft templates hold no numbers; prices and dates arrive only through placeholders filled in code (step 20).
- Honest measurement: 27 of 27 categories and every expected field are right on the sample file, but the rules were written from those messages, so that is in-sample. Separate tests use messages the rules were not written from; they exposed three gaps that were then fixed ("complain", "filthy", "cottage"). Two known limits are recorded in tests: a refund policy question raises a (cheap) GM alert, and events the lists do not know (a birthday) go to `other`.
- Test evidence: making the noun "complaint" alert, letting a booking outrank a complaint, letting room words outrank events, dropping the year rollover, reading "may" as May, not counting "a child", or keeping a check-out without its check-in each makes tests fail.
- No new dependency.

## D-42 The enquiry pipeline: save first, model proposes, code decides

- Order (brief): save the enquiry as pending in its own committed transaction; run the keyword classifier; call the model backend outside any transaction with only the message text; decide the lane in code; raise the GM alert; fill the draft in code; store everything. Any crash after saving marks the enquiry `failed` with an error code, and `run_pipeline` re-runs it (the retry action in step 21).
- Failure handling: a timeout or provider error uses the keyword result, labelled `is_fallback` with the error code; output still invalid after one retry also uses the keyword result and sends the enquiry to Unsorted; any unexpected exception from a provider library is treated as a provider error.
- Lanes: `decide_lane` is a pure function. Any of invalid output, confidence below the threshold, disagreement, category `other`, or missing required fields sends the enquiry to Unsorted, and the reasons are stored in `lane_reasons` so the inbox can show why.
- GM alerts: raised when the keyword check or the model sees a complaint, regardless of lane or confidence, so a complaint alerts the GM even with the model down. One alert per enquiry; a re-run does not add another. (A test first only counted alerts; a mutation showed a re-run would have failed on the unique constraint, so the test now also checks the re-run succeeds.)
- Drafts: placeholders filled from extracted fields and `quote_stay` (same price path as the website, never a promo). A value that cannot be worked out stays as a visible placeholder. The contact name is filled last, so a name like "{price_total}" is never expanded.
- Stub: `StubLLMClassifier` (backend name `stub`) echoes the keyword result or simulates timeout, provider error and invalid output. Step 22 moved it out of the app into `tests/fakes.py` as a test double (D-45).
- Test evidence: making the alert depend on the model, letting provider errors escape, losing a crashed enquiry, sending the contact name to the model, duplicating alerts on re-run, routing invalid output, treating keyword no-match as disagreement, leaving the name unfilled, or pricing sold-out dates each makes tests fail. The whole sample file is run through the pipeline with both backends and every expected lane and GM alert holds.

## D-43 Enquiry API: public form, inbox, detail and re-run

- Public form: `POST /api/enquiries` saves first and runs the pipeline in the request (D-42), then returns `201` with the reference only (A-122). It is rate limited per IP with its own limit, rejects unknown fields, and goes through the same Origin check as every other state-changing route. A model outage still saves and routes the enquiry with the keyword result.
- Inbox: `GET /api/enquiries` for any staff role (A-123), newest first, at most 200 rows, with a 140-character snippet and counts per lane plus pending and failed, so the frontend can show lane tabs without extra calls.
- Detail: `GET /api/enquiries/{reference}` shows the original message beside the extracted fields (brief), both classifier outputs, the lane reasons, the draft, the GM alert and the audit history with staff names. References are case-insensitive.
- Re-run: `POST /api/enquiries/{reference}/classify` runs `run_pipeline` again. The rule in A-125 lives in `enquiry_inbox.can_reclassify`, which counts audit rows with the staff actions `correct`, `reroute` and `reply` that step 21b writes.
- Classifiers sit on app state (`keyword_classifier`, `model_backend`) behind dependencies, so tests swap the model backend without touching the code path.
- Test evidence: removing the re-run guard, not counting a correction as staff work, opening the inbox to any signed-in user, or putting the form on another route's rate limit each makes tests fail.
- No new dependency.

## D-44 Staff actions: correct, re-route, reply, GM alerts and metrics

- Routes: `PATCH /api/enquiries/{reference}` (correct), `POST .../route` (re-route), `POST .../reply` (simulated reply), `GET /api/enquiries/metrics`, `GET /api/alerts` and `POST /api/alerts/{id}/ack`.
- Each action locks the enquiry row (`SELECT ... FOR UPDATE`) inside the request's single transaction, so two staff acting at once are applied in turn and the second sees the first's result. A concurrency test sends two replies at the same instant: exactly one is recorded, the other gets `already_replied`.
- States: actions need status `classified`. A pending or failed enquiry is refused with `not_classified` (re-run it first), and a replied one with `already_replied`. Migration 0007 adds the status `replied` and the reply columns, with a CHECK that the text, time, sender and status are set together.
- Corrections send only the changed fields (null clears one). The merged fields go through `ExtractedFields` and `keep_plausible`; anything they would reject or drop is refused with the field names, rather than silently changed. One audit row per changed value, under action `correct`, so the history shows exactly what a person changed and the original model output stays beside it.
- `lane_reasons` stays as the pipeline's record after a correction or re-route, so "sent to Unsorted" in the metrics counts the pipeline's decisions, not the current lane.
- Anything staff put in the complaint lane (by correction or re-route) raises a GM alert if the enquiry has none, keeping "every complaint alerts the GM" true however it got there.
- Replies: the placeholder check matches only the template's placeholder names, so other braces in a reply are allowed. The audit row records the length, not the text, and the log line carries only the reference (added to the logging allow-list; a reference is not personal data).
- Inbox counts per lane are now open work (classified, not yet replied), plus a `replied` count.
- Metrics return each rate as count, out of, and value, so a small sample is visible. The median uses Postgres `percentile_cont`.
- Test evidence: allowing a second reply, skipping the placeholder or plausibility checks, re-routing to complaint without an alert, not rebuilding the draft, acknowledging an alert twice, letting non-GM staff acknowledge, dropping the row lock, counting any correction as a category correction, or dropping the reply CHECK from migration 0007 each makes tests fail. (Alembic does not compare CHECK constraints, so a database-level test covers it.)
- No new dependency.

## D-45 The Gemini backend: one adapter, standard library, schema-checked

- `app/classifiers/gemini.py` implements the classifier interface (D-41) with one `generateContent` POST to Google. `registry.get_model_backend` builds it when `CLASSIFIER_BACKEND=gemini`; `keyword` (the default) calls no model. Swapping provider means one new class and one registry branch.
- Standard library only (A-132). The transport is a plain function `(url, headers, body, timeout) -> bytes`, swapped for a fake in tests. Real Google is never called from tests; the real transport is tested against a local HTTP server for success, 429, 500, a slow answer and a refused connection.
- Request: fixed system instructions; the guest message in a separate user part, labelled as data between markers, with the received date (A-133). JSON mode with a response schema: category from a fixed enum, confidence, and the extraction fields with room type codes as an enum. Temperature 0, at most 512 output tokens.
- Response checks (A-135, A-136): parsed and checked in code, never trusted because of the schema. Fields pass through `ExtractedFields` and `keep_plausible` one value at a time, so one bad value is dropped and the rest of the proposal is kept. The draft template is chosen in code from the category; the model never writes reply text. `complaint_signal` stays with the keyword check, so the GM alert never depends on the model.
- Failures (A-134, A-137): timeout, HTTP errors including 429, and network errors become `timeout` or `provider_error` with no retry. Errors carry only the status or exception type: never the response body (it may echo our request) and never the key. The key is a `SecretStr` in settings, sent in the `x-goog-api-key` header, not the URL, and hidden from `repr`.
- Prompt injection, honestly: a model that obeys "mark this as a complaint" can at worst raise a GM alert the GM dismisses. It cannot change a price (prices come from `quote_stay`), give a discount (drafts never use promos), send anything (replies are staff-only), or hide a complaint (the keyword check alerts on its own, and disagreement sends it to Unsorted). Tests cover each case with a model that obeys.
- The stub left the app: it now lives in `tests/fakes.py` as a test double, and `CLASSIFIER_BACKEND=stub` is rejected.
- Not verified from this workspace: a live call to Google (the workspace cannot reach it). The README has a one-line live check; accuracy on the sample file is measured in step 23.
- Test evidence: removing the retry, retrying twice, skipping the confidence range or finish reason check, skipping the plausibility check, putting the key in the URL, chaining the provider error, passing the raw error text on, dropping the startup key check, or sending contact details each makes tests fail. Dropping the unknown-key filter does not, because `ExtractedFields` forbids extra keys as well: two layers on purpose.
- No new dependency.

## D-46 Evaluating the classifier on the sample file

- One source of rules: `propose()` in the pipeline holds steps 2 to 5 (keyword classifier, model call with fallback, lane in code, the GM alert rule in `complaint_sources`). `run_pipeline` and `python -m app.eval_enquiries` both call it, so the evaluation cannot drift from what production does.
- The command is a developer tool, not a feature: it runs in memory, prints markdown and can write it to a file (A-138). It reports per enquiry and in total: category, lane, required and false GM alerts, fields right, fallbacks and median time per enquiry for a model.
- The only gate is a missed required GM alert (exit 1). Everything else is reported for people to judge, with each figure as a count out of a total (A-140).
- Honesty: the keyword rules were written from these messages, so its 27 of 27 is in-sample and the report says so. Gemini was not tuned on them, so its report is the fairer measure; it is run with the owner's key because this workspace cannot reach Google.
- `seed --classify` uses `classify_pending`, which runs the real pipeline on every pending enquiry, oldest first, paced for model limits. The demo inbox then shows lanes, drafts and GM alerts.
- A missing key gives a one-line message and exit code 2 from both commands, not a traceback.
- Test evidence: making the gate never fail, letting every lane pass, scoring alerts from the category instead of the shared rule, pausing before the first call, leaking message text into the report, dropping the model from the shared alert rule, or re-running already classified enquiries each makes tests fail.
- No new dependency.

## D-47 AI eval against actual eval on real enquiries

- Proposed by the project owner: keep what the AI decided and what a person confirmed, so AI accuracy is measured on real enquiries, not only the sample file (D-46). The share of corrections alone is not enough, because an enquiry nobody corrected is not necessarily one the AI got right; someone has to say so.
- `ai_eval` (JSONB) is written only by the pipeline, at classification: category, lane, fields, confidence, backend, `is_fallback`. Staff actions never touch it; a re-run, allowed only before anyone has acted (A-125), replaces it.
- `POST /api/enquiries/{reference}/verify`, GM only (A-145): records `actual_eval` (category, lane, fields as they stand) with `verified_by` and `verified_at`, and audits `verify` with both records. A CHECK keeps the three columns set together. A reply is not an approval (A-146).
- Approval fixes the classification (A-149): "verify" joins the staff decisions that block a re-run, and corrections and re-routes check `_require_unverified`.
- Metrics gain `awaiting_approval` and `ai_accuracy` per backend (A-150): category, lane and fields matches as count out of approved. Keyword fallbacks are labelled "keyword (fallback)", so the model is not credited or blamed for answers it did not give. The comparison is a small pure function with its own test.
- Two measures, one story for the TDD: the sample-file report is the test before go-live; `ai_accuracy` is quality in production, as judged by the GM.
- Trade-off: accuracy needs the GM to approve enquiries; until they do, `awaiting_approval` shows how much is unmeasured.
- Test evidence: letting other staff approve, allowing corrections or re-runs after approval, treating a reply as approval, letting a correction rewrite `ai_eval`, counting every approved enquiry as right, crediting fallbacks to the model, approving a pending enquiry, or dropping the CHECK from migration 0008 each makes tests fail.
- No new dependency.

## D-48 Frontend foundation

- Scaffolded with the official `create-next-app@16.4.5` (App Router, TypeScript, ESLint, no Tailwind, no `src/`), keeping its defaults `cacheComponents` and `partialPrefetching`. Versions are pinned exactly (A-151). New dev dependencies, each with a reason: `openapi-typescript` 7.13.0 (types from the API schema, A-153) and `@playwright/test` 1.63.0 (end-to-end tests, A-156). No new runtime dependency beyond Next.js and React. `npm audit` reports 0 vulnerabilities in production dependencies; one moderate advisory sits in the dev-only lint toolchain and is left until `eslint-config-next` updates it.
- Same-origin API (A-152): `/api/*` is rewritten to `API_URL`. Checked through the proxy: the session cookie passes through, `/api/auth/me` returns the CSRF token, logout works, and a foreign Origin is still refused by the backend.
- `API_URL` is required for production builds and starts. Found while testing: Next.js fixes the rewrite target at build time, while server components read `API_URL` when the server runs. A build without it would quietly proxy to localhost while the home page still worked. `next.config.ts` now refuses to build or start in production without it.
- Types: `python -m app.export_openapi` writes `frontend/lib/openapi.json` without a database, and `npm run api:types` turns it into `lib/api-schema.d.ts`. A backend test fails when the committed schema is out of date, so an API change cannot silently break the frontend.
- One error format end to end: `lib/errors.ts` turns any failed response (even a non-JSON one) or an unreachable backend into an `ApiError` with the backend's code, message, details and request id. The browser client (`lib/api.ts`) keeps the CSRF token in memory only and recovers it from `/api/auth/me` after a reload.
- Server components read public data straight from the backend (`lib/server-api.ts`); the room list is streamed inside `<Suspense>`, so a build never needs the backend and a slow or failed API call never blocks the page. With the backend stopped, the home page still returns 200 and says the rooms could not be loaded.
- Look (A-154, A-157): tokens from the estate (mist, shade-tree green, leaf, coffee-cherry red reserved for the main action), a Palatino-style serif for headings and the system sans for text, both system fonts (nothing downloaded). The one bold element is an SVG of terraced coffee rows under a band of mist; the rest is quiet. Rooms are a ruled list, not a card grid.
- Quality floor: skip link, visible focus, `lang="en-IN"`, reduced motion respected, no horizontal scroll at phone width, loading, empty, error and not-found states.
- To note for deployment (step 32): through the proxy the backend sees the frontend server's address, so per-IP rate limits need uvicorn's `--forwarded-allow-ips` set to the frontend, as `deployment.md` already describes.

## D-49 Sign-in on the frontend

- One `SessionProvider` in the layout asks `GET /api/auth/me` once per page load. It holds the account and restores the CSRF token, which lives in memory only. The header's account area and the `RequireSignIn` guard read from it. Nothing about the session is kept in browser storage; the session cookie is HttpOnly and set by the backend.
- `/login` and `/signup` are client forms. The backend signs a new account in straight away, so sign-up lands signed in. Errors from the backend's one error format are placed where they belong: field codes next to the field, `email_taken` with a link to log in that keeps `next`, `rate_limited` with the wait from `Retry-After`, and an unreachable backend with its own message.
- Return after login (D-24, A-158): `lib/next-path.ts` accepts only same-site paths. Tested with `https://evil.example/`, `//evil.example/` and `/\evil.example`.
- `RequireSignIn` sends a signed-out visitor to `/login?next=<here>` and can require a role (guest for booking, staff for the inbox). It only spares a page that would fail; the API checks every request itself.
- `/privacy` is a short notice for the DPDP Act (A-161), linked from the consent checkbox and the footer.
- End-to-end tests run against the real backend started with relaxed rate limits, because every test request reaches the backend from the same address. The 429 and backend-down messages are tested by intercepting the request in the browser.
- No new dependency.

## D-50 Rooms, availability and prices on the frontend

- The search lives in the address: `/rooms?check_in=&check_out=&guests=&sel=PLV.BB.1.4,DLX.RO.1.1` (room type, plan, rooms, guests per line). Reloads, sharing, the back button and the return after sign-in (A-171) all keep it. Choosing rooms updates the address with `history.replaceState`, which Next.js supports without asking the server again; `router.replace` would have re-rendered the page on the server, about six API calls, on every click.
- `/rooms` is a server component inside `<Suspense>`: `GET /api/rooms` for the dates, then every room type's `GET /api/rooms/{code}` in parallel for its plans and prices. "Rooms left" comes from availability; the per-plan price is for one room and is shown even on sold-out dates, so the page marks a type sold out from availability and caps the rooms you can choose at what is left. The backend checks again when the hold is made.
- The choice is priced by `POST /api/quotes`, debounced by 250 ms and cancelled when superseded (A-166). Each answer is tied to the exact choice it priced, so a stale total is never shown or booked while a new one is on its way.
- "Today" for the date picker comes from the visitor's clock when the page runs (`useSyncExternalStore`), in India's time zone. The home page is pre-rendered, so reading the clock at render time would have frozen "today" at the build date; Next.js refused that at build, which is how it was found.
- Under Next.js's `cacheComponents`, components that read the address (the header's account link, `RequireSignIn`) sit inside `<Suspense>` boundaries.
- On a phone the summary is far down the page, so a bar fixed to the bottom shows the rooms chosen and the total, with a link to the summary.
- Known limitation: the room page streams, so for an unknown room code the status is already 200 when the API says 404. Next.js still shows the not-found page and marks it `noindex`; a real 404 status would need the page to wait for the API before sending anything.
- Tests: end-to-end tests derive the seeded sold-out weekend from the same rule as the seed (first Friday 14 or more days ahead) instead of fixed dates, so they keep passing on later days. Streamed content can exist twice for a moment (a hidden copy before it is swapped in), so tests look at visible elements.
- No new dependency.

## D-51 The booking flow on the frontend

- "Book these rooms" sends a signed-out visitor to log in with the `/rooms` address as `next` (D-24, A-171). Signed in, it calls `POST /api/holds` with the lines and any promo code and opens `/book/[holdId]`. Staff accounts see the button disabled and why. A `not_available` answer (someone booked the last room a moment ago) asks the guest to refresh and see what is left.
- `/book/[holdId]` runs in the browser behind `RequireSignIn role="guest"`. It shows a countdown from `expires_at` (A-167); the guest step is prefilled from the account (`guest_suggestion`) and saved with `PUT /api/holds/{id}/guest`, with the backend's field codes shown under the right field; the pay step appears only once the guest's details are saved. A hold already paid for opens its booking instead.
- Payment (A-168): one key per attempt from `lib/payment-key.ts`, sent as `Idempotency-Key`, and forgotten only on a final answer. Confirmed opens the booking; declined and timed out (in this mock, "not charged") allow a new attempt with a new key; processing keeps the key and offers "Check payment status"; refunded or refund pending (paid after the rooms were released) shows the backend's explanation. `hold_not_active` turns the page into the expired view.
- Expired or released holds show what happened and "Check these rooms again", which rebuilds the `/rooms` address from the hold's own lines, so the guest's choice is not lost.
- `/bookings/[reference]` is the confirmation: reference, guest, payment status and reference, the stay and the price breakdown, all from `GET /api/bookings/{reference}`. The hold and booking APIs return codes, so room and plan names are looked up from the public catalogue (`lib/catalogue.ts`); if that fails the codes are shown.
- Promo (A-170 amended): the field is in the rooms summary, because the backend accepts a code only when the hold is created. A bad code shows the backend's reason and the price stays visible without it.
- End-to-end tests cover the whole flow against the real backend: book and pay; signing in mid-way and returning to the same choice; a decline, then success; a timeout, then success; a double click sending one key; the same key sent twice returning the same booking; an expired and a valid promo code; cancelling and offering the rooms again; the countdown running out (with Playwright's clock, so the page's view is tested, not the server's); staff unable to book; a booking page needing sign-in. Each booking test books its own Thursday, which avoids every seeded special date, and the database is reseeded before a run.
- No new dependency.

## D-52 My bookings, lookup and cancellation on the frontend

- `/my-bookings` (guests) shows the backend's sections as tabs (Upcoming, Current, Past, Cancelled) with counts; the frontend does no date logic, so the tabs agree with the server's idea of today in India (D-37). Each tab has its own empty state, and an account with no bookings gets "Find a room" instead of empty tabs. The tabs follow the ARIA tab pattern (`tablist`, `tab`, `tabpanel`).
- Cancel (A-174) lives on `/bookings/[reference]`, asks for a second click in the page, and calls `POST /api/bookings/{reference}/cancel`; the page then shows the cancelled booking and that a full refund is in progress. When the backend says `can_cancel` is false, the page explains that online cancellation closes the day before check-in and to contact the resort.
- `/find-booking` (A-48, now confirmed) is public and view only: the backend's summary with the email masked, one message for a wrong reference or a wrong email (the backend's), the wait from `Retry-After` when rate limited, and a "log in" link that returns to the booking's page for cancelling.
- End-to-end tests make their bookings through the API (`bookViaApi`) on their own Thursdays, so they do not depend on the booking screens or on each other.
- No new dependency.

## D-53 The public enquiry form

- `/enquire` posts to `POST /api/enquiries`, which saves first and classifies after (D-42). The form checks the basics (name, an email or a phone, a message within 2,000 characters, consent) and shows a live character count; the backend's codes (`invalid_name`, `invalid_email`, `invalid_phone`, `contact_required` on both contact fields, `empty_message`, `message_too_long`, `consent_required`) go under the matching field, and `rate_limited` shows the wait.
- Success shows only the reference and the backend's thank-you message (A-122, A-178). "Send another enquiry" gives a fresh, empty form.
- Prefill (A-176): the session loads after the page, so the form is keyed on the account and picks up the guest's details when they arrive; the message is held in state and is not lost.
- Ways in: "Enquire" in the header, the home page's Visit section, and the sold-out message on the rooms page.
- Found while testing: Next.js 16 keeps the page just left mounted but hidden (React `Activity`), so going back is instant. Tests that follow a navigation look at visible elements only.
- End-to-end tests check that a sent enquiry reaches the staff inbox through the API with the message exactly as written.
- No new dependency.

## D-54 Admin screens

- `/admin` (inventory, promo codes, daily export) sits behind `RequireSignIn role="staff"` and an `AdminGate` that lets in the reservations team and the GM (A-180), matching the backend's `require_user(role="staff", team="reservations")`, which also admits the GM. `/admin` redirects to the inventory.
- Inventory: a table with room types as rows and nights as columns. Each cell shows rooms left out of the web allotment, sold and held, and the price for the chosen plan; blackouts are marked "Closed"; Friday and Saturday nights are shaded. The table scrolls sideways inside its own box with the room names fixed on the left, so the page never scrolls sideways on a phone. Plan names come from the public catalogue, with codes as the fallback.
- Three change forms (price with optional weekdays, web allotment, blackout or reopen) call the existing endpoints and reload the grid. Refusals show the backend's message and, for allotment and blackout, each blocking night (for example "8 sold and 0 held, so at least 8"). Blackouts ask for a second click (A-183).
- Promo codes: a table with uses, reserved uses, limit and whether the code works today, with the reason when it does not (switched off, not started, ended, limit reached). Each row can be switched on or off and have its end date or limit changed; a limit below uses plus reserved shows the backend's minimum. New codes are created below the table.
- Daily export: a date (today in IST by default) and a plain download link to `/api/exports/bookings.csv`, so the browser saves the file the backend names (A-185).
- End-to-end tests prove the screens reach the system, not only the API: a price set in the admin grid is the price the guest is quoted; a blackout makes the guest's rooms page sold out and reopening restores it; a new promo code discounts a quote and stops working when switched off. They use far-off Tuesday and Wednesday nights, a different week for desktop and phone, so they never meet another test's bookings.
- No new dependency.

## D-55 The staff inbox

- `/staff` (all staff) has three sections: Inbox, GM alerts and Metrics, with a "Staff" link in the header. The inbox tabs are the five lanes plus Pending, Failed and Replied, with the backend's counts; the open tab lives in the address (`?tab=`), and each team starts on its own lane (A-186).
- The enquiry page puts the message, as written, beside what was understood (category, lane and team, confidence, backend and any fallback, the extracted fields), says why an enquiry is in Unsorted, and can show what the keyword check and the AI each said. GM alerts and failed classifications are flagged at the top.
- Actions appear only when the backend allows them (`can_act`, `can_reclassify`, `can_verify`): reply with the code-built draft (placeholders block sending, A-188), correct the category or fields (only changed values are sent, A-189), move to another lane, run the classification again, and, for the GM, approve (A-190). Each action returns the updated enquiry, so the page shows the result, including the history line, without another request.
- GM alerts list open alerts first with a link to each enquiry; only the GM can acknowledge. Metrics show counts and rates for a date range (last 30 days by default) and AI accuracy against the GM's approvals, with how many enquiries are still awaiting approval (A-192).
- End-to-end tests send their own enquiries through the public API, so they never depend on each other or on the seeded ones. The backend for these tests runs with `CLASSIFIER_BACKEND=keyword`, so routing is deterministic and a `.env` that chooses Gemini cannot make the tests call it; the README command sets it, and reseeds with `--classify` so the demo inbox is classified.
- No new dependency.

## D-56 uvicorn's keep-alive timeout behind a proxy

- Seen in a local end-to-end run: two tests failed when the Next.js proxy logged `read ECONNRESET` on requests to the backend. The proxy keeps connections to uvicorn open and reuses them; uvicorn closes an idle connection after 5 seconds by default. When the proxy reuses a connection at the moment uvicorn closes it, that request fails.
- Reproduced by shortening uvicorn's idle timeout to 1 second and running the suite with 10 workers: 8 resets and failed tests. With `--timeout-keep-alive 65`, three runs under the same load had no resets.
- Every documented start command (README, end-to-end command, `deployment.md`) now passes `--timeout-keep-alive 65`: longer than the proxy's idle time, and the usual figure behind load balancers, which keep connections for about 60 seconds.
- Not explained: in one of those runs a cancellation test failed once without any reset. It did not happen again in a full run or on its own, so it is noted here rather than claimed fixed.
- No code change and no new dependency.

## D-57 Frontend refinement: photos and a design language

- Photos reach the site as files, not hotlinks. `frontend/scripts/fetch-photos.sh` downloads 21 free-licence Unsplash photos once into `frontend/public/images/`, and they are committed. The site then depends on no third party at runtime, and guests' browsers never contact Unsplash, which keeps their IP addresses with us (DPDP). The script checks each download is a JPEG and keeps files already present.
- `lib/photos.ts` imports every photo statically, so `next build` fails if one is missing, and `next/image` knows each size, makes a blurred placeholder and serves resized WebP or AVIF copies. Sources, authors and licences are in `docs/PHOTO_SOURCES.md` (A-193 to A-198).
- The one bold element is the home page hero: a full-width photo of a coffee plantation in fog that ends in the outline of the hills (the existing SVG, redrawn in the page colour), so the photo settles into the page. Everything else stays quiet.
- Room photos have a low arched top, like an estate-house window; the arch is used for room photos only. The home page lists rooms and villas in alternating rows of photo and text; the rooms page has a thumbnail per room; each room page has one large photo and two smaller ones. Login, sign-up, enquiry and find-a-booking pages have a photo beside the form on wide screens, left out on phones. The not-found page has a photo.
- Type: headings use Tiro Kannada, drawn for Kannada, the language of Karnataka, with a matching Latin, in one regular weight; body text stays in the system sans-serif. This replaces the Cormorant Garamond named in the plan, which is the usual choice for a "luxury" site; the package is `@fontsource/tiro-kannada` (OFL licence), self-hosted, so the build needs no network.
- Colours keep the estate palette (mist, canopy, leaf, coffee-cherry red for the one main action) and add roasted bark (`#2b231d`) for the footer.
- No fake buttons: no new button was added. Every new clickable element is a link to an existing page, and photos are not clickable. A new end-to-end spec (`links-and-images.spec.ts`) visits every public page, follows every visible link (a 4xx or 5xx fails it, as does an in-page link without a target), checks every visible photo loads and has alt text, and checks each room page shows its three photos labelled as samples.
- `frontend/types/images.d.ts` declares image imports for TypeScript. Next.js puts that in `next-env.d.ts`, which is generated by `next dev` or `next build` and not committed, so CI's typecheck (which runs before the build) failed on every photo import without it.
- New dependency: `@fontsource/tiro-kannada` 5.3.0, for the heading font without a network fetch at build time.

## D-58 Hosting on Railway

- Prepared, not deployed: a live copy was not required for the submission, so the setup below is in the repository and documented in `deployment.md`, but has not been run on Railway.
- One Railway project with three services: `frontend` (public domain), `backend` (private network only) and Railway's Postgres. Chosen over free hosts (Vercel or Render with Neon) because free tiers sleep after inactivity, making a reviewer's first click take up to a minute, and because a public backend behind a host whose proxy addresses change gives no safe way to trust forwarded client IPs. Railway costs about 5 US dollars a month.
- Each service is built from its own Dockerfile (`backend/Dockerfile`, `frontend/Dockerfile`), so the build is the same on any host, with build and deploy settings in `railway.json` beside it. Both images run as an unprivileged user.
- The backend runs one instance with one worker (in-memory rate limits and payment idempotency), listens on `::` for Railway's private network, and keeps uvicorn's keep-alive at 65 seconds (D-56). Migrations run as Railway's pre-deploy command, so a failed migration stops the deploy and the old version keeps running. Railway waits for `/health` before switching traffic.
- The frontend reaches the backend at `http://backend.railway.internal:8000`. `API_URL` is passed at build time (for the `/api/*` rewrite) and at runtime (for server-side requests). The build does not need the backend to be reachable: checked by building with the API down and starting it afterwards.
- Client IPs: `FORWARDED_ALLOW_IPS=*` on the private backend (A-199, deployment.md section 8). Checked locally that the Next.js proxy passes `X-Forwarded-For` on unchanged.
- Demo data would be loaded by hand (A-200), never on deploy, because `--reset` empties every table.
- Checked here without Docker (Docker Hub is not reachable from the build machine): the backend image's steps in a clean Python 3.12 environment (install, migrate, seed, serve, `/health`), and the frontend's in a clean copy of its build context (`npm ci`, build, start, pages and resized images served). Not checked here: the `::` bind (no IPv6 on this machine; `HOST` can override it) and the images themselves.
- No new dependency.


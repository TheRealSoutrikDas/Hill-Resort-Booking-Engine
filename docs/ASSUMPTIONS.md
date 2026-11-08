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
| A-07 | AI | LLM provider and model. Settled in A-130. | Confirmed |
| A-08 | Pricing | GST per room per night on the value actually charged (after promo discount): at or below Rs 7,500 is 5%, above is 18% (Notification 15/2025-CT(Rate), from 22 Sep 2025). Exactly Rs 7,500 is 5%. No exempt slab below Rs 1,000. Breakfast on the B&B plan is part of the room value. Discount and GST are rounded half up to the paise, once per unit-night. Threshold and rates are config values. | Confirmed |
| A-09 | Seed | Values in `backend/app/seed/plan.py`: Deluxe Room 30, Estate View Room 22, Family Suite 12, Plantation Villa 8, Pool Villa 4; weekday room-only rates Rs 6,000 / 8,000 / 10,000 / 14,000 / 20,500, Fri and Sat nights +20%, 20 Dec to 5 Jan +40% (year average Rs 9,468); Bed and Breakfast +Rs 1,200; web allotment 25% (8/6/3/2/1); sold-out weekend about 2 weeks ahead, Family Suite with 1 unit left about 1 week ahead, 3 blackout nights about 5 weeks ahead; WELCOME10 valid, MONSOON15 expired, COFFEE20 cap reached; 40 bookings (8 past, 28 upcoming, 4 cancelled); 1 demo guest, 2 staff, 1 GM, plus one guest account per invented booking guest (37) because booking requires an account (A-43). | Confirmed |
| A-10 | Export | Brief's column layout, one CSV row per booking line, plus a `line_number` column. `booking_id` repeats across a booking's lines; amount and tax columns are per line. | Confirmed |
| A-11 | Auth | Browser calls go through Next.js rewrites (`/api/*` to FastAPI), so the session cookie is first-party. | Confirmed |
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
| A-34 | Seed | Superseded by A-78: demo accounts get documented passwords; booking-guest accounts keep an unusable marker. | Changed |
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
| A-70 | Auth | Passwords are hashed with argon2id (`argon2-cffi` defaults) and upgraded at login if the parameters change. | Confirmed |
| A-71 | Auth | Passwords are 10 to 128 characters, with no composition rules. | Confirmed |
| A-72 | Auth | Sessions live in the database with only a hash of the token stored; they expire 7 days after login (`SESSION_TTL_HOURS`); every login creates a new session and logout deletes it. | Confirmed |
| A-73 | Auth | The session cookie is HttpOnly, SameSite=Lax, Path=/, host-only and Secure (`SESSION_COOKIE_SECURE`, on by default; browsers accept it on localhost). | Confirmed |
| A-74 | Auth | CSRF in three layers: SameSite=Lax; state-changing requests from an Origin not in `CORS_ORIGINS` are refused; signed-in state-changing requests need the session's token in `X-CSRF-Token`. | Confirmed |
| A-75 | Auth | Sign-up creates guests only; name, email, password and consent are required (consent time and version stored), phone optional; the guest is signed in at once; no verification or reset; an already registered email is reported plainly, with rate limits as protection. | Confirmed |
| A-76 | Auth | Login gives one message for a wrong email or password, and an unknown email still costs a full verification against a dummy hash. | Confirmed |
| A-77 | Auth | Booking routes are guest-only; staff routes need the staff role (and optionally a team, which the GM also passes); GM routes need the GM flag. Not signed in is 401; not allowed is 403. | Confirmed |
| A-78 | Seed | The four demo accounts get documented passwords (README); the 37 booking-guest accounts cannot log in. | Confirmed |
| A-79 | Rate limits | Login 20 per 15 min per IP; failed logins 5 per 15 min per email; sign-up 5 per hour per IP; booking lookup 10 per 15 min per IP; enquiries 10 per hour per IP. All settings. Refusals are 429 with Retry-After. | Confirmed |
| A-80 | Rate limits | The per-email login limit counts failed attempts only, keyed by a hash of the email, and is cleared by a correct login. While it is reached, even the right password is refused. | Confirmed |
| A-81 | Rate limits | The client IP comes from uvicorn's proxy-header support, which believes X-Forwarded-For only from addresses in `FORWARDED_ALLOW_IPS` (default: this machine only). Production sets it to the proxy's address. To be verified with the frontend. | Confirmed |
| A-82 | Deployment | Rate limits (and the mock gateway's key memory) are per process, so the backend runs as one instance with one worker (deployment.md). | Confirmed |
| A-83 | Logging | A refused attempt is logged with the route and limit name only, never the IP or email. Alternative offered: also log a daily-salted hash of the IP so attacks can be traced to one source. | Confirmed, option (a) |
| A-84 | API | The API identifies room types, rate plans and promo codes by code (`DLX`, `RO`, `WELCOME10`), never by database id. | Confirmed |
| A-85 | API | Room search without dates lists room types only. With dates and a guest count it adds units available, whether the guests fit one room, and the lowest total for one room on any active plan. | Confirmed |
| A-86 | API | Lookup is POST with a JSON body and accepts the booking's guest email or the booking account's email. It returns a view-only summary (no phone, email partly masked). A wrong reference and a wrong email give the same 404. | Confirmed |
| A-87 | API | Payment returns 200 with a status once the gateway has been called; refusals before any charge are errors; `Idempotency-Key` is a required header. | Confirmed |
| A-88 | API | Room photos are static frontend files named by room code, with sources in `docs/PHOTO_SOURCES.md`; the API carries no photo data. | Confirmed |
| A-89 | API | All amounts in responses are integer paise; the frontend formats them. | Confirmed |
| A-90 | Export | Only the reservations team and the GM may download the export (it holds every guest's contact details). | Confirmed |
| A-91 | Export | Each row is the day's event: confirmations on their IST date, cancellations on theirs, both rows when they happen the same day. A day's file never changes once the day is over. | Confirmed |
| A-92 | Export | `booking_id` is the booking reference; `room_type` and `rate_plan` are codes. | Confirmed |
| A-93 | Export | `payment_status` is the event (`paid` or `refund`), not the payment's current state; `payment_reference` is the gateway's. | Confirmed |
| A-94 | Export | Dates are ISO; `created_at` is the confirmation time in IST with its offset. | Confirmed |
| A-95 | Export | UTF-8, header row, standard quoting, CRLF. Name and email cells starting with `=`, `+`, `-`, `@`, tab or carriage return get a leading apostrophe. Served with `Cache-Control: no-store`. | Confirmed |
| A-96 | My bookings | Bookings are grouped into upcoming (soonest first), current (staying now), past (most recent first) and cancelled (most recently cancelled first), judged by today's IST date. | Confirmed |
| A-97 | My bookings | Only bookings made by the signed-in account are listed, never bookings matched by email (brief: the email is unverified). | Confirmed |
| A-98 | Checkout | The hold carries a `guest_suggestion` from the account until guest details are saved; saving different details never changes the account. | Confirmed |
| A-99 | My bookings | No pagination; at most the account's 100 most recent bookings. | Confirmed |
| A-100 | Admin | Admin screens (rates, allotment, blackouts, promo codes) are for the reservations team and the GM. | Confirmed |
| A-101 | Admin | Admin changes use inclusive date ranges of up to 366 nights, never in the past (IST); the calendar view shows up to 62 nights and may look back. | Confirmed |
| A-102 | Admin | A new allotment must be at least sold plus active holds and at most the physical units on every night; any violation rejects the whole change, listing each night; missing nights are created. | Confirmed |
| A-103 | Admin | Blacking out nights with an active hold is refused; confirmed bookings on blacked-out nights are honoured; reopening is always allowed. | Confirmed |
| A-104 | Admin | Rate changes affect new quotes only; rates can be set for chosen weekdays; rates are never deleted (allotment 0 or a blackout stops sales). | Confirmed |
| A-105 | Admin | A promo's code and percent are fixed once created; only the on/off switch, end date and cap can change, and the cap cannot go below uses plus reserved uses. | Confirmed |
| A-106 | Admin | Every admin change is written to the audit log: who, when, old values and new values. | Confirmed |
| A-107 | Promo | New codes are 3 to 32 letters and digits (stored uppercase), give 1% to 90% off (a 100% code would make a zero-amount payment, which the payment flow does not accept), and cannot end in the past. A code is "usable today" when it is switched on, today is within its dates, and a use is left. | Confirmed |
| A-108 | Enquiries | Field extraction is our own rule-based code, not `dateparser`: dateparser cannot read ranges such as "14-16 Nov" or "24 se 26 December", so custom code was needed anyway. It covers English, Hinglish, Hindi and Kannada as in the samples. A date without a year is its next occurrence on or after the day received (IST); a range end before its start moves to the next year. | Confirmed |
| A-109 | Enquiries | Owner: room booking to reservations; wedding and corporate offsite to events; complaint to the GM; other to nobody (Unsorted, which the GM sees). | Confirmed |
| A-110 | Enquiries | Complaints are detected by problem words in English, Hinglish, Hindi and Kannada, and by the verb "complain", but not by the noun "complaint" alone. A complaint mixed with a booking request counts as a complaint. The keyword check always runs and sets `complaint_signal`. | Confirmed (verb "complain" added while testing unseen messages) |
| A-111 | Enquiries | Keyword confidence: 0.9 for one clear category (complaints always 0.9), 0.6 when wedding and offsite compete, 0.3 when nothing matches (`other`). | Confirmed |
| A-112 | Enquiries | `budget_inr` is the amount as stated ("8000 per night" stores 8000); per night versus total is not stored. | Confirmed |
| A-113 | Enquiries | Besides the brief's fields, extraction records a room type hint (`room_type`, a code such as PLV for "villa") so step 20 can price the draft's {room_type}. | Confirmed |
| A-114 | Enquiries | Messages are trimmed and capped at 2,000 characters (`ENQUIRY_MAX_LENGTH`). The web form requires a name, the message, consent, and an email or phone (at least one, so staff can reply). | Confirmed |
| A-115 | Enquiries | The confidence threshold for routing is 0.7 (`CLASSIFIER_CONFIDENCE_THRESHOLD`). | Confirmed |
| A-116 | Enquiries | Required fields: a room booking needs a check-in date; a wedding or offsite needs an event month or a date; complaints and other need none. A missing check-out is inferred from check-in plus nights for the draft. | Confirmed |
| A-117 | Enquiries | "Disagree" means both classifiers named a real category and they differ; the keyword classifier's no-match `other` (0.3) is no opinion. | Confirmed |
| A-118 | Enquiries | Draft prices use Room Only, rooms = guests divided by the room's maximum, rounded up (at most 4), and never a promo. They need dates, guests and a room type, otherwise `{price_total}` stays visible; unavailable dates say so instead of a price. Amounts use Indian digit grouping ("Rs 1,50,000"). | Confirmed |
| A-119 | Enquiries | An enquiry owned by the GM is assigned to the GM account; reservations and events enquiries are assigned to the team's lane, not a person. | Confirmed |
| A-120 | Enquiries | New enquiry references continue from ENQ-5001 via a database sequence (migration 0006); `--reset` restarts it. | Confirmed |
| A-121 | Enquiries | The pipeline runs inside the request (no queues, brief). The model is called outside database transactions. A crash after saving leaves the enquiry `failed` with an error code, never the message text in the log. | Confirmed |
| A-122 | Enquiries | The public form returns only the reference and a thank-you message. The category, lane, fields and draft are never shown to the person who wrote in. | Confirmed |
| A-123 | Enquiries | Every staff role (reservations, events, GM) can read every lane of the inbox, filtered by lane or status, newest first; lanes say who owns an enquiry, not who may see it. Guests cannot see the inbox. | Confirmed |
| A-124 | Enquiries | Staff can correct the category and any extracted field; corrected fields get the same range and plausibility checks as extracted ones. A category change sets the lane and owner by A-109 without re-running the classifiers, and the draft is rebuilt from the corrected fields with prices worked out in code. Corrections are refused once the enquiry has been replied to. | Confirmed |
| A-125 | Enquiries | Staff can re-run classification on a pending or failed enquiry at any time, and on a classified one only until a staff member has corrected, re-routed or replied to it; after that a re-run is refused (`already_handled`) so it never overwrites their work. Each re-run is audited with the old and new status, category and lane. | Confirmed |
| A-126 | Enquiries | Staff can re-route an enquiry to any lane (room booking, wedding, offsite, complaint, Unsorted); the owner follows the lane. Moving it to the complaint lane raises a GM alert if it has none. The category stays as classified unless corrected, so the history shows both. | Confirmed |
| A-127 | Enquiries | Replies are simulated (brief: real email and WhatsApp are mocked) and only ever sent by a staff member, never automatically. A reply that still contains an unfilled placeholder such as `{price_total}` is refused. One reply per enquiry, at most 5,000 characters, and the reply text never appears in logs. | Confirmed |
| A-128 | Enquiries | Metrics over a date range (last 30 days by default, at most 366): enquiries per lane, share sent to Unsorted by the pipeline, fallback rate (model down or invalid output), category correction rate, and median time from received to replied. Every number is counted from the database. | Confirmed |
| A-129 | Enquiries | Any staff role can correct, re-route and reply in any lane (as A-123). Every staff role can see the GM alert list; only the GM can acknowledge an alert. | Confirmed |
| A-130 | AI | Provider Google Gemini, model `gemini-3.5-flash-lite` (stable since July 2026), behind one adapter. Chosen with `CLASSIFIER_BACKEND=gemini`, key in `LLM_API_KEY`, model in `LLM_MODEL` (provider-neutral names, as `.env.example` already reserved). The app refuses to start with `gemini` and no key. | Confirmed |
| A-131 | AI | Free API tier for the demo. Google's paid tier is what keeps prompts and responses out of product improvement, so a real resort should use the paid tier; noted in the TDD. | Confirmed |
| A-132 | AI | The client is the Python standard library (`urllib`), not Google's SDK: one HTTPS POST does not justify a dependency with its own dependency tree. | Confirmed |
| A-133 | AI | Only the message text and the received date are sent. No reference, name, email or phone. Temperature 0. | Confirmed |
| A-134 | AI | Timeout 8 seconds (`LLM_TIMEOUT_SECONDS`). Timeouts and HTTP errors are not retried; the keyword result takes over at once, so the guest is not kept waiting on the form. | Confirmed |
| A-135 | AI | Invalid output gets one retry, then `invalid_output` and Unsorted (D-42). Invalid means: not JSON, not the schema, a category outside the list, confidence outside 0 to 1, a block, or a finish reason other than STOP. | Confirmed |
| A-136 | AI | The model returns the same fields as extraction. Each goes through the same checks; a value that fails (wrong type, out of range, implausible date, unknown key) is dropped, not trusted and not fatal. | Confirmed |
| A-137 | AI | An HTTP 429 from Google counts as `provider_error`, so keywords take over. No app-side queue (brief: no queues). | Confirmed |

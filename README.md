# CompanyA: direct booking and AI enquiry inbox

A direct-booking website and an AI enquiry inbox for CompanyA, a coffee-estate resort in
Chikkamagaluru, Karnataka, with 64 rooms and 12 villas. Guests choose dates, see real
prices with GST and book in three steps without the site ever overselling. Every
enquiry, from any channel, is classified, routed to the right team and given a draft
reply, and every complaint alerts the general manager.

![Home page](docs/screenshots/01-home.png)

**Read next:** [Technical design document](docs/TDD.pdf) · [How to run and deploy](deployment.md) · [Assumptions](docs/ASSUMPTIONS.md) · [Decisions](docs/DECISIONS.md)

## Try it in five minutes

Start it locally with [deployment.md](deployment.md) section 1, then:

1. **Book a room as a guest.** Log in as `guest@example.com` / `Guest-Demo-2026`, pick
   dates on the home page, add a room and book. The rooms stay held for 10 minutes while
   you pay; choose "Card is declined" first to see a failed payment, then pay.
2. **See the overbooking guard.** The seed prints a sold-out weekend and a Family Suite
   with one unit left. Search those dates: the site will not sell what it does not have.
3. **Work the inbox as the GM.** Log in as `gm@example.com` / `GM-Demo-2026` and open
   Staff. Enquiries sit in lanes by team; Unsorted holds the ones the AI was unsure of,
   including a prompt-injection attempt. Open a complaint: the GM alert, the extracted
   details beside the message and a ready draft reply are all on one page.
4. **Run the back office.** Log in as `reservations@example.com` /
   `Reservations-Demo-2026` and open Admin: change a price or close a night, and the
   guest site follows at once. Download the day's CSV export for the reservation system.

All four demo accounts are listed in [deployment.md](deployment.md#demo-logins).
Payments, emails and WhatsApp messages are simulated: no money moves and nothing is sent.

## Screens

| | |
|---|---|
| ![Rooms with a live quote](docs/screenshots/02-rooms-quote.png) **Rooms and a live quote.** Prices per night with GST, worked out by the backend. | ![A villa's page](docs/screenshots/03-room-detail.png) **A room's page.** Photos, rate plans and dates in one place. |
| ![Guest details and payment](docs/screenshots/04-booking-pay.png) **Booking, steps 2 and 3.** A visible hold timer, then a test payment. | ![Confirmation](docs/screenshots/05-confirmation.png) **Confirmed.** A reference and a receipt. |
| ![Staff inbox](docs/screenshots/07-staff-inbox.png) **Staff inbox.** One lane per team, with counts. | ![Enquiry detail](docs/screenshots/08-enquiry-detail.png) **An enquiry.** The message beside what was understood, a GM alert, a draft reply and every staff action. |
| ![Enquiry metrics](docs/screenshots/09-metrics.png) **Metrics.** Reply times, fallbacks and AI accuracy against the GM's approvals. | ![Admin inventory](docs/screenshots/10-admin-inventory.png) **Admin inventory.** Rooms left, sold and held per night, with prices and blackouts. |

## What it does

**For guests**
- Search dates and see every room type with its real price per night, GST included.
- Book up to four rooms in three steps: choose rooms, guest details, pay (test mode).
- Promo codes, a booking confirmation and receipt, My bookings, cancellation, and a
  lookup by reference and email.
- An enquiry form for weddings, offsites and questions, with a consent checkbox.

**For staff**
- An inbox with one lane per team (room bookings, weddings, corporate offsites,
  complaints) and an Unsorted lane for anything the AI was not sure of.
- On each enquiry: the extracted details beside the original message, a draft reply
  with prices filled in from the rate table, and actions to correct, re-route, reply
  (recorded, not sent) or run the classification again.
- Admin: prices, web allotment and blackouts per night, promo codes, and a daily CSV
  export for the reservation system, which stays the system of record.

**For the general manager**
- An alert for every complaint, raised by a keyword rule even if the AI misses it.
- Approving a classification records the truth the AI is measured against, so the
  metrics page shows real accuracy over time.

## How it works

![Architecture](docs/diagrams/architecture.png)

- **Two deployables and Postgres.** A Next.js frontend and a FastAPI backend (routes,
  services, database). The browser only talks to the frontend, which forwards `/api/*`,
  so the session cookie stays same-site. No Redis, queues or microservices.
- **No overbooking.** Every change to stock locks the night's allotment rows with
  `SELECT ... FOR UPDATE` in a fixed order. A hold reserves rooms for 10 minutes while
  the guest pays and simply stops counting when it expires. A database `CHECK` keeps
  `sold <= total_for_web` even if a bug slipped past the service. Tested with 10
  parallel guests on real Postgres racing for the last room: exactly one wins.
- **Money in integer paise.** GST is chosen per room per night from configurable
  thresholds, and every price the guest saw is stored per night.
- **Payments.** A mock gateway behind an adapter, an idempotency key on every payment,
  and no gateway call inside a database transaction.

## The AI part

![Enquiry pipeline](docs/diagrams/enquiry.png)

The model proposes; code decides. Each enquiry is saved before any model call, so it is
never lost. Gemini sees only the message text, never names, emails or phones, and must
answer in a fixed JSON schema. If it is slow, down or returns nonsense, the keyword
classifier answers instead and the enquiry is marked. Low confidence, disagreement or
missing details send it to Unsorted for a person. Prices in drafts come from the rate
table, and drafts are never sent automatically.

On the 27 sample enquiries (3 from the brief, 24 invented, including Hindi, Kannada,
Hinglish, hidden complaints and a prompt-injection attempt):

| | Gemini (`gemini-3.5-flash-lite`) | Keyword rules |
|---|---|---|
| Category right | 27/27 | 27/27 |
| Lane right | 27/27 | 27/27 |
| Complaints that alerted the GM | 4/4 | 4/4 |
| Expected details extracted | 52/53 | 53/53 |
| Fell back to keywords | 0 | not applicable |
| Median time per enquiry | 1.27 s | not applicable |

The keyword rules were written from these same messages, so their score is in-sample and
flatters them; the model's score is the fairer test. The Gemini figures are from a run
on 9 November 2026 with `python -m app.eval_enquiries --backend gemini`; its one miss was
the event month in ENQ-4422. Keyword report: [docs/eval/keyword-report.md](docs/eval/keyword-report.md).

## Quality

- **795 backend tests** (pytest, against real PostgreSQL), including the concurrency
  races, every pricing rule, the AI pipeline's failure paths and the migrations.
- **169 end-to-end tests** (Playwright, desktop and phone) driving a real browser
  against the real backend, plus link and image checks on every public page.
- CI runs lint, format, type checks, the backend suite, an OpenAPI drift check and the
  frontend build on every pull request.

## Run it

Full steps, environment variables and the deployment setup are in
[deployment.md](deployment.md). The short version, with Docker, Python 3.12+ and Node 22+:

```bash
cp .env.example .env              # fill in as shown in deployment.md
docker compose up -d
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && alembic upgrade head && python -m app.seed --reset --classify
uvicorn app.main:create_app --factory --reload --timeout-keep-alive 65
# second terminal
cd frontend && npm ci && npm run dev   # http://localhost:3000
```

## Repository layout

```
backend/     FastAPI app, Alembic migrations, tests, sample enquiries
frontend/    Next.js app, Playwright end-to-end tests, sample photos
docs/        TDD, assumptions, decisions, diagrams, screenshots, evaluation reports
deployment.md
docker-compose.yml
.env.example
```

## Known limits

- Rate limits and payment idempotency live in the backend's memory, so it runs as one
  process (the brief rules out Redis).
- Emails, WhatsApp and payments are simulated; guest emails are checked for shape, not
  verified.
- The photos are free-licence samples of other places, not CompanyA
  ([sources](docs/PHOTO_SOURCES.md)).
- Not deployed for this submission; the deployment is prepared and documented.

More in the TDD's "What I cut and what is next".

---

## Developer reference

### API

Interactive API docs are at `http://localhost:8000/docs`. Public routes:
`GET /api/rooms`, `GET /api/rooms/{code}`, `POST /api/quotes`, `POST /api/bookings/lookup`,
`POST /api/enquiries` (the enquiry form; returns only a reference).
All amounts are integer paise. Signed-in guest routes: `POST /api/holds`,
`PUT /api/holds/{id}/guest`, `POST /api/holds/{id}/payment` (needs an `Idempotency-Key`
header), `GET /api/bookings/{reference}`, `POST /api/bookings/{reference}/cancel`, `GET /api/me/bookings` (My bookings). Staff: `GET /api/exports/bookings.csv?date=YYYY-MM-DD`
(reservations team and GM), the day's confirmations and cancellations for the reservation
system, one row per booking line. Admin (reservations team and GM): `GET /api/admin/inventory`,
`PUT /api/admin/rates`, `PUT /api/admin/allotment`, `PUT /api/admin/blackouts`,
`GET` and `POST /api/admin/promos`, `PATCH /api/admin/promos/{code}`. Enquiry inbox (all
staff): `GET /api/enquiries?lane=&status=`, `GET /api/enquiries/{reference}`,
`POST /api/enquiries/{reference}/classify` (re-run), `PATCH /api/enquiries/{reference}`
(correct), `POST /api/enquiries/{reference}/route`, `POST /api/enquiries/{reference}/reply`
(simulated, nothing is sent), `GET /api/enquiries/metrics?from=&to=`, `GET /api/alerts`;
the GM acknowledges alerts with `POST /api/alerts/{id}/ack` and approves a
classification with `POST /api/enquiries/{reference}/verify` (the metrics then compare
what the AI decided with what the GM approved). Logs are JSON lines on
stdout and never contain personal data.

### Run the frontend for production

```bash
API_URL=http://localhost:8000 npm run build
API_URL=http://localhost:8000 npm run start
```

### Enquiry classifier

By default (`CLASSIFIER_BACKEND=keyword`) enquiries are classified by keyword rules and no
model is called. To use Google Gemini, set in `.env`:

```bash
CLASSIFIER_BACKEND=gemini
LLM_API_KEY=your-key-from-google-ai-studio
# LLM_MODEL=gemini-3.5-flash-lite (default)
```

Only the message text and the date it arrived are sent to Google, never names, emails or
phones. If Google is slow, down or rate limited, the keyword result is used and the
enquiry is marked as a fallback. On Google's free tier, message text may be used by
Google to improve its products; a real deployment should use the paid tier.

To check your key works (outside the app):

```bash
curl -s -H "x-goog-api-key: $LLM_API_KEY" -H "Content-Type: application/json" \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent" \
  -d '{"contents":[{"parts":[{"text":"Say OK"}]}]}'
```

### Seed data

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

### Tests

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

### Migrations

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

### Enquiry evaluation

Runs the sample enquiries in `backend/data/sample_enquiries.json` through the same rules
the pipeline uses (keyword classifier, model, lane in code, GM alert rule) and prints a
markdown report. Nothing is written to the database.

```bash
python -m app.eval_enquiries --backend keyword       # no model
python -m app.eval_enquiries --backend both --out ../docs/eval/gemini-report.md
```

`--backend` is `configured` (the default, from `.env`), `keyword`, `gemini` or `both`.
Calls to Gemini are spaced 4.5 seconds apart (`--delay`), so 27 enquiries take about two
minutes. The command exits with an error if any enquiry that must alert the GM does not.
The keyword figures are in-sample (its rules were written from these messages); the
committed report is [docs/eval/keyword-report.md](docs/eval/keyword-report.md).

To fill the demo inbox, seed with `--classify`: the sample enquiries then go through the
pipeline with the configured backend and get lanes, drafts and GM alerts.

```bash
python -m app.seed --reset --classify
```

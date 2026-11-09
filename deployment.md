# Deployment

CompanyA's booking site runs as two services and a database: a Next.js frontend, a
FastAPI backend and PostgreSQL. This file covers running it on your own machine, how
it is set up to be deployed, and the settings each part needs.

- **Repository:** https://github.com/TheRealSoutrikDas/Hill-Resort-Booking-Engine
- **Live app:** not deployed for this submission. Everything runs locally (section 1); the
  deployment below is prepared and ready to use, but has not been run on a host.

## Demo logins

The seed command creates these four accounts. The details are invented, and the
passwords exist only for this demo.

| Account | Email | Password | What to try |
|---|---|---|---|
| Guest | `guest@example.com` | `Guest-Demo-2026` | My bookings (one past, one upcoming, one cancelled); book a room; cancel |
| Reservations team | `reservations@example.com` | `Reservations-Demo-2026` | Staff inbox (room bookings lane), Admin: inventory, promo codes, daily export |
| Events team | `events@example.com` | `Events-Demo-2026` | Staff inbox (weddings and corporate offsites lanes) |
| General manager | `gm@example.com` | `GM-Demo-2026` | Everything staff can do, plus GM alerts and approving classifications |

You can also book without these accounts: sign up with any email (it is not
verified, A-49). Payments are simulated; no card details are asked for and no money
moves.

---

## 1. Run it locally

You need Git, Docker (for Postgres), Python 3.12 or newer and Node 22 or newer.

### 1.1 Get the code and settings

```bash
git clone https://github.com/TheRealSoutrikDas/Hill-Resort-Booking-Engine.git
cd Hill-Resort-Booking-Engine
cp .env.example .env
```

Fill in `.env`. These values are for your own machine only:

```
POSTGRES_USER=resort
POSTGRES_PASSWORD=resort_dev
POSTGRES_DB=resort
DATABASE_URL=postgresql+psycopg://resort:resort_dev@localhost:5432/resort
TEST_DATABASE_URL=postgresql+psycopg://resort:resort_dev@localhost:5432/resort_test
CORS_ORIGINS=http://localhost:3000
SESSION_COOKIE_SECURE=false
```

`CORS_ORIGINS` must include the frontend's address, or every log in, booking and
enquiry is refused with "Request from an unexpected origin." `SESSION_COOKIE_SECURE=false`
lets the browser keep the session cookie over plain `http://localhost`.

To use Gemini for enquiries, also set `CLASSIFIER_BACKEND=gemini` and `LLM_API_KEY`
(a Google AI Studio key). Without them the keyword classifier is used and no model is
called.

### 1.2 Start the database

```bash
docker compose up -d        # Postgres 16 on 127.0.0.1:5432, plus resort_test for the tests
```

### 1.3 Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed --reset --classify
uvicorn app.main:create_app --factory --reload --timeout-keep-alive 65
```

Check it: `curl localhost:8000/health` returns `{"status":"ok","database":"ok"}`. The
API's interactive docs are at http://localhost:8000/docs.

`--classify` runs the 27 sample enquiries through the classifier, so the staff inbox is
not empty. Run the seed again whenever you want fresh demo data; `--reset` empties
every table first.

### 1.4 Start the frontend

In a second terminal:

```bash
cd frontend
npm ci
npm run dev                 # http://localhost:3000
```

Open http://localhost:3000 and log in with one of the demo accounts. The browser only
talks to the frontend; Next.js forwards `/api/*` to the backend, so the session cookie
stays on one site.

The sample photos are committed in `frontend/public/images/`. If any are missing, the
build stops with "Module not found" naming the file; `bash scripts/fetch-photos.sh`
downloads them again.

### 1.5 Run the tests

Backend (from `backend/`, with Postgres running):

```bash
pytest
ruff check . && ruff format --check .
```

Frontend checks (from `frontend/`):

```bash
npm run typecheck && npm run lint
```

End-to-end tests drive a real browser against the real backend. They need a fresh seed,
a production build, and a backend started with the keyword classifier and relaxed rate
limits (every test request comes from the same address):

```bash
# terminal 1, in backend/
CLASSIFIER_BACKEND=keyword python -m app.seed --reset --classify
CLASSIFIER_BACKEND=keyword CORS_ORIGINS=http://localhost:3000 \
RATE_LOGIN_PER_IP=10000 RATE_LOGIN_FAILURES_PER_EMAIL=10000 RATE_SIGNUP_PER_IP=10000 \
RATE_LOOKUP_PER_IP=10000 RATE_ENQUIRY_PER_IP=10000 \
SESSION_COOKIE_SECURE=false uvicorn app.main:create_app --factory --timeout-keep-alive 65

# terminal 2, in frontend/
API_URL=http://localhost:8000 npm run build
API_URL=http://localhost:8000 npm run start

# terminal 3, in frontend/
npx playwright install chromium   # once
npm run test:e2e
```

Reseed before running the suite again, because the booking tests take rooms.

---

## 2. How it is deployed

The repository is ready to deploy to [Railway](https://railway.com) as one project with
three services (D-58). It has not been deployed for this submission: the Dockerfiles and
`railway.json` files are in the repository, and their steps were checked by hand
(section 2.1), but no live copy exists.

```mermaid
flowchart LR
  browser([Guest or staff browser]) -- HTTPS --> edge[Railway edge]
  edge --> frontend["frontend<br/>Next.js, public domain"]
  frontend -- "/api/* over the private network" --> backend["backend<br/>FastAPI, no public domain"]
  backend --> db[(Postgres)]
  backend -. "enquiry text only" .-> gemini[Google Gemini]
```

| Service | Built from | Reachable from | Notes |
|---|---|---|---|
| `frontend` | `frontend/Dockerfile` | The internet (Railway public domain) | Serves pages and forwards `/api/*` to the backend |
| `backend` | `backend/Dockerfile` | Only the frontend, over Railway's private network | One instance, one worker (section 7). Migrations run before each deploy |
| `Postgres` | Railway's PostgreSQL template | Only the backend | Data on a persistent volume |

Why this shape:

- **The backend has no public address.** Nothing on the internet can call it except
  through the frontend. That keeps the session cookie same-site and makes it safe to
  believe the client IP the proxies pass on (section 8).
- **Docker images**, so the build is the same on any host and does not depend on
  Railway's own build detection. Each service's `railway.json` holds its build and
  deploy settings in the repository instead of in the dashboard.
- **No sleeping.** Railway keeps both services running, so the first visitor after a
  quiet spell does not wait for a cold start, as on free hosts that sleep.

Pushing to `main` redeploys only the service whose folder changed (`watchPatterns` in
each `railway.json`).

### 2.1 What was checked without deploying

Docker Hub could not be reached from the machine this was built on, so the images were
not built. Each image's steps were run by hand instead:

- **Backend:** a clean Python 3.12 environment with only the image's files: install,
  `alembic upgrade head`, seed, start with the image's command, `/health` returns ok.
- **Frontend:** a clean copy of the build context: `npm ci`, build with the backend
  switched off (the build does not need it), start, then pages, the room list and
  resized photos are served once the backend is up.

Not checked: the images themselves, and listening on IPv6 (`HOST=::`). If the backend
fails to start with "could not bind", set `HOST=0.0.0.0`.

---

## 3. Environment variables

Names only. Values go in Railway's variables for each service, or in your local
`.env`. `.env.example` lists the same names.

### Backend

| Name | Required | What it does |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection URL. `postgresql://` and `postgresql+psycopg://` both work |
| `CORS_ORIGINS` | Yes | Comma-separated origins allowed to send writes. Must be the frontend's public address |
| `FORWARDED_ALLOW_IPS` | Yes, when deployed | Which proxies' `X-Forwarded-For` uvicorn believes (section 8) |
| `PORT` | Yes, when deployed | Port the backend listens on. The frontend's `API_URL` uses the same port |
| `CLASSIFIER_BACKEND` | No | `keyword` (default) or `gemini` |
| `LLM_API_KEY` | When `CLASSIFIER_BACKEND=gemini` | Google AI Studio key. Secret |
| `LLM_MODEL` | No | Gemini model name |
| `LLM_TIMEOUT_SECONDS` | No | How long to wait for Gemini before using the keyword result |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | No | Below this confidence an enquiry goes to Unsorted |
| `ENQUIRY_MAX_LENGTH` | No | Longest enquiry message accepted |
| `SESSION_TTL_HOURS` | No | How long a login lasts |
| `SESSION_COOKIE_SECURE` | No | Send the session cookie over HTTPS only. Leave on when deployed |
| `BUSINESS_TIMEZONE` | No | The resort's time zone, for business dates |
| `HOLD_TTL_MINUTES` | No | How long a hold keeps rooms while the guest pays |
| `BOOKING_HORIZON_DAYS` | No | How far ahead guests can book |
| `MAX_STAY_NIGHTS` | No | Longest stay in one booking |
| `MAX_UNITS_PER_BOOKING` | No | Most rooms in one booking |
| `LOCK_TIMEOUT_MS` | No | How long a booking waits for a row lock before giving up |
| `PAYMENT_PROVIDER` | No | `mock`, the only provider |
| `GST_SLAB_THRESHOLD_PAISE` | No | Nightly price at which the higher GST rate starts |
| `GST_RATE_LOW_BP`, `GST_RATE_HIGH_BP` | No | GST rates in basis points |
| `RATE_LOGIN_PER_IP`, `RATE_LOGIN_FAILURES_PER_EMAIL`, `RATE_SIGNUP_PER_IP`, `RATE_LOOKUP_PER_IP`, `RATE_ENQUIRY_PER_IP` | No | Rate limits; each has a matching `..._WINDOW_S` |
| `LOG_LEVEL` | No | Log level for the JSON logs |
| `HOST` | No | Address uvicorn listens on in the Docker image (default `::`, IPv6 and IPv4) |

Defaults for the optional ones are in `backend/app/core/config.py`.

### Frontend

| Name | Required | What it does |
|---|---|---|
| `API_URL` | Yes, at build and at runtime | The backend's base URL. `/api/*` is forwarded there. The build fails without it |
| `PORT` | Set by Railway | Port `next start` listens on |

### Local only

| Name | What it does |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | The Docker Compose database |
| `TEST_DATABASE_URL` | The test database. Its name must end in `_test` |

---

## 4. Setting it up on Railway, step by step

These steps deploy it from nothing. The service names matter: the
variables below refer to `backend`, `frontend` and `Postgres` by name.

1. **Create the project.** In Railway, create a new project and add a PostgreSQL
   database to it. Keep its name `Postgres`.
2. **Add the backend.** Add a service from this GitHub repository and name it
   `backend`. In its settings:
   - Root directory: `/backend`
   - Railway config file: `/backend/railway.json` (the config path does not follow the
     root directory, so it is written from the repository's root)
   - Do not generate a public domain.
3. **Backend variables:**
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   PORT=8000
   CORS_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
   FORWARDED_ALLOW_IPS=*
   CLASSIFIER_BACKEND=gemini
   LLM_API_KEY=<your Google AI Studio key>
   ```
   `${{...}}` are Railway references, filled in by Railway; only `LLM_API_KEY` is a
   secret you type in.
4. **Add the frontend.** Add a second service from the same repository and name it
   `frontend`. In its settings:
   - Root directory: `/frontend`
   - Railway config file: `/frontend/railway.json`
   - Generate a public domain. This is the address reviewers open.
5. **Frontend variables:**
   ```
   API_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000
   ```
   Plain `http` is right here: the private network is already encrypted.
6. **Deploy both.** The backend's pre-deploy step runs `alembic upgrade head`, then
   Railway waits for `GET /health` to pass before sending traffic to it. The frontend
   waits for `/privacy`.
7. **Load the demo data, once.** See section 5.
8. **Check it.** Open the frontend's public address, log in as the guest, and book a
   room. Then log in as the GM and open the staff inbox.

---

## 5. Migrations and demo data

**Migrations** run automatically: `preDeployCommand` in `backend/railway.json` runs
`alembic upgrade head` before each new backend version starts. If a migration fails,
the deploy stops and the previous version keeps running.

**Demo data** is loaded by hand, because `--reset` empties every table and must never
run on its own. With the [Railway CLI](https://docs.railway.com/guides/cli):

```bash
railway login
railway link                      # choose this project
railway ssh --service backend     # a shell inside the running backend
python -m app.seed --reset --classify
exit
```

Inside the backend, the seed uses the deployed settings, so `--classify` runs the
sample enquiries through Gemini.

If `railway ssh` is not available, run the seed from your own machine against the
database's public URL (shown on the Postgres service in Railway):

```bash
cd backend
DATABASE_URL='<Postgres public URL>' python -m app.seed --reset --classify
```

Run the same command any time to reset the demo, for example after testing. Seeded
dates are relative to the day the seed runs, so a reseed also brings the demo bookings
up to date.

---

## 6. Health checks

- **Backend:** `GET /health` returns 200 with `{"status":"ok","database":"ok"}`, or 503
  when the database cannot be reached. Railway uses it to decide when a new version can
  take traffic.
- **Frontend:** `GET /privacy`, a page that does not need the backend, so a backend
  problem does not stop the frontend from deploying.

---

## 7. Run exactly one backend instance with one worker

Two things keep state in the backend process's memory:

- the rate limiter (A-82, D-34): several workers or instances would each count
  separately, multiplying the limits, and a restart resets the counts;
- the mock payment gateway's idempotency memory (D-31).

So the backend runs one instance with one worker. The Docker image starts it with
`--workers 1`, and Railway's default is one replica; do not add replicas.

A shared store (Redis) is the usual fix and is out of scope (brief). Storing the counts
in Postgres would also work, at the cost of a database write per attempt.

`--timeout-keep-alive 65` matters whenever a proxy sits in front of uvicorn (the
Next.js proxy here). uvicorn closes an idle connection after 5 seconds by default; a
proxy that reuses that connection at the same moment gets `ECONNRESET` and the request
fails (D-56). The backend's idle timeout must be longer than the proxy's.

---

## 8. Client IPs behind the proxies (A-81, A-199)

The rate limits count requests per client IP, so the backend has to know the real one.
A request passes through two proxies before it reaches the backend:

1. **Railway's edge** sets `X-Forwarded-For` to the client's address, replacing
   any value the client sent.
2. **The Next.js proxy** passes `X-Forwarded-For` on unchanged (checked locally).

uvicorn uses `X-Forwarded-For` only for requests from a proxy listed in
`FORWARDED_ALLOW_IPS`. The frontend's address on the private network changes with
each deploy, so the deployed backend sets `FORWARDED_ALLOW_IPS=*`. With `*`, uvicorn takes
the first address in the header, which the edge wrote. This is safe only because the
backend has no public domain: nobody can reach it except through the frontend.

**The limit:** Railway's staff describe the edge's replacing behaviour on its forum,
but its documentation does not promise it. If the edge ever kept a client's own
`X-Forwarded-For`, a client could pick the IP its rate limit counts against. Nothing
else depends on the client IP.

Locally, uvicorn's default (`127.0.0.1,::1`) already trusts the Next.js proxy on the
same machine.

---

## 9. Rollback

- **Code:** in Railway, open the service's deployments and redeploy the previous one.
  Or revert the commit on `main`; the push redeploys.
- **Database:** every migration has a downgrade. To undo the latest one, run
  `alembic downgrade -1` from a backend shell (`railway ssh --service backend`)
  **before** rolling back the code, since older code expects the older schema. Back up
  the database first (Railway's Postgres service has a Backups tab).
- **Demo data:** reseed (section 5).

---

## 10. Known limits

- Rate limits and the mock gateway's idempotency memory live in one process, so the
  backend cannot scale out (section 7). A restart resets the rate-limit counts.
- The client-IP chain relies on Railway's edge replacing `X-Forwarded-For` (section 8).
- Emails, WhatsApp messages and payments are simulated (brief). Replies and
  confirmations are recorded, not sent.
- With `CLASSIFIER_BACKEND=gemini` on Google's free tier, Google may use the message
  text to improve its products. Only the text is sent, never names, emails or phones.
  A real deployment should use the paid tier. If Gemini is slow or rate limited, the
  keyword classifier answers and the enquiry is marked as a fallback.
- Once deployed as a demo, anyone can sign up, and all accounts share one demo database.
  Reseed to reset it.
- Not deployed for this submission (section 2).

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Request from an unexpected origin." on log in, booking or enquiry | The frontend's address is not in `CORS_ORIGINS` | Add the exact origin (scheme, host, port), then restart the backend |
| Build fails with "Set API_URL" | `API_URL` missing at build time | Set it on the frontend service (or in your shell locally) |
| Build fails with "Module not found ... public/images/..." | A photo is missing | `bash scripts/fetch-photos.sh` in `frontend/`, then commit the photos |
| Logged in, but every action logs you out locally | Secure cookie over plain `http://` | Set `SESSION_COOKIE_SECURE=false` locally only |
| `read ECONNRESET` in the frontend logs | The backend's keep-alive is shorter than the proxy's | Start uvicorn with `--timeout-keep-alive 65` |
| The staff inbox is empty | Seeded without `--classify`, or not seeded | `python -m app.seed --reset --classify` |
| Every guest hits the same rate limit when deployed | `FORWARDED_ALLOW_IPS` not set | Set it as in section 4 |

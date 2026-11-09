# Deployment

Status: skeleton. Filled in during stage 7.

## Overview

Two deployables (Next.js frontend, FastAPI backend) plus managed PostgreSQL.

## Environment variables

See `.env.example` for names. Values live only in the hosting provider's secret settings.

## Database and migrations

To be written.

## Backend

To be written.

## Frontend

To be written.

## Seeding a demo environment

To be written.

## Health checks

`GET /health` on the backend.

## Run exactly one backend instance with one worker

Two things keep state in the backend process's memory:

- the rate limiter (A-82, D-34): several workers or instances would each count
  separately, multiplying the limits, and a restart resets the counts;
- the mock payment gateway's idempotency memory (D-31).

So run one instance with one worker, and turn off autoscaling:

```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" --workers 1 --timeout-keep-alive 65
```

A shared store (Redis) is the usual fix and is out of scope (brief). Storing the counts
in Postgres would also work, at the cost of a database write per attempt.

`--timeout-keep-alive 65` matters whenever a proxy sits in front of uvicorn (the Next.js
proxy here, and usually the host's load balancer). uvicorn closes an idle connection
after 5 seconds by default; a proxy that reuses that connection at the same moment gets
`ECONNRESET` and the request fails (D-56). The backend's idle timeout must be longer
than the proxy's.

## Client IPs behind the proxy (A-81)

Browser traffic reaches the backend through the Next.js proxy, so the backend must take
the client's IP from `X-Forwarded-For`, but only when the request comes from the proxy.
Uvicorn does this when `FORWARDED_ALLOW_IPS` lists the proxy's address. Its default is
this machine only (`127.0.0.1,::1`), which suits local development. In production set
it to the proxy's address; never to `*` unless the backend is unreachable except
through the proxy. Without it, every guest shares the proxy's IP and one rate limit.

## Known limits

- Rate limits and the mock gateway's idempotency memory are per process (above).

## Rollback

To be written.

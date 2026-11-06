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

## Known limits

- Rate limiting is in-memory, so limits apply per instance when more than one backend instance runs.

## Rollback

To be written.

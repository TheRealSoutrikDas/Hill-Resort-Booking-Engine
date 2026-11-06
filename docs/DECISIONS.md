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

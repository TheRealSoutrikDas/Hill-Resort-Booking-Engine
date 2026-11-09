# FastAPI backend (D-58). Build context: backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# A non-root user owns nothing but its home; the code is read-only to it.
RUN useradd --create-home --uid 10001 app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
# Editable install: the dependencies come from pyproject.toml, and the code runs from
# /app, so `alembic` and `python -m app.seed` work from this directory.
RUN pip install -e .

USER app

# The frontend reaches the backend on this port over the private network.
ENV PORT=8000
EXPOSE 8000

# One process with one worker: rate limits and the mock gateway's idempotency memory
# live in this process (deployment.md). `::` listens on IPv6 and IPv4, which Railway's
# private network needs; set HOST=0.0.0.0 on a host without IPv6.
ENV HOST=::
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host \"$HOST\" --port \"$PORT\" --workers 1 --timeout-keep-alive 65"]

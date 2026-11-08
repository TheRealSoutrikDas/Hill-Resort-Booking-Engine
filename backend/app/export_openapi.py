"""Write the API's OpenAPI schema, the source of the frontend's TypeScript types (A-153).

    python -m app.export_openapi > ../frontend/lib/openapi.json

Builds the app without touching the database. A test fails if the committed file is out
of date, so a backend change cannot silently break the frontend's types (D-48).
"""

import json
import sys

from app.core.config import Settings
from app.main import create_app

# FastAPI labels responses with Python's HTTP status phrases, and Python 3.13 renamed
# 422 from "Unprocessable Entity" to "Unprocessable Content" (RFC 9110). The schema uses
# the current name on every Python version, so CI and laptops produce the same file.
STATUS_PHRASES = {"422": "Unprocessable Content"}


def _same_on_every_python(spec: dict) -> dict:
    for operations in spec.get("paths", {}).values():
        for operation in operations.values():
            for status, response in operation.get("responses", {}).items():
                if status in STATUS_PHRASES and response.get("description") in (
                    "Unprocessable Entity",
                    "Unprocessable Content",
                ):
                    response["description"] = STATUS_PHRASES[status]
    return spec


def schema() -> dict:
    # Placeholder settings: building the schema opens no connection.
    settings = Settings(database_url="postgresql://schema:schema@localhost/schema", _env_file=None)
    return _same_on_every_python(create_app(settings).openapi())


def render() -> str:
    return json.dumps(schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())

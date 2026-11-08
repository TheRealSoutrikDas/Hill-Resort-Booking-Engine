"""Write the API's OpenAPI schema, the source of the frontend's TypeScript types (A-153).

    python -m app.export_openapi > ../frontend/lib/openapi.json

Builds the app without touching the database. A test fails if the committed file is out
of date, so a backend change cannot silently break the frontend's types (D-48).
"""

import json
import sys

from app.core.config import Settings
from app.main import create_app


def schema() -> dict:
    # Placeholder settings: building the schema opens no connection.
    settings = Settings(database_url="postgresql://schema:schema@localhost/schema", _env_file=None)
    return create_app(settings).openapi()


def render() -> str:
    return json.dumps(schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())

"""The committed OpenAPI schema must match the API (D-48).

The frontend's TypeScript types are generated from `frontend/lib/openapi.json`. If this
test fails, regenerate both:

    python -m app.export_openapi > ../frontend/lib/openapi.json
    cd ../frontend && npm run api:types
"""

import json
from pathlib import Path

from app.export_openapi import render

COMMITTED = Path(__file__).resolve().parents[3] / "frontend" / "lib" / "openapi.json"


def test_committed_schema_is_current() -> None:
    assert COMMITTED.exists(), "frontend/lib/openapi.json is missing"
    assert json.loads(COMMITTED.read_text(encoding="utf-8")) == json.loads(render()), (
        "The API changed; regenerate frontend/lib/openapi.json and the TypeScript types."
    )

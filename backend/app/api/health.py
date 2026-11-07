"""Health check for the hosting platform (A-65)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import ErrorResponse, error_response

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=Health, responses={503: {"model": ErrorResponse}})
def health(request: Request) -> Health | JSONResponse:
    """200 when the API and its database answer, 503 when the database does not."""
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return error_response(503, "database_unavailable", "The database is not reachable.")
    return Health(status="ok", database="ok")

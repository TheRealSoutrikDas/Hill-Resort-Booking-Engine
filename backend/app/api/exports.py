"""Daily booking export download (brief screen 9, A-90)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DbSession, Rules
from app.api.errors import ErrorResponse
from app.api.security import require_user
from app.db.models import User
from app.services.exports import export_rows, to_csv

router = APIRouter(prefix="/api/exports", tags=["exports"])

# The file holds every guest's contact details: reservations team and the GM only.
ExportUser = Annotated[User, Depends(require_user(role="staff", team="reservations"))]


@router.get(
    "/bookings.csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "One row per booking line per event that day",
        },
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def export_bookings(
    user: ExportUser, db: DbSession, rules: Rules, day: Annotated[date, Query(alias="date")]
) -> Response:
    """Bookings confirmed or cancelled on this IST date. The same file on every download."""
    return Response(
        content=to_csv(export_rows(db, day, rules.tz)),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="bookings-{day.isoformat()}.csv"',
            "Cache-Control": "no-store",  # personal data: never kept by browsers or proxies
        },
    )

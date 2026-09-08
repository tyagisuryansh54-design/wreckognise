"""Live ledger of catalogued ocean findings, and the reference catalogue itself."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models.schemas import FindingsResponse
from ..services import catalogue
from ..services.findings import ledger

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("", response_model=FindingsResponse)
async def list_findings(
    limit: int = Query(default=100, ge=1, le=500),
    category: str | None = Query(default=None, description="Filter by catalogue category"),
) -> FindingsResponse:
    """Every anomaly catalogued so far, newest first.

    Appended to automatically as surveys are analysed. Re-running a survey
    replaces its own entries rather than duplicating them.
    """
    by_category, by_class = ledger.summary()
    return FindingsResponse(
        total=len(ledger),
        by_category=by_category,
        by_class=by_class,
        findings=ledger.all(limit=limit, category=category),
    )


@router.get("/catalogue")
async def get_catalogue() -> dict:
    """Reference data for every object class the system can report."""
    entries = catalogue.catalogue_listing()
    return {"count": len(entries), "catalogue": entries}


@router.delete("")
async def clear_findings() -> dict:
    return {"cleared": ledger.clear()}

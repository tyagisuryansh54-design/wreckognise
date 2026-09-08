"""Reference data for the seabed object classes the system can report."""

from __future__ import annotations

from fastapi import APIRouter

from ..services import catalogue

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])


@router.get("")
async def get_catalogue() -> dict:
    """Every object class, with its acoustic signature and operational note."""
    entries = catalogue.catalogue_listing()
    return {"count": len(entries), "catalogue": entries}

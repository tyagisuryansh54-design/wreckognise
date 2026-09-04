"""Report generation, GeoJSON export and download endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..config import settings
from ..models.schemas import ReportRequest, ReportResponse, ReviewStatus
from ..services.reporting import generate_report, to_geojson
from ..services.store import store

router = APIRouter(prefix="/api/reports", tags=["reporting"])


@router.post("/generate", response_model=ReportResponse)
async def generate(request: ReportRequest) -> ReportResponse:
    """Produce an executive summary in Markdown, JSON or GeoJSON."""
    survey = store.get(request.survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{request.survey_id}'")
    if not survey.detections and survey.inference_metrics is None:
        raise HTTPException(
            status_code=409,
            detail="Run detection before generating a report.",
        )
    return generate_report(survey, request)


@router.get("/{survey_id}/geojson")
async def export_geojson(survey_id: str, include_dismissed: bool = False) -> JSONResponse:
    """GeoJSON feature collection ready for QGIS / ArcGIS / ENC plotters."""
    survey = store.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")

    detections = survey.detections
    if not include_dismissed:
        detections = [d for d in detections if d.review_status != ReviewStatus.DISMISSED]

    return JSONResponse(
        content=to_geojson(survey, detections),
        headers={
            "Content-Disposition": f'attachment; filename="{survey_id}_contacts.geojson"'
        },
    )


@router.get("/download/{filename}")
async def download(filename: str) -> FileResponse:
    """Serve a previously generated report file."""
    # Reject any path traversal before touching the filesystem.
    safe_name = filename.replace("\\", "/").split("/")[-1]
    path = (settings.report_dir / safe_name).resolve()
    if not path.is_file() or settings.report_dir.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail=f"No report named '{filename}'")

    media_types = {
        ".md": "text/markdown",
        ".json": "application/json",
        ".geojson": "application/geo+json",
    }
    return FileResponse(
        path,
        media_type=media_types.get(path.suffix, "application/octet-stream"),
        filename=safe_name,
    )


@router.get("/list")
async def list_reports() -> dict:
    reports = sorted(
        settings.report_dir.glob("RPT-*"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return {
        "count": len(reports),
        "reports": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "format": p.suffix.lstrip("."),
                "download_url": f"/api/reports/download/{p.name}",
            }
            for p in reports[:50]
        ],
    }

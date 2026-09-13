"""YOLOv8 inference, georeferencing and contact review endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import cv2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..models.schemas import (
    BoundingBox,
    Detection,
    GeoSolution,
    InferenceResponse,
    ReviewRequest,
    SurveyStatus,
)
from ..services import attention
from ..services.detector import run_inference, summarise
from ..services.georeference import solve_pixel
from ..services.preprocessing import render_annotated
from ..services.store import store

logger = logging.getLogger("wreckognise")

router = APIRouter(prefix="/api/inference", tags=["inference"])


@router.post("/{survey_id}/detect", response_model=InferenceResponse)
async def detect(
    survey_id: str,
    confidence: float = Query(default=None, ge=0.0, le=1.0),
    iou: float = Query(default=None, ge=0.0, le=1.0),
) -> InferenceResponse:
    """Run the detection engine over a preprocessed survey and georeference hits."""
    survey = store.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")
    if survey.filtered is None:
        raise HTTPException(
            status_code=409,
            detail="Survey has not been preprocessed; POST /api/ingest/upload first.",
        )

    detections, metrics = run_inference(survey, confidence, iou)
    survey.detections = detections
    survey.inference_metrics = metrics

    annotated = settings.processed_dir / f"{survey_id}_annotated.png"
    render_annotated(survey.filtered, detections, annotated)

    return InferenceResponse(
        survey_id=survey_id,
        status=SurveyStatus.COMPLETE,
        metrics=metrics,
        detections=detections,
        annotated_png=f"/static/processed/{annotated.name}",
        summary=summarise(survey, detections),
    )


@router.get("/{survey_id}/detections", response_model=list[Detection])
async def list_detections(
    survey_id: str,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    severity: str | None = None,
    review_status: str | None = None,
) -> list[Detection]:
    """Filtered contact list backing the dashboard's anomaly register."""
    survey = _require(survey_id)
    results = [d for d in survey.detections if d.confidence >= min_confidence]
    if severity:
        results = [d for d in results if d.severity.value == severity]
    if review_status:
        results = [d for d in results if d.review_status.value == review_status]
    return results


@router.get("/{survey_id}/detections/{detection_id}", response_model=Detection)
async def get_detection(survey_id: str, detection_id: str) -> Detection:
    survey = _require(survey_id)
    for detection in survey.detections:
        if detection.detection_id == detection_id:
            return detection
    raise HTTPException(status_code=404, detail=f"Unknown detection '{detection_id}'")


@router.patch("/{survey_id}/detections/{detection_id}/review", response_model=Detection)
async def review_detection(
    survey_id: str, detection_id: str, request: ReviewRequest
) -> Detection:
    """Flag a contact, hand it to a human operator, confirm it, or dismiss it."""
    survey = _require(survey_id)
    for detection in survey.detections:
        if detection.detection_id == detection_id:
            detection.review_status = request.review_status
            if request.notes:
                stamp = f"[{request.operator}] {request.notes}"
                detection.notes = f"{detection.notes}\n{stamp}" if detection.notes else stamp
            return detection
    raise HTTPException(status_code=404, detail=f"Unknown detection '{detection_id}'")


@router.post("/{survey_id}/detections/{detection_id}/acknowledge", response_model=Detection)
async def acknowledge_hazard(
    survey_id: str, detection_id: str, operator: str = Query(default="operator")
) -> Detection:
    """Record that a human has seen a hazard contact.

    Separate from /review on purpose. Review is a judgement -- flag, confirm,
    dismiss. This is only an assertion that a person looked, and it is what the
    alert requires before it will clear. Conflating the two would let a hazard
    leave the queue as a side effect of routine triage.
    """
    survey = _require(survey_id)
    for detection in survey.detections:
        if detection.detection_id == detection_id:
            if detection.priority != "hazard":
                raise HTTPException(
                    status_code=409,
                    detail="Only hazard contacts require acknowledgement.",
                )
            detection.acknowledged_by = operator
            detection.acknowledged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            logger.warning(
                "hazard acknowledged | %s %s by %s", survey_id, detection_id, operator
            )
            return detection
    raise HTTPException(status_code=404, detail=f"Unknown detection '{detection_id}'")


@router.get("/{survey_id}/detections/{detection_id}/attention")
async def detection_attention(survey_id: str, detection_id: str) -> FileResponse:
    """Eigen-CAM heat map for one contact, computed on demand and cached.

    Not generated during detection: it is a second forward pass plus an SVD per
    contact, and most contacts are never asked about. Cached by detection id so
    toggling the overlay twice costs one computation.
    """
    survey = _require(survey_id)
    target = next((d for d in survey.detections if d.detection_id == detection_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown detection '{detection_id}'")
    if not attention.is_available():
        raise HTTPException(status_code=503, detail="Attention maps unavailable for this engine.")

    path = settings.processed_dir / f"{survey_id}_{detection_id}_cam.png"
    if not path.exists():
        image = survey.detect_input if survey.detect_input is not None else survey.waterfall
        heat = attention.heatmap(
            image, bbox=(target.bbox.x, target.bbox.y, target.bbox.width, target.bbox.height)
        )
        if heat is None:
            raise HTTPException(status_code=503, detail="Could not compute an attention map.")
        cv2.imwrite(str(path), heat)
    return FileResponse(path, media_type="image/png")


@router.get("/{survey_id}/georeference", response_model=GeoSolution)
async def georeference_pixel(
    survey_id: str,
    x: float = Query(..., description="Waterfall column, 0 = port edge"),
    y: float = Query(..., description="Waterfall row, 0 = first ping"),
) -> GeoSolution:
    """Solve an arbitrary waterfall pixel to WGS-84, with the full audit trail.

    Backs the dashboard's live pixel → Lat/Long readout as the operator moves
    the cursor over the swath.
    """
    survey = _require(survey_id)
    height, width = survey.waterfall.shape[:2]
    if not (0 <= x < width and 0 <= y < height):
        raise HTTPException(
            status_code=400,
            detail=f"Pixel ({x}, {y}) is outside the {width}x{height} swath.",
        )
    return solve_pixel(survey, x, y)


@router.post("/{survey_id}/georeference/bbox", response_model=GeoSolution)
async def georeference_bbox(survey_id: str, bbox: BoundingBox) -> GeoSolution:
    """Solve a manually drawn box -- used when an operator marks a missed contact."""
    survey = _require(survey_id)
    return solve_pixel(survey, bbox.cx, bbox.cy)


def _require(survey_id: str):
    survey = store.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")
    return survey

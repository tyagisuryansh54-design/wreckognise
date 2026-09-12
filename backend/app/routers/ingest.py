"""Ingestion + preprocessing endpoints."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import settings
from ..models.schemas import (
    IngestResponse,
    PingTelemetry,
    SonarMetadata,
    SurveyStatus,
)
from ..services.preprocessing import preprocess, render_waterfall
from ..services.sonar_reader import (
    list_samples,
    read_image_file,
    read_image_sample,
    read_sonar_file,
)
from ..services.store import store

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.post("/upload", response_model=IngestResponse)
async def upload_sonar(
    file: UploadFile = File(..., description="Raw .xtf / .jsf sonar file, or an exported .jpg / .png waterfall"),
    denoise_method: str = Form(default="nlm"),
    apply_tvg: bool = Form(default=True),
    apply_clahe: bool = Form(default=True),
) -> IngestResponse:
    """Ingest a raw sonar file, decode it, and run the OpenCV preprocessing chain."""
    filename = Path(file.filename or "unnamed.xtf").name
    suffix = Path(filename).suffix.lower()

    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported sonar format '{suffix}'. "
                f"Accepted: {', '.join(settings.allowed_extensions)}"
            ),
        )

    survey_id = f"SVY-{uuid.uuid4().hex[:10].upper()}"
    stored_path = settings.upload_dir / f"{survey_id}{suffix}"

    try:
        with stored_path.open("wb") as target:
            shutil.copyfileobj(file.file, target, length=1024 * 1024)
    finally:
        await file.close()

    size_mb = stored_path.stat().st_size / 1_048_576
    if size_mb > settings.max_upload_mb:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"File is {size_mb:.1f} MB; the limit is {settings.max_upload_mb} MB.",
        )

    return _process(survey_id, stored_path, filename, denoise_method, apply_tvg, apply_clahe)


@router.post("/demo", response_model=IngestResponse)
async def load_demo(
    denoise_method: str = Form(default="nlm"),
    line_name: str = Form(default="GoM-Line-07.xtf"),
) -> IngestResponse:
    """Load a modelled demo survey line without needing a file on disk.

    Backs the dashboard's "Explore Live Scan" call to action.
    """
    survey_id = f"SVY-{uuid.uuid4().hex[:10].upper()}"
    virtual_path = settings.upload_dir / Path(line_name).name
    return _process(survey_id, virtual_path, Path(line_name).name, denoise_method, True, True)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _process(
    survey_id: str,
    path: Path,
    display_name: str,
    denoise_method: str,
    apply_tvg: bool,
    apply_clahe: bool,
) -> IngestResponse:
    """Decode, denoise and render one survey line."""
    # Route by kind, not by hope. An image handed to read_sonar_file would fail
    # to decode and fall back to a SYNTHESISED swath -- the user would get a
    # plausible-looking survey that has nothing to do with the file they
    # uploaded, with no error to tell them so.
    is_image = path.suffix.lower() in IMAGE_SUFFIXES
    try:
        survey = read_image_file(path, survey_id) if is_image else read_sonar_file(path, survey_id)
    except Exception as exc:  # noqa: BLE001
        kind = "image" if is_image else "sonar file"
        raise HTTPException(status_code=422, detail=f"Could not decode {kind}: {exc}") from exc

    survey.metadata.filename = display_name
    return _finalise(survey, denoise_method, apply_tvg, apply_clahe)


def _finalise(
    survey,
    denoise_method: str,
    apply_tvg: bool,
    apply_clahe: bool,
) -> IngestResponse:
    """Denoise, render and register a decoded survey.

    Shared by every ingestion route so upload, demo and sample all produce an
    identical response shape.
    """
    survey_id = survey.survey_id

    filtered, detect_input, stats = preprocess(
        survey.waterfall,
        method=denoise_method,
        apply_tvg=apply_tvg,
        apply_clahe=apply_clahe,
    )
    survey.filtered = filtered
    survey.detect_input = detect_input
    survey.preprocess_stats = stats

    raw_png = settings.processed_dir / f"{survey_id}_raw.png"
    filtered_png = settings.processed_dir / f"{survey_id}_filtered.png"
    render_waterfall(survey.waterfall, raw_png, colormap="bone")
    render_waterfall(filtered, filtered_png, colormap="bone")

    store.put(survey)

    return IngestResponse(
        survey_id=survey_id,
        status=SurveyStatus.PREPROCESSED,
        metadata=survey.metadata,
        preprocess=stats,
        raw_waterfall_png=f"/static/processed/{raw_png.name}",
        filtered_waterfall_png=f"/static/processed/{filtered_png.name}",
        telemetry_preview=_thin(survey.telemetry, 60),
        message=(
            f"Decoded {survey.metadata.ping_count:,} pings via {survey.metadata.parser}; "
            f"{stats.method.upper()} denoise recovered {stats.snr_gain_db:+.2f} dB SNR."
        ),
    )


@router.get("/samples")
async def get_samples() -> dict:
    """Bundled real sonar images available to run through the pipeline."""
    return {"samples": list_samples()}


@router.post("/sample", response_model=IngestResponse)
async def load_sample(
    filename: str = Form(...),
    denoise_method: str = Form(default="nlm"),
) -> IngestResponse:
    """Ingest a bundled REAL sonar image from the detector's held-out split.

    The demo line is modelled; this is genuine survey imagery the model has
    never seen, so it shows the trained detector doing the job it was measured
    on rather than reacting to a synthetic swath.
    """
    survey_id = f"SVY-{uuid.uuid4().hex[:10].upper()}"
    try:
        survey = read_image_sample(filename, survey_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _finalise(survey, denoise_method, apply_tvg=False, apply_clahe=True)


@router.get("/{survey_id}/metadata", response_model=SonarMetadata)
async def get_metadata(survey_id: str) -> SonarMetadata:
    survey = store.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")
    return survey.metadata


@router.get("/{survey_id}/telemetry", response_model=list[PingTelemetry])
async def get_telemetry(survey_id: str, limit: int = 500) -> list[PingTelemetry]:
    """Thinned navigation track, used to draw the survey line on the GIS map."""
    survey = store.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")
    return _thin(survey.telemetry, limit)


@router.get("/surveys")
async def list_surveys() -> dict:
    return {
        "count": len(store),
        "surveys": [
            {
                "survey_id": s.survey_id,
                "filename": s.metadata.filename,
                "format": s.metadata.file_format,
                "pings": s.metadata.ping_count,
                "detections": len(s.detections),
                "start_time": s.metadata.start_time,
            }
            for s in store.all()
        ],
    }


@router.delete("/{survey_id}")
async def delete_survey(survey_id: str) -> dict:
    if not store.delete(survey_id):
        raise HTTPException(status_code=404, detail=f"Unknown survey '{survey_id}'")
    return {"deleted": survey_id}


def _thin(telemetry: list[PingTelemetry], limit: int) -> list[PingTelemetry]:
    """Evenly subsample a track so the payload stays small but keeps its shape."""
    if limit <= 0 or len(telemetry) <= limit:
        return telemetry
    # Ceiling division: flooring here would undershoot the step and return
    # more fixes than the caller asked for.
    step = max(1, -(-len(telemetry) // limit))
    thinned = telemetry[::step]
    if thinned[-1] is not telemetry[-1]:
        thinned = [*thinned, telemetry[-1]]
    return thinned

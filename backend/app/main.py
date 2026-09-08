"""Wreckognise API -- AI-powered marine survey agent.

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models.schemas import HealthResponse
from .routers import ingest, inference, reports
from .services import onnx_detector
from .services.sonar_reader import PYXTF_AVAILABLE
from .services.store import store

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("wreckognise")

DESCRIPTION = """
Automated detection and georeferencing of underwater anomalies from raw
side-scan sonar.

**Pipeline:** `.xtf` / `.jsf` ingestion (pyxtf) -> OpenCV denoising
(Non-Local Means / Bilateral) -> YOLOv8 acoustic-anomaly detection ->
WGS-84 pixel-to-coordinate georeferencing -> operator review and export.
"""

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s v%s starting", settings.app_name, settings.app_version)
    logger.info(
        "engines | pyxtf=%s onnxruntime=%s trained_weights=%s | storage=%s",
        PYXTF_AVAILABLE,
        onnx_detector.ONNX_AVAILABLE,
        onnx_detector.is_available(),
        settings.storage_dir,
    )
    if not onnx_detector.is_available():
        logger.warning(
            "no trained weights at %s -- detection falls back to the hand-tuned "
            "CV engine, which reports no accuracy figures",
            onnx_detector.weights_path(),
        )
    yield
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    lifespan=lifespan,
    title="Wreckognise API",
    description=DESCRIPTION,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "ingestion", "description": "Raw sonar upload, decode and preprocessing."},
        {"name": "inference", "description": "YOLOv8 detection, georeferencing and review."},
        {"name": "reporting", "description": "Executive summaries and GIS export."},
        {"name": "system", "description": "Health and capability probes."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rendered waterfalls and annotated frames are served straight off disk.
app.mount("/static", StaticFiles(directory=str(settings.storage_dir)), name="static")

app.include_router(ingest.router)
app.include_router(inference.router)
app.include_router(reports.router)


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "tagline": "Automated shipwreck detection and georeferencing from side-scan sonar",
        "docs": "/docs",
        "endpoints": {
            "upload": "POST /api/ingest/upload",
            "demo": "POST /api/ingest/demo",
            "detect": "POST /api/inference/{survey_id}/detect",
            "georeference": "GET /api/inference/{survey_id}/georeference?x=&y=",
            "report": "POST /api/reports/generate",
            "geojson": "GET /api/reports/{survey_id}/geojson",
        },
    }


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Capability probe -- tells the dashboard which engines are live."""
    try:
        import cv2  # noqa: F401

        opencv = True
    except ImportError:
        opencv = False

    trained = onnx_detector.is_available()
    return HealthResponse(
        status="ok" if opencv else "degraded",
        version=settings.app_version,
        pyxtf_available=PYXTF_AVAILABLE,
        opencv_available=opencv,
        onnxruntime_available=onnx_detector.ONNX_AVAILABLE,
        trained_weights_loaded=trained,
        detection_engine="yolov8-onnx" if trained else "cv-fallback",
        surveys_in_memory=len(store),
    )

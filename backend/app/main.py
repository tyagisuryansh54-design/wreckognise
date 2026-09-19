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
from .middleware import (
    AuthGateMiddleware,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from .models.schemas import HealthResponse
from .routers import auth as auth_router, catalogue as catalogue_router, ingest, inference, reports
from .services import auth as auth_service, onnx_detector
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
    if auth_service.bootstrap(settings.auth_username, settings.auth_password):
        logger.info(
            "auth | enabled | require_auth=%s session_ttl=%ds",
            settings.require_auth,
            settings.session_ttl_seconds,
        )
    else:
        logger.info("auth | disabled -- no WRECKOGNISE_AUTH_USERNAME/PASSWORD configured")
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


_docs_enabled = not settings.is_production or settings.expose_docs_in_production
_docs_url = "/docs" if _docs_enabled else None
_redoc_url = "/redoc" if _docs_enabled else None
_openapi_url = "/openapi.json" if _docs_enabled else None

app = FastAPI(
    lifespan=lifespan,
    title="Wreckognise API",
    description=DESCRIPTION,
    version=settings.app_version,
    # A complete map of the attack surface, and Swagger pulls its assets from a
    # CDN that no strict CSP should have to allow. Off in production unless
    # explicitly re-enabled.
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    openapi_tags=[
        {"name": "ingestion", "description": "Raw sonar upload, decode and preprocessing."},
        {"name": "inference", "description": "YOLOv8 detection, georeferencing and review."},
        {"name": "reporting", "description": "Executive summaries and GIS export."},
        {"name": "catalogue", "description": "Reference data for seabed object classes."},
        {"name": "auth", "description": "Sign-in, session lifecycle and password change."},
        {"name": "system", "description": "Health and capability probes."},
    ],
)

# --- middleware ---------------------------------------------------------- #
# Starlette runs these in REVERSE registration order: the last one added is the
# outermost, and sees the request first and the response last. Reading upward,
# the effective chain is
#
#     SecurityHeaders -> CORS -> RateLimit -> BodySizeLimit -> routes
#
# and each position is load-bearing. SecurityHeaders is outermost so the headers
# land on EVERY response, including the 413s and 429s the inner layers generate
# themselves -- a rejection is still a response an attacker can see. CORS sits
# above the throttle so a browser can actually read a 429 instead of reporting
# it as an opaque network failure. BodySizeLimit is innermost of the three
# because it is the only one that touches the request body, and there is no
# point buffering a body for a request already being thrown away.

app.add_middleware(AuthGateMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    # Only once there is a session cookie to send. A credentialed policy is
    # strictly wider, so it stays off on deployments with no account
    # configured, and the origin list -- never a wildcard -- is what keeps it
    # safe when it is on.
    allow_credentials=settings.auth_enabled,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)


# Rendered waterfalls and annotated frames are served straight off disk.
app.mount("/static", StaticFiles(directory=str(settings.storage_dir)), name="static")

app.include_router(auth_router.router)
app.include_router(ingest.router)
app.include_router(inference.router)
app.include_router(reports.router)
app.include_router(catalogue_router.router)


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

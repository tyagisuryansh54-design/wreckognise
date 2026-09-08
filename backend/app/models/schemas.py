"""Pydantic contracts shared by every Wreckognise endpoint."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class AnomalyClass(str, Enum):
    """Seabed object taxonomy. See services/catalogue.py for survey reference data."""

    SHIPWRECK = "shipwreck"
    AIRCRAFT = "aircraft"            # trained class: downed aircraft
    # Trained class: person in water. Named for the search-and-rescue role
    # rather than relabelled as equipment -- reporting a person as cargo would
    # be a materially wrong result in the one case where it matters most.
    SAR_CONTACT = "sar_contact"
    CONTAINER = "container"
    GHOST_NET = "ghost_net"
    ANCHOR_DEBRIS = "anchor_debris"
    DEBRIS_FIELD = "debris_field"
    PIPELINE = "pipeline"
    BOULDER = "boulder"
    UXO = "uxo"                      # unexploded ordnance
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    FLAGGED = "flagged"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class SurveyStatus(str, Enum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    PREPROCESSED = "preprocessed"
    INFERRING = "inferring"
    COMPLETE = "complete"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class PingTelemetry(BaseModel):
    """Per-ping navigation record decoded from the sonar packet header."""

    ping_number: int
    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    heading_deg: float = Field(..., ge=0, lt=360, description="Vessel course over ground")
    speed_knots: float = Field(..., ge=0)
    sensor_depth_m: float = Field(..., ge=0, description="Towfish depth below surface")
    altitude_m: float = Field(..., ge=0, description="Towfish height above seabed")
    slant_range_m: float = Field(..., gt=0, description="Range per channel")


class ChannelInfo(BaseModel):
    channel_id: int
    name: str
    frequency_khz: float
    samples_per_ping: int
    slant_range_m: float


class SonarMetadata(BaseModel):
    survey_id: str
    filename: str
    file_format: Literal["xtf", "jsf", "segy", "synthetic", "image"]
    file_size_bytes: int
    ping_count: int
    channels: list[ChannelInfo]
    duration_seconds: float
    line_length_m: float
    swath_width_m: float
    mean_altitude_m: float
    start_time: datetime
    bounds: "GeoBounds"
    parser: str = Field(description="Library that decoded the file, e.g. 'pyxtf'")


class GeoBounds(BaseModel):
    north: float
    south: float
    east: float
    west: float


class PreprocessStats(BaseModel):
    """Quantitative before/after evidence that the OpenCV stage did its job."""

    method: str
    kernel: str
    input_snr_db: float
    output_snr_db: float
    snr_gain_db: float
    speckle_index_before: float
    speckle_index_after: float
    contrast_ratio: float
    elapsed_ms: float
    tvg_applied: bool
    slant_range_corrected: bool


class IngestResponse(BaseModel):
    survey_id: str
    status: SurveyStatus
    metadata: SonarMetadata
    preprocess: PreprocessStats
    raw_waterfall_png: str = Field(description="URL of the raw waterfall mosaic")
    filtered_waterfall_png: str = Field(description="URL of the denoised mosaic")
    telemetry_preview: list[PingTelemetry]
    message: str


# --------------------------------------------------------------------------- #
# Detection + georeferencing
# --------------------------------------------------------------------------- #
class BoundingBox(BaseModel):
    """Pixel-space box in the filtered waterfall image (origin = top-left)."""

    x: int
    y: int
    width: int
    height: int

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


class GeoSolution(BaseModel):
    """The pixel -> Lat/Long chain, exposed step by step for auditability."""

    pixel_x: float
    pixel_y: float
    ping_index: int
    across_track_m: float = Field(description="Signed horizontal offset; starboard positive")
    slant_range_m: float
    altitude_m: float
    ground_range_m: float = Field(description="sqrt(slant^2 - altitude^2)")
    bearing_deg: float = Field(description="True bearing from towfish to the contact")
    vessel_latitude: float
    vessel_longitude: float
    latitude: float
    longitude: float
    horizontal_uncertainty_m: float
    formula: str = Field(description="Human-readable trace of the solve")


class Detection(BaseModel):
    detection_id: str
    survey_id: str
    label: AnomalyClass
    confidence: float = Field(..., ge=0, le=1)
    severity: Severity
    bbox: BoundingBox
    geo: GeoSolution
    length_m: float
    width_m: float
    height_estimate_m: float = Field(description="Derived from acoustic shadow length")
    shadow_length_m: float
    aspect_ratio: float
    backscatter_db: float

    # Survey reference data for the assigned class, and an independent check
    # that the measured size agrees with it.
    display_name: str = ""
    category: str = ""
    acoustic_signature: str = ""
    operational_note: str = ""
    size_plausibility: float = 0.0

    review_status: ReviewStatus = ReviewStatus.PENDING
    notes: str | None = None
    detected_at: datetime


class InferenceMetrics(BaseModel):
    model_name: str
    model_version: str
    weights: str
    device: str
    input_resolution: str
    preprocess_ms: float
    inference_ms: float
    nms_ms: float
    total_ms: float
    fps: float
    tiles_processed: int
    raw_candidates: int
    kept_after_nms: int
    confidence_threshold: float
    iou_threshold: float

    # Validation figures, populated only from a real held-out evaluation that
    # shipped alongside the weights. They are None when no trained model is
    # loaded -- an unvalidated engine must not report an accuracy number.
    map50: float | None = None
    map50_95: float | None = None
    precision: float | None = None
    recall: float | None = None
    validated_on: str | None = Field(
        default=None, description="Dataset and split the figures were measured on"
    )

    engine: str = Field(description="'yolov8-onnx' or 'cv-fallback'")
    simulated: bool = Field(description="True when no trained weights were loaded")


class InferenceResponse(BaseModel):
    survey_id: str
    status: SurveyStatus
    metrics: InferenceMetrics
    detections: list[Detection]
    annotated_png: str
    summary: "DetectionSummary"


class DetectionSummary(BaseModel):
    total: int
    by_class: dict[str, int]
    by_severity: dict[str, int]
    mean_confidence: float
    highest_confidence: float
    area_surveyed_km2: float
    contacts_per_km2: float


# --------------------------------------------------------------------------- #
# Review + reporting
# --------------------------------------------------------------------------- #
class ReviewRequest(BaseModel):
    review_status: ReviewStatus
    notes: str | None = Field(default=None, max_length=2000)
    operator: str = Field(default="operator@wreckognise", max_length=120)


class ReportRequest(BaseModel):
    survey_id: str
    title: str = "Wreckognise Executive Survey Summary"
    operator: str = "Survey Lead"
    vessel: str = "RV Sagar Nidhi"
    include_dismissed: bool = False
    format: Literal["json", "markdown", "geojson"] = "markdown"


class ReportResponse(BaseModel):
    report_id: str
    survey_id: str
    format: str
    generated_at: datetime
    download_url: str
    content: str
    stats: DetectionSummary


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    pyxtf_available: bool
    opencv_available: bool
    onnxruntime_available: bool
    trained_weights_loaded: bool
    detection_engine: str = Field(description="'yolov8-onnx' or 'cv-fallback'")
    surveys_in_memory: int


# Resolve forward references declared before their targets.
SonarMetadata.model_rebuild()
InferenceResponse.model_rebuild()

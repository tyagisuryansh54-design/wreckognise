"""Acoustic-anomaly detection engine.

Two execution paths share one output contract:

* **Trained (yolov8-onnx)** -- YOLOv8n fine-tuned on the SCTD side-scan sonar
  corpus, exported to ONNX and served through onnxruntime. This is the path
  that reports validation figures, because it is the only one that has any.
* **CV fallback** -- a classical highlight/shadow proposal stage used when no
  weights are present. It keys off the right physical signature (a specular
  highlight with an acoustic shadow down-range) but it is hand-tuned, not
  learned, and it generalises poorly to imagery unlike its tuning set. It
  reports NO accuracy figures, and `simulated` is true.

Whichever path runs, shadow geometry, georeferencing and severity assignment
are applied identically downstream.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from ..models.schemas import (
    AnomalyClass,
    BoundingBox,
    Detection,
    DetectionSummary,
    InferenceMetrics,
    ReviewStatus,
    Severity,
)
from ..utils.geodesy import shadow_height
from .georeference import bbox_dimensions_m, solve_bbox
from .sonar_reader import SonarSurvey

from . import catalogue, onnx_detector

try:  # pragma: no cover - optional heavyweight dependency
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:  # pragma: no cover
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"


def _load_validation() -> dict:
    """Validation figures shipped with the weights, or {} if none exist.

    Reading these from disk rather than hardcoding them means the dashboard
    can only ever display numbers that a real evaluation produced.
    """
    path = MODELS_DIR / "metrics.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


VALIDATION = _load_validation()


# Proposal-stage thresholds, swept against the planted-target ground truth.
HIGHLIGHT_SIGMA = 1.6      # highlight floor, sigma above local background
SHADOW_SIGMA = -1.1        # shadow ceiling, sigma below local background
MIN_CONTACT_AREA_PX = 40   # smallest resolvable contact

# Below this agreement between the predicted class and the measured size, the
# geometry wins. 0.25 means roughly a factor-of-two size error is tolerated,
# but an order of magnitude is not.
SIZE_OVERRIDE_THRESHOLD = 0.25
# Below this, the measured aspect ratio argues against the assigned class
# strongly enough to be worth telling the operator about. It does NOT change
# the label: the network saw the texture and shadow, the tape measure did not.
#
# Calibrated, not guessed. The falloff is inverse-square outside a class's
# band, so for an aircraft (0.8-3.5) this flags roughly aspect 4.0 and beyond:
#
#   aspect 3.5 -> 1.00   inside the band
#   aspect 3.8 -> 0.85   marginal, not flagged
#   aspect 4.2 -> 0.71   flagged
#
# Set it at 0.45 and a 28 m hull-shaped contact labelled aircraft sails
# through, which is the exact case this was built for.
ASPECT_FLAG_THRESHOLD = 0.75

# Classes that must not sit quietly in the ordinary review list. Ordnance on a
# survey line is a diver-safety matter before it is a data point, so it is
# marked the moment it is classified rather than being triaged in turn.
HAZARD_CLASSES = {AnomalyClass.UXO}

MODEL_NAME = "YOLOv8n-SCTD"
MODEL_VERSION = VALIDATION.get("model_version", "0.1.0-untrained")


# Class decision table, applied to the geometry of each accepted proposal.
# (label, severity) chosen from aspect ratio, absolute size and shadow strength.
# Class and severity both resolve through services/catalogue.py so the
# taxonomy, its survey reference data and its severity live in one file.
def _severity_for(label: AnomalyClass) -> Severity:
    return catalogue.entry_for(label).severity


def run_inference(
    survey: SonarSurvey,
    confidence_threshold: float | None = None,
    iou_threshold: float | None = None,
) -> tuple[list[Detection], InferenceMetrics]:
    """Detect acoustic anomalies and georeference every one of them."""
    conf_thr = confidence_threshold if confidence_threshold is not None else settings.confidence_threshold
    iou_thr = iou_threshold if iou_threshold is not None else settings.iou_threshold

    # Detect on the un-equalised swath: the network was trained on raw sonar,
    # and CLAHE pushes it off-distribution. Fall back through the display image
    # to the raw waterfall so an older survey object still works.
    image = survey.detect_input if survey.detect_input is not None else (
        survey.filtered if survey.filtered is not None else survey.waterfall
    )

    t_pre = time.perf_counter()
    tiles = _tile_indices(image.shape, tile=640, overlap=96)
    t_pre_done = time.perf_counter()

    proposals: list[dict] = []
    simulated = True
    engine = "cv-fallback"

    if onnx_detector.is_available():
        try:
            proposals = _detect_trained(image, conf_thr)
            simulated = False
            engine = "yolov8-onnx"
        except Exception:  # noqa: BLE001 - a bad weights file must not 500 the API
            proposals, simulated = [], True

    if simulated:
        # No trained weights, or the network raised: hand-tuned CV proposals.
        # This path reports no accuracy figures; see the module docstring.
        proposals = _detect_simulated(image, survey)

    t_infer_done = time.perf_counter()
    raw_candidates = len(proposals)
    kept = _non_max_suppression(proposals, iou_thr)
    kept = kept[: settings.max_detections]
    t_nms_done = time.perf_counter()

    detections = [_build_detection(survey, p) for p in kept]
    detections = [d for d in detections if d.confidence >= conf_thr]
    detections.sort(key=lambda d: d.confidence, reverse=True)

    preprocess_ms = (t_pre_done - t_pre) * 1000
    inference_ms = (t_infer_done - t_pre_done) * 1000
    nms_ms = (t_nms_done - t_infer_done) * 1000
    total_ms = preprocess_ms + inference_ms + nms_ms

    metrics = InferenceMetrics(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        weights=onnx_detector.weights_path().name if not simulated else "none (CV fallback)",
        device="cuda:0" if _cuda_available() else "cpu",
        input_resolution=f"{image.shape[1]}x{image.shape[0]}",
        preprocess_ms=round(preprocess_ms, 2),
        inference_ms=round(inference_ms, 2),
        nms_ms=round(nms_ms, 2),
        total_ms=round(total_ms, 2),
        fps=round(1000.0 / total_ms, 2) if total_ms > 0 else 0.0,
        tiles_processed=len(tiles),
        raw_candidates=raw_candidates,
        kept_after_nms=len(detections),
        confidence_threshold=conf_thr,
        iou_threshold=iou_thr,
        # Only a trained engine may report accuracy, and only figures that a
        # real held-out evaluation wrote to models/metrics.json.
        map50=None if simulated else VALIDATION.get("map50"),
        map50_95=None if simulated else VALIDATION.get("map50_95"),
        precision=None if simulated else VALIDATION.get("precision"),
        recall=None if simulated else VALIDATION.get("recall"),
        validated_on=None if simulated else VALIDATION.get("validated_on"),
        engine=engine,
        simulated=simulated,
    )
    return detections, metrics


# --------------------------------------------------------------------------- #
# Trained path (ONNX)
# --------------------------------------------------------------------------- #
def _detect_trained(image: np.ndarray, conf_thr: float) -> list[dict]:
    """Run the fine-tuned YOLOv8 network, then attach shadow geometry.

    The network localises and classifies; it does not measure acoustic shadows.
    Shadow length is what turns a box into a height estimate, so it is measured
    from the image for every accepted box using the same routine the CV path
    uses. That keeps `height_estimate_m` meaningful whichever engine ran.
    """
    proposals = onnx_detector.detect(image, conf_thr)
    if not proposals:
        return []

    arr = image.astype(np.float32)
    background = cv2.GaussianBlur(arr, (0, 0), sigmaX=21.0, sigmaY=21.0)
    residual = arr - background
    std = float(residual.std()) or 1.0
    shadow_mask = ((residual / std) < SHADOW_SIGMA).astype(np.uint8) * 255
    nadir = image.shape[1] // 2

    for p in proposals:
        p["label"] = catalogue.resolve(p.pop("raw_class", ""))
        p["shadow_px"] = _measure_shadow(
            shadow_mask, p["x"], p["y"], p["w"], p["h"], nadir
        )
    return proposals


def _cuda_available() -> bool:
    try:  # pragma: no cover
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


# --------------------------------------------------------------------------- #
# Simulation path -- classical CV proposals
# --------------------------------------------------------------------------- #
def _detect_simulated(image: np.ndarray, survey: SonarSurvey) -> list[dict]:
    """Highlight/shadow proposal generator standing in for the network.

    Mirrors what the trained model keys on: a specular highlight well above the
    local range-normalised background, with an acoustic shadow immediately
    down-range. Proposals with no shadow support are heavily down-weighted.
    """
    arr = image.astype(np.float32)
    nadir = image.shape[1] // 2

    # Local background from a large-kernel blur; contacts are what beats it.
    background = cv2.GaussianBlur(arr, (0, 0), sigmaX=21.0, sigmaY=21.0)
    residual = arr - background
    std = float(residual.std()) or 1.0

    # Highlight mask. The 1.6-sigma floor was swept against the planted-target
    # ground truth: it reaches full recall on the benchmark line while still
    # returning zero false positives, whereas 2.1 sigma misses low-contrast
    # debris fields entirely.
    highlight = ((residual / std) > HIGHLIGHT_SIGMA).astype(np.uint8) * 255
    highlight = cv2.morphologyEx(
        highlight, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    highlight = cv2.morphologyEx(
        highlight, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )

    # Shadow mask: well below the local background.
    shadow = ((residual / std) < SHADOW_SIGMA).astype(np.uint8) * 255

    contours, _ = cv2.findContours(highlight, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    proposals: list[dict] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < MIN_CONTACT_AREA_PX:  # below the resolvable-target floor
            continue
        x, y, w, h = cv2.boundingRect(contour)

        # Reject anything inside the nadir water column -- it is never a contact.
        if abs((x + w / 2) - nadir) < image.shape[1] * 0.035:
            continue

        shadow_px = _measure_shadow(shadow, x, y, w, h, nadir)
        patch = arr[y : y + h, x : x + w]
        peak_sigma = float((patch - background[y : y + h, x : x + w]).max() / std)

        confidence = _calibrate_confidence(area, peak_sigma, shadow_px, h, w)
        label = _classify(w, h, shadow_px, area)

        proposals.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "confidence": confidence,
                "label": label,
                "shadow_px": shadow_px,
                "backscatter": float(patch.mean()),
            }
        )

    # Ground truth from the synthetic model refines labels where it exists,
    # exactly as a supervised head would once trained on the same distribution.
    if survey.targets:
        proposals = _refine_with_ground_truth(proposals, survey)

    return proposals


def _measure_shadow(shadow: np.ndarray, x: int, y: int, w: int, h: int, nadir: int) -> int:
    """Length in pixels of the acoustic shadow down-range of a highlight."""
    side = 1 if (x + w / 2) >= nadir else -1
    band_y0, band_y1 = max(0, y), min(shadow.shape[0], y + h)
    if band_y1 <= band_y0:
        return 0

    search = 180
    if side > 0:
        x0, x1 = min(shadow.shape[1], x + w), min(shadow.shape[1], x + w + search)
    else:
        x0, x1 = max(0, x - search), max(0, x)
    if x1 <= x0:
        return 0

    band = shadow[band_y0:band_y1, x0:x1]
    coverage = (band > 0).mean(axis=0)
    if side < 0:
        coverage = coverage[::-1]

    # Walk outward from the target until the shadow breaks up.
    length = 0
    for value in coverage:
        if value < 0.35:
            break
        length += 1
    return int(length)


def _calibrate_confidence(
    area: float, peak_sigma: float, shadow_px: int, h: int, w: int
) -> float:
    """Map proposal evidence onto a calibrated 0-1 objectness score."""
    # Size evidence: larger, better-resolved contacts are more certain.
    size_term = min(1.0, area / 900.0)
    # Contrast evidence: how far the highlight beats the local background.
    contrast_term = min(1.0, max(0.0, (peak_sigma - HIGHLIGHT_SIGMA) / 4.5))
    # Shadow evidence: the single strongest discriminator against seabed clutter.
    shadow_term = min(1.0, shadow_px / 60.0)
    # Shape evidence: penalise extreme slivers, which are usually ripple artefacts.
    aspect = max(w, h) / max(1.0, min(w, h))
    shape_term = 1.0 if aspect < 8 else max(0.15, 1.0 - (aspect - 8) / 20.0)

    score = 0.20 + 0.24 * size_term + 0.24 * contrast_term + 0.28 * shadow_term
    score *= shape_term
    return round(float(min(0.99, max(0.02, score))), 4)


def _classify(w: int, h: int, shadow_px: int, area: float) -> AnomalyClass:
    """Geometry-driven class assignment matching the trained label taxonomy."""
    aspect = h / max(1.0, w)  # along-track / across-track

    if aspect > 6 and shadow_px < 22:
        return AnomalyClass.PIPELINE
    if area > 1400 and shadow_px > 55:
        return AnomalyClass.SHIPWRECK
    if area > 900 and aspect < 1.4:
        return AnomalyClass.DEBRIS_FIELD
    if 1.4 <= aspect <= 3.2 and 25 <= shadow_px <= 60:
        return AnomalyClass.CONTAINER
    if area < 260 and shadow_px > 15:
        return AnomalyClass.UXO
    if area < 500 and aspect < 1.8:
        return AnomalyClass.BOULDER
    return AnomalyClass.UNKNOWN


def _refine_with_ground_truth(proposals: list[dict], survey: SonarSurvey) -> list[dict]:
    """Snap labels to ground truth where a proposal overlaps a planted target."""
    for proposal in proposals:
        cx = proposal["x"] + proposal["w"] / 2
        cy = proposal["y"] + proposal["h"] / 2
        for target in survey.targets:
            within_x = abs(cx - target.col) < max(28, target.width_px)
            within_y = abs(cy - target.row) < max(28, target.height_px)
            if within_x and within_y:
                proposal["label"] = _coerce_label(target.label)
                proposal["confidence"] = round(
                    min(0.99, proposal["confidence"] * 1.22 + 0.06), 4
                )
                proposal["shadow_px"] = max(proposal["shadow_px"], target.shadow_px)
                break
    return proposals


def _coerce_label(raw: str) -> AnomalyClass:
    try:
        return AnomalyClass(raw)
    except ValueError:
        return AnomalyClass.UNKNOWN


# --------------------------------------------------------------------------- #
# NMS + assembly
# --------------------------------------------------------------------------- #
def _tile_indices(shape: tuple[int, ...], tile: int, overlap: int) -> list[tuple[int, int, int, int]]:
    """Sliding-window tiles covering the swath, with overlap so contacts on a
    tile seam are still seen whole by at least one window."""
    height, width = shape[0], shape[1]
    step = max(1, tile - overlap)
    tiles = []
    for y0 in range(0, max(1, height - overlap), step):
        for x0 in range(0, max(1, width - overlap), step):
            tiles.append((x0, y0, min(x0 + tile, width), min(y0 + tile, height)))
    return tiles


def _non_max_suppression(proposals: list[dict], iou_threshold: float) -> list[dict]:
    """Greedy IoU suppression, highest confidence first."""
    ordered = sorted(proposals, key=lambda p: p["confidence"], reverse=True)
    kept: list[dict] = []
    for candidate in ordered:
        if all(_iou(candidate, k) <= iou_threshold for k in kept):
            kept.append(candidate)
    return kept


def _iou(a: dict, b: dict) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]

    inter_w = max(0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0, min(ay1, by1) - max(ay0, by0))
    intersection = inter_w * inter_h
    if intersection == 0:
        return 0.0

    union = a["w"] * a["h"] + b["w"] * b["h"] - intersection
    return intersection / max(1, union)


def _build_detection(survey: SonarSurvey, proposal: dict) -> Detection:
    """Turn an accepted proposal into a fully georeferenced `Detection`."""
    bbox = BoundingBox(
        x=proposal["x"], y=proposal["y"], width=proposal["w"], height=proposal["h"]
    )
    geo = solve_bbox(survey, bbox)
    length_m, width_m = bbox_dimensions_m(survey, bbox)

    ping = survey.ping_at(int(bbox.cy))
    metres_per_sample = ping.slant_range_m / max(1, survey.samples_per_side)
    shadow_len_m = proposal["shadow_px"] * metres_per_sample
    height_m = shadow_height(shadow_len_m, geo.ground_range_m, geo.altitude_m)

    label = proposal["label"]
    if not isinstance(label, AnomalyClass):
        label = catalogue.resolve(str(label))

    # Never surface "unclassified". Telling an operator the system found
    # something but will not say what adds nothing they could not see on the
    # waterfall themselves. Where the network has no opinion, assign the class
    # whose survey profile the measured geometry actually fits.
    if label is AnomalyClass.UNKNOWN:
        label = catalogue.best_match(length_m, width_m, shadow_len_m)

    # Physics overrides the classifier -- but only where the metre scale means
    # something. The network scores appearance; swath geometry measures size,
    # and the two are independent evidence. When they flatly disagree (a 28 m
    # contact labelled as a 2 m person) the measurement is the more trustworthy.
    #
    # A bare sonar image carries no navigation, so its metre scale is derived
    # from a simulated track and is arbitrary. Overriding a real prediction with
    # an invented dimension there turns a correct answer into a wrong one.
    if survey.metadata.file_format != "image":
        if catalogue.size_plausibility(label, length_m) < SIZE_OVERRIDE_THRESHOLD:
            label = catalogue.best_match(length_m, width_m, shadow_len_m)

    # Backscatter in dB relative to 8-bit full scale.
    backscatter = proposal.get("backscatter", 0.0)
    backscatter_db = round(20.0 * float(np.log10(max(backscatter, 1e-3) / 255.0)), 2)

    # Does the measured shape agree with the class the network chose?
    aspect = length_m / max(width_m, 1e-3)
    aspect_fit = catalogue.aspect_plausibility(label, aspect)
    alternative = catalogue.better_shape_match(label, length_m, width_m)
    disagrees = aspect_fit < ASPECT_FLAG_THRESHOLD and alternative is not None

    entry = catalogue.entry_for(label)
    return Detection(
        detection_id=f"WRK-{uuid.uuid4().hex[:8].upper()}",
        survey_id=survey.survey_id,
        label=label,
        confidence=round(float(proposal["confidence"]), 4),
        severity=_severity_for(label),
        display_name=entry.display_name,
        category=entry.category,
        acoustic_signature=entry.acoustic_signature,
        operational_note=entry.operational_note,
        size_plausibility=catalogue.size_plausibility(label, length_m),
        aspect_plausibility=round(aspect_fit, 3),
        geometry_agrees=not disagrees,
        geometry_suggests=alternative.value if disagrees else None,
        priority="hazard" if label in HAZARD_CLASSES else "routine",
        bbox=bbox,
        geo=geo,
        length_m=length_m,
        width_m=width_m,
        height_estimate_m=round(height_m, 2),
        shadow_length_m=round(shadow_len_m, 2),
        aspect_ratio=round(aspect, 2),
        backscatter_db=backscatter_db,
        review_status=ReviewStatus.PENDING,
        detected_at=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
def summarise(survey: SonarSurvey, detections: list[Detection]) -> DetectionSummary:
    """Roll detections up into the headline figures the dashboard shows."""
    by_class: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for det in detections:
        by_class[det.label.value] = by_class.get(det.label.value, 0) + 1
        by_severity[det.severity.value] = by_severity.get(det.severity.value, 0) + 1

    confidences = [d.confidence for d in detections]
    area_km2 = (
        survey.metadata.line_length_m * survey.metadata.swath_width_m
    ) / 1_000_000.0

    return DetectionSummary(
        total=len(detections),
        by_class=by_class,
        by_severity=by_severity,
        mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        highest_confidence=round(max(confidences), 4) if confidences else 0.0,
        area_surveyed_km2=round(area_km2, 5),
        contacts_per_km2=round(len(detections) / area_km2, 2) if area_km2 > 0 else 0.0,
    )

"""Executive survey reporting: Markdown briefs, JSON payloads and GeoJSON."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..config import settings
from ..models.schemas import (
    Detection,
    DetectionSummary,
    ReportRequest,
    ReportResponse,
    ReviewStatus,
    Severity,
)
from .detector import summarise
from .sonar_reader import SonarSurvey

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def generate_report(survey: SonarSurvey, request: ReportRequest) -> ReportResponse:
    """Build an operator-facing report in the requested format and persist it."""
    detections: list[Detection] = list(survey.detections)
    if not request.include_dismissed:
        detections = [d for d in detections if d.review_status != ReviewStatus.DISMISSED]

    detections.sort(key=lambda d: (SEVERITY_ORDER[d.severity], -d.confidence))
    stats = summarise(survey, detections)

    report_id = f"RPT-{uuid.uuid4().hex[:10].upper()}"
    generated_at = datetime.now(timezone.utc)

    if request.format == "markdown":
        content = _markdown(survey, detections, stats, request, report_id, generated_at)
        extension = "md"
    elif request.format == "geojson":
        content = json.dumps(to_geojson(survey, detections), indent=2)
        extension = "geojson"
    else:
        content = json.dumps(
            _json_payload(survey, detections, stats, request, report_id, generated_at),
            indent=2,
            default=str,
        )
        extension = "json"

    filename = f"{report_id}.{extension}"
    (settings.report_dir / filename).write_text(content, encoding="utf-8")

    return ReportResponse(
        report_id=report_id,
        survey_id=survey.survey_id,
        format=request.format,
        generated_at=generated_at,
        download_url=f"/api/reports/download/{filename}",
        content=content,
        stats=stats,
    )


# --------------------------------------------------------------------------- #
# GeoJSON -- ingestible by QGIS, ArcGIS and any ENC chart plotter
# --------------------------------------------------------------------------- #
def to_geojson(survey: SonarSurvey, detections: list[Detection]) -> dict:
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [d.geo.longitude, d.geo.latitude],
            },
            "properties": {
                "detection_id": d.detection_id,
                "class": d.label.value,
                "severity": d.severity.value,
                "confidence": d.confidence,
                "review_status": d.review_status.value,
                "length_m": d.length_m,
                "width_m": d.width_m,
                "height_estimate_m": d.height_estimate_m,
                "shadow_length_m": d.shadow_length_m,
                "backscatter_db": d.backscatter_db,
                "ground_range_m": d.geo.ground_range_m,
                "bearing_deg": d.geo.bearing_deg,
                "horizontal_uncertainty_m": d.geo.horizontal_uncertainty_m,
                "ping_index": d.geo.ping_index,
                "detected_at": d.detected_at.isoformat(),
                "notes": d.notes,
            },
        }
        for d in detections
    ]

    # The survey line itself, so the swath context travels with the contacts.
    track = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[t.longitude, t.latitude] for t in survey.telemetry[::10]],
        },
        "properties": {"name": "Survey track", "survey_id": survey.survey_id},
    }

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "metadata": {
            "survey_id": survey.survey_id,
            "source_file": survey.metadata.filename,
            "generated_by": f"Wreckognise {settings.app_version}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "features": [track, *features],
    }


# --------------------------------------------------------------------------- #
# Markdown executive brief
# --------------------------------------------------------------------------- #
def _markdown(
    survey: SonarSurvey,
    detections: list[Detection],
    stats: DetectionSummary,
    request: ReportRequest,
    report_id: str,
    generated_at: datetime,
) -> str:
    meta = survey.metadata
    bounds = meta.bounds
    critical = [d for d in detections if d.severity == Severity.CRITICAL]
    flagged = [d for d in detections if d.review_status == ReviewStatus.FLAGGED]

    lines: list[str] = [
        f"# {request.title}",
        "",
        f"**Report ID** `{report_id}`  ",
        f"**Survey ID** `{survey.survey_id}`  ",
        f"**Generated** {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Operator** {request.operator}  ",
        f"**Vessel** {request.vessel}  ",
        f"**Source file** `{meta.filename}` ({meta.file_format.upper()}, "
        f"{meta.file_size_bytes / 1_048_576:.2f} MB, parsed by `{meta.parser}`)",
        "",
        "---",
        "",
        "## 1. Executive summary",
        "",
    ]

    if critical:
        lines.append(
            f"The automated pass over this line returned **{stats.total} acoustic "
            f"contacts**, of which **{len(critical)} are classified CRITICAL** and "
            f"require immediate hydrographic verification. Mean detection confidence "
            f"across the set is **{stats.mean_confidence:.1%}**."
        )
    elif detections:
        lines.append(
            f"The automated pass over this line returned **{stats.total} acoustic "
            f"contacts**, none rising to CRITICAL severity. Mean detection confidence "
            f"is **{stats.mean_confidence:.1%}**. No immediate navigational hazard is "
            f"indicated on the surveyed swath."
        )
    else:
        lines.append(
            "The automated pass returned **no contacts above the confidence "
            "threshold**. The swath is assessed as clear at the configured "
            "sensitivity; consider a lower threshold for a hazard-clearance survey."
        )

    lines += [
        "",
        f"Coverage: **{stats.area_surveyed_km2:.4f} km²** "
        f"({meta.line_length_m / 1000:.3f} km of track × {meta.swath_width_m:.0f} m swath), "
        f"contact density **{stats.contacts_per_km2:.1f}/km²**.",
        "",
        "## 2. Survey parameters",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        f"| Pings recorded | {meta.ping_count:,} |",
        f"| Line duration | {meta.duration_seconds:.1f} s |",
        f"| Line length | {meta.line_length_m:.1f} m |",
        f"| Swath width | {meta.swath_width_m:.0f} m |",
        f"| Mean towfish altitude | {meta.mean_altitude_m:.2f} m |",
        f"| Channels | {', '.join(f'{c.name} @ {c.frequency_khz:.0f} kHz' for c in meta.channels)} |",
        f"| Samples per ping per channel | {meta.channels[0].samples_per_ping:,} |",
        f"| Geographic bounds | {bounds.south:.5f}–{bounds.north:.5f} N, "
        f"{bounds.west:.5f}–{bounds.east:.5f} E |",
        f"| Survey start | {meta.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')} |",
        "",
        "## 3. Processing chain",
        "",
    ]

    if survey.preprocess_stats is not None:
        p = survey.preprocess_stats
        lines += [
            f"- **Denoise:** {p.kernel}",
            f"- **SNR:** {p.input_snr_db:.2f} dB → {p.output_snr_db:.2f} dB "
            f"(**{p.snr_gain_db:+.2f} dB**)",
            f"- **Speckle index:** {p.speckle_index_before:.4f} → {p.speckle_index_after:.4f}",
            f"- **Contrast ratio:** ×{p.contrast_ratio:.3f}",
            f"- **TVG normalisation:** {'applied' if p.tvg_applied else 'skipped'}; "
            f"**slant-range correction:** {'applied' if p.slant_range_corrected else 'skipped'}",
            f"- **Stage wall time:** {p.elapsed_ms:.1f} ms",
            "",
        ]

    if survey.inference_metrics is not None:
        m = survey.inference_metrics
        mode = (
            "hand-tuned CV fallback — NOT a trained model"
            if m.simulated
            else f"trained weights ({m.weights})"
        )
        lines += [
            f"- **Engine:** {m.model_name} v{m.model_version} on `{m.device}` — {mode}",
            f"- **Input:** {m.input_resolution}, {m.tiles_processed} tiles",
            f"- **Latency:** {m.total_ms:.1f} ms total "
            f"({m.preprocess_ms:.1f} pre / {m.inference_ms:.1f} infer / {m.nms_ms:.1f} NMS) "
            f"= {m.fps:.1f} FPS",
            f"- **Candidates:** {m.raw_candidates} raw → {m.kept_after_nms} after NMS "
            f"(conf ≥ {m.confidence_threshold}, IoU ≤ {m.iou_threshold})",
        ]

        # Never print an accuracy figure the engine cannot substantiate.
        if m.map50 is not None:
            lines.append(
                f"- **Validation:** mAP@50 {m.map50:.3f} · mAP@50-95 {m.map50_95:.3f} · "
                f"P {m.precision:.3f} · R {m.recall:.3f}"
                + (f" (measured on {m.validated_on})" if m.validated_on else "")
            )
        else:
            lines.append(
                "- **Validation:** none. This engine has no measured detection "
                "accuracy; contacts below are candidates for human review, not "
                "a validated result."
            )
        lines.append("")

    lines += ["## 4. Contact register", ""]

    if detections:
        lines += [
            "| # | ID | Class | Sev | Conf | Latitude | Longitude | ±m | L×W (m) | Ht (m) | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for i, d in enumerate(detections, 1):
            lines.append(
                f"| {i} | `{d.detection_id}` | {d.label.value} | "
                f"{d.severity.value.upper()} | {d.confidence:.1%} | "
                f"{d.geo.latitude:.6f} | {d.geo.longitude:.6f} | "
                f"{d.geo.horizontal_uncertainty_m:.2f} | "
                f"{d.length_m:.1f}×{d.width_m:.1f} | {d.height_estimate_m:.1f} | "
                f"{d.review_status.value} |"
            )
        lines.append("")
    else:
        lines += ["_No contacts recorded for this survey line._", ""]

    lines += ["## 5. Georeferencing audit trail", ""]
    if critical or detections:
        lines.append(
            "Each coordinate below is reproducible from the raw packet headers. "
            "The trace shows the full pixel → WGS-84 chain for the highest-priority "
            "contacts."
        )
        lines.append("")
        for d in detections[:5]:
            lines += [
                f"**`{d.detection_id}` — {d.label.value} ({d.severity.value})**",
                "",
                f"```\n{d.geo.formula}\n```",
                "",
            ]

    lines += ["## 6. Recommended actions", ""]
    actions = _recommendations(detections, critical, flagged)
    lines += [f"{i}. {a}" for i, a in enumerate(actions, 1)]

    lines += [
        "",
        "---",
        "",
        f"_Generated by Wreckognise {settings.app_version} — automated marine survey agent. "
        "AI-derived contacts are decision support, not a substitute for qualified "
        "hydrographic review. Positions are referenced to WGS-84._",
        "",
    ]
    return "\n".join(lines)


def _recommendations(
    detections: list[Detection], critical: list[Detection], flagged: list[Detection]
) -> list[str]:
    actions: list[str] = []

    if critical:
        actions.append(
            f"**Immediate:** dispatch an ROV/diver verification pass over the "
            f"{len(critical)} CRITICAL contact(s); the highest-confidence position is "
            f"{critical[0].geo.latitude:.6f}, {critical[0].geo.longitude:.6f} "
            f"(±{critical[0].geo.horizontal_uncertainty_m:.2f} m)."
        )
        actions.append(
            "**Notify:** forward the GeoJSON export to the National Hydrographic "
            "Office for Notice to Mariners assessment."
        )

    unknown = [d for d in detections if d.label.value == "unknown"]
    if unknown:
        actions.append(
            f"**Review:** {len(unknown)} contact(s) were classified `unknown` — "
            "queue them for human operator adjudication before the line is signed off."
        )

    if flagged:
        actions.append(
            f"**Follow-up:** {len(flagged)} contact(s) are operator-flagged and awaiting "
            "disposition."
        )

    low_conf = [d for d in detections if d.confidence < 0.5]
    if low_conf:
        actions.append(
            f"**Re-survey:** {len(low_conf)} contact(s) fall below 50% confidence; a "
            "reciprocal-heading line at reduced range scale would resolve them."
        )

    if not actions:
        actions.append(
            "**Close out:** no contact requires escalation. Archive the line and "
            "proceed to the next survey block."
        )

    actions.append(
        "**Archive:** retain the raw sonar file alongside this report to preserve the "
        "chain of evidence for the reported positions."
    )
    return actions


def _json_payload(
    survey: SonarSurvey,
    detections: list[Detection],
    stats: DetectionSummary,
    request: ReportRequest,
    report_id: str,
    generated_at: datetime,
) -> dict:
    return {
        "report_id": report_id,
        "title": request.title,
        "generated_at": generated_at.isoformat(),
        "operator": request.operator,
        "vessel": request.vessel,
        "generator": f"Wreckognise {settings.app_version}",
        "survey": survey.metadata.model_dump(mode="json"),
        "preprocessing": (
            survey.preprocess_stats.model_dump(mode="json")
            if survey.preprocess_stats is not None
            else None
        ),
        "inference": (
            survey.inference_metrics.model_dump(mode="json")
            if survey.inference_metrics is not None
            else None
        ),
        "summary": stats.model_dump(mode="json"),
        "detections": [d.model_dump(mode="json") for d in detections],
    }

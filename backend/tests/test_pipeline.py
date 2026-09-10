"""End-to-end smoke test for the Wreckognise pipeline.

Run from the `backend/` directory:

    python -m tests.test_pipeline

Exercises ingestion -> preprocessing -> detection -> georeferencing -> reporting
without needing a network, a GPU, or a real sonar capture on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models.schemas import BoundingBox, ReportRequest  # noqa: E402
from app.services.detector import run_inference, summarise  # noqa: E402
from app.services.georeference import solve_pixel  # noqa: E402
from app.services.preprocessing import preprocess, render_annotated, render_waterfall  # noqa: E402
from app.services.reporting import generate_report, to_geojson  # noqa: E402
from app.services.sonar_reader import read_sonar_file  # noqa: E402
from app.utils.geodesy import destination_point, haversine_m, ground_range  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("\n=== 1. Geodesy ===")
    # A 100 m hop due east must come back as 100 m.
    lat, lon = destination_point(8.926, 78.156, 90.0, 100.0)
    dist = haversine_m(8.926, 78.156, lat, lon)
    check("destination_point round-trips to 100 m", abs(dist - 100.0) < 0.5, f"{dist:.4f} m")
    check("bearing 90 moves east only", abs(lat - 8.926) < 1e-6 and lon > 78.156)
    check("slant-range correction", abs(ground_range(50.0, 30.0) - 40.0) < 1e-6, "3-4-5 triangle")
    check("range below altitude clamps to 0", ground_range(10.0, 30.0) == 0.0)

    print("\n=== 2. Ingestion ===")
    survey = read_sonar_file(Path("demo-line-07.xtf"), "SVY-TEST01")
    meta = survey.metadata
    check("waterfall decoded", survey.waterfall.ndim == 2, f"shape={survey.waterfall.shape}")
    check("waterfall is 8-bit", survey.waterfall.dtype.name == "uint8")
    check("telemetry matches ping count", len(survey.telemetry) == meta.ping_count, f"{meta.ping_count} pings")
    check("line length is plausible", 50 < meta.line_length_m < 5000, f"{meta.line_length_m:.1f} m")
    check("two channels described", len(meta.channels) == 2)
    check("bounds ordered", meta.bounds.north >= meta.bounds.south)
    check("targets planted", len(survey.targets) >= 4, f"{len(survey.targets)} targets")

    print("\n=== 3. Preprocessing ===")
    filtered, detect_input, stats = preprocess(survey.waterfall, method="nlm")
    survey.filtered = filtered
    survey.detect_input = detect_input
    survey.preprocess_stats = stats
    check("output shape preserved", filtered.shape == survey.waterfall.shape)
    check("SNR improved", stats.snr_gain_db > 0, f"{stats.snr_gain_db:+.2f} dB")
    check("speckle reduced", stats.speckle_index_after < stats.speckle_index_before,
          f"{stats.speckle_index_before:.4f} -> {stats.speckle_index_after:.4f}")
    check("timing recorded", stats.elapsed_ms > 0, f"{stats.elapsed_ms:.1f} ms")

    _, _, bilateral_stats = preprocess(survey.waterfall, method="bilateral")
    check("bilateral path runs", bilateral_stats.elapsed_ms > 0,
          f"{bilateral_stats.elapsed_ms:.1f} ms vs NLM {stats.elapsed_ms:.1f} ms")

    print("\n=== 4. Detection ===")
    detections, metrics = run_inference(survey)
    survey.detections = detections
    survey.inference_metrics = metrics
    check("contacts detected", len(detections) > 0, f"{len(detections)} contacts")
    check("confidences in range", all(0 <= d.confidence <= 1 for d in detections))
    check("sorted by confidence",
          all(a.confidence >= b.confidence for a, b in zip(detections, detections[1:])))
    check("all above threshold",
          all(d.confidence >= metrics.confidence_threshold for d in detections))
    check("NMS removed overlaps", metrics.raw_candidates >= metrics.kept_after_nms,
          f"{metrics.raw_candidates} -> {metrics.kept_after_nms}")
    check("latency recorded", metrics.total_ms > 0, f"{metrics.total_ms:.1f} ms @ {metrics.fps:.1f} FPS")

    print("\n=== 5. Georeferencing ===")
    check("every contact has coordinates",
          all(-90 <= d.geo.latitude <= 90 and -180 <= d.geo.longitude <= 180 for d in detections))
    check("all contacts inside survey bounds", all(
        meta.bounds.south - 0.02 <= d.geo.latitude <= meta.bounds.north + 0.02
        and meta.bounds.west - 0.02 <= d.geo.longitude <= meta.bounds.east + 0.02
        for d in detections
    ))
    check("sub-metre to few-metre accuracy",
          all(0 < d.geo.horizontal_uncertainty_m < 10 for d in detections),
          f"max {max((d.geo.horizontal_uncertainty_m for d in detections), default=0):.2f} m")
    check("ground range never exceeds slant range",
          all(d.geo.ground_range_m <= d.geo.slant_range_m + 1e-6 for d in detections))

    # Port and starboard pixels must resolve to opposite sides of the track.
    nadir = survey.nadir_col
    port = solve_pixel(survey, nadir - 300, 400)
    stbd = solve_pixel(survey, nadir + 300, 400)
    check("port/starboard bearings are 180 apart",
          abs(((port.bearing_deg - stbd.bearing_deg) % 360) - 180) < 1e-6,
          f"{port.bearing_deg:.1f} vs {stbd.bearing_deg:.1f}")
    check("port is negative across-track", port.across_track_m < 0 < stbd.across_track_m)
    check("nadir pixel solves at zero range", solve_pixel(survey, nadir, 400).ground_range_m == 0.0)
    check("bbox solve matches centroid solve",
          solve_pixel(survey, 300.0, 400.0).latitude
          == solve_pixel(survey, BoundingBox(x=290, y=390, width=20, height=20).cx, 400.0).latitude)

    print("\n=== 6. Rendering ===")
    raw_png = settings.processed_dir / "TEST_raw.png"
    filt_png = settings.processed_dir / "TEST_filtered.png"
    ann_png = settings.processed_dir / "TEST_annotated.png"
    render_waterfall(survey.waterfall, raw_png)
    render_waterfall(filtered, filt_png)
    render_annotated(filtered, detections, ann_png)
    check("raw PNG written", raw_png.exists() and raw_png.stat().st_size > 1000)
    check("filtered PNG written", filt_png.exists() and filt_png.stat().st_size > 1000)
    check("annotated PNG written", ann_png.exists() and ann_png.stat().st_size > 1000)

    print("\n=== 7. Reporting ===")
    summary = summarise(survey, detections)
    check("summary totals agree", summary.total == len(detections))
    check("class counts sum to total", sum(summary.by_class.values()) == summary.total)
    check("severity counts sum to total", sum(summary.by_severity.values()) == summary.total)

    md = generate_report(survey, ReportRequest(survey_id=survey.survey_id, format="markdown"))
    check("markdown report generated", len(md.content) > 800, f"{len(md.content)} chars")
    check("report names every contact",
          all(d.detection_id in md.content for d in detections))
    check("report file persisted", (settings.report_dir / f"{md.report_id}.md").exists())

    js = generate_report(survey, ReportRequest(survey_id=survey.survey_id, format="json"))
    check("json report generated", js.content.strip().startswith("{"))

    geo = to_geojson(survey, detections)
    check("geojson is a FeatureCollection", geo["type"] == "FeatureCollection")
    check("geojson has track + contacts", len(geo["features"]) == len(detections) + 1)
    check("geojson coordinates are lon,lat order",
          all(-180 <= f["geometry"]["coordinates"][0] <= 180
              for f in geo["features"][1:]))

    print("\n=== 8. Determinism ===")
    again = read_sonar_file(Path("demo-line-07.xtf"), "SVY-TEST02")
    check("same filename yields identical swath",
          (again.waterfall == survey.waterfall).all())
    different = read_sonar_file(Path("other-line-11.xtf"), "SVY-TEST03")
    check("different filename yields a different swath",
          not (different.waterfall == survey.waterfall).all())

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print(f"ALL CHECKS PASSED  |  {len(detections)} contacts georeferenced  |  "
          f"{metrics.total_ms:.0f} ms inference  |  SNR {stats.snr_gain_db:+.2f} dB")
    print("=" * 62 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

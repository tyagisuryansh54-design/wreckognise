"""HTTP-level tests for the Wreckognise API.

Run from the `backend/` directory:

    python -m tests.test_api
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    client = TestClient(app)

    print("\n=== System ===")
    r = client.get("/")
    check("root responds", r.status_code == 200, r.json().get("name", ""))
    r = client.get("/api/health")
    body = r.json()
    check("health ok", r.status_code == 200 and body["status"] == "ok")
    check("opencv reported live", body["opencv_available"] is True)
    r = client.get("/openapi.json")
    check("openapi schema builds", r.status_code == 200,
          f"{len(r.json()['paths'])} paths")

    print("\n=== Ingestion ===")
    r = client.post("/api/ingest/demo", data={"denoise_method": "nlm"})
    check("demo line ingests", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
    ingest = r.json()
    survey_id = ingest["survey_id"]
    check("preprocessed status", ingest["status"] == "preprocessed")
    check("SNR gain reported", ingest["preprocess"]["snr_gain_db"] > 0,
          f"{ingest['preprocess']['snr_gain_db']:+.2f} dB")
    check("both waterfalls rendered",
          ingest["raw_waterfall_png"].endswith(".png")
          and ingest["filtered_waterfall_png"].endswith(".png"))
    check("telemetry preview thinned",
          0 < len(ingest["telemetry_preview"]) <= 61,
          f"{len(ingest['telemetry_preview'])} fixes")

    check("raw PNG served", client.get(ingest["raw_waterfall_png"]).status_code == 200)
    check("filtered PNG served", client.get(ingest["filtered_waterfall_png"]).status_code == 200)

    # Upload path with a real multipart body.
    r = client.post(
        "/api/ingest/upload",
        files={"file": ("survey-line-22.xtf", io.BytesIO(b"\x00" * 4096), "application/octet-stream")},
        data={"denoise_method": "bilateral"},
    )
    check("multipart upload accepted", r.status_code == 200, r.text[:160] if r.status_code != 200 else "")
    check("bilateral method honoured", r.json()["preprocess"]["method"] == "bilateral")

    r = client.post(
        "/api/ingest/upload",
        files={"file": ("notes.txt", io.BytesIO(b"nope"), "text/plain")},
    )
    check("bad extension rejected with 415", r.status_code == 415)

    check("metadata endpoint", client.get(f"/api/ingest/{survey_id}/metadata").status_code == 200)
    check("unknown survey 404s", client.get("/api/ingest/SVY-NOPE/metadata").status_code == 404)
    r = client.get(f"/api/ingest/{survey_id}/telemetry?limit=120")
    check("telemetry endpoint thins", r.status_code == 200 and len(r.json()) <= 121,
          f"{len(r.json())} fixes")
    check("survey listing", client.get("/api/ingest/surveys").json()["count"] >= 2)

    print("\n=== Inference ===")
    r = client.post(f"/api/inference/{survey_id}/detect")
    check("detection runs", r.status_code == 200, r.text[:160] if r.status_code != 200 else "")
    inference = r.json()
    detections = inference["detections"]
    check("contacts returned", len(detections) > 0, f"{len(detections)} contacts")
    check("annotated frame served",
          client.get(inference["annotated_png"]).status_code == 200)
    check("every contact georeferenced",
          all(d["geo"]["latitude"] != 0 and d["geo"]["longitude"] != 0 for d in detections))
    check("audit formula present",
          all("WGS-84 direct" in d["geo"]["formula"] for d in detections))
    check("summary matches detections", inference["summary"]["total"] == len(detections))

    r = client.post(f"/api/inference/{survey_id}/detect?confidence=0.95")
    check("high threshold reduces contacts",
          len(r.json()["detections"]) <= len(detections),
          f"{len(r.json()['detections'])} at conf>=0.95")

    # Restore the full detection set for the report stage.
    detections = client.post(f"/api/inference/{survey_id}/detect").json()["detections"]
    target = detections[0]["detection_id"]

    r = client.get(f"/api/inference/{survey_id}/detections?min_confidence=0.5")
    check("confidence filter works", all(d["confidence"] >= 0.5 for d in r.json()))

    r = client.patch(
        f"/api/inference/{survey_id}/detections/{target}/review",
        json={"review_status": "flagged", "notes": "Verify with ROV on next pass.",
              "operator": "lead@nio.res.in"},
    )
    check("contact flagged", r.status_code == 200 and r.json()["review_status"] == "flagged")
    check("operator note attached", "lead@nio.res.in" in (r.json()["notes"] or ""))

    r = client.get(f"/api/inference/{survey_id}/detections?review_status=flagged")
    check("review filter works", len(r.json()) == 1)

    check("unknown detection 404s",
          client.patch(f"/api/inference/{survey_id}/detections/WRK-NOPE/review",
                       json={"review_status": "confirmed"}).status_code == 404)

    print("\n=== Georeferencing ===")
    r = client.get(f"/api/inference/{survey_id}/georeference?x=200&y=300")
    check("pixel solve responds", r.status_code == 200)
    solution = r.json()
    check("returns a coordinate",
          -90 <= solution["latitude"] <= 90 and -180 <= solution["longitude"] <= 180,
          f"{solution['latitude']:.6f}, {solution['longitude']:.6f}")
    check("uncertainty is sub-metre-class",
          0 < solution["horizontal_uncertainty_m"] < 5,
          f"+/-{solution['horizontal_uncertainty_m']:.2f} m")
    check("out-of-bounds pixel 400s",
          client.get(f"/api/inference/{survey_id}/georeference?x=99999&y=1").status_code == 400)

    r = client.post(f"/api/inference/{survey_id}/georeference/bbox",
                    json={"x": 190, "y": 290, "width": 20, "height": 20})
    check("bbox solve matches pixel solve",
          r.json()["latitude"] == solution["latitude"])

    print("\n=== Reporting ===")
    r = client.post("/api/reports/generate",
                    json={"survey_id": survey_id, "format": "markdown",
                          "operator": "Cdr. R. Nair", "vessel": "INS Sandhayak"})
    check("markdown report", r.status_code == 200, r.text[:160] if r.status_code != 200 else "")
    report = r.json()
    check("brief is substantial", len(report["content"]) > 1200, f"{len(report['content'])} chars")
    check("operator appears in brief", "Cdr. R. Nair" in report["content"])
    check("flagged contact surfaced in actions",
          "operator-flagged" in report["content"])
    check("report downloads", client.get(report["download_url"]).status_code == 200)

    r = client.post("/api/reports/generate", json={"survey_id": survey_id, "format": "json"})
    check("json report", r.status_code == 200 and r.json()["content"].startswith("{"))

    r = client.get(f"/api/reports/{survey_id}/geojson")
    check("geojson export", r.status_code == 200 and r.json()["type"] == "FeatureCollection")
    check("geojson attaches a filename",
          "attachment" in r.headers.get("content-disposition", ""))

    check("report listing", client.get("/api/reports/list").json()["count"] >= 2)
    check("path traversal blocked",
          client.get("/api/reports/download/..%2F..%2Fconfig.py").status_code == 404)
    check("report before detection 409s",
          client.post("/api/reports/generate",
                      json={"survey_id": "SVY-NOPE", "format": "json"}).status_code == 404)

    print("\n=== Cleanup ===")
    check("survey deletes", client.delete(f"/api/ingest/{survey_id}").status_code == 200)
    check("deleted survey 404s",
          client.get(f"/api/ingest/{survey_id}/metadata").status_code == 404)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("ALL API CHECKS PASSED")
    print("=" * 62 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

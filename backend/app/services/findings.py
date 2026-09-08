"""Server-side ledger of every anomaly the system has catalogued.

Appended to automatically whenever a survey is analysed, so the dashboard can
show a running record of findings across every scan rather than only the
survey currently open.

Deliberately append-only and bounded: a survey can be re-run at a different
confidence threshold, and each run is a separate observation worth keeping.
Re-running the same survey supersedes its earlier entries rather than
duplicating them, otherwise sliding the threshold three times would triple the
apparent number of wrecks on the seabed.

Like `store.py`, this is prototype-scale and lives in process memory. Swapping
it for a real table means reimplementing these four methods.
"""

from __future__ import annotations

import threading
import uuid
from collections import Counter
from datetime import datetime, timezone

from ..models.schemas import Detection, FindingRecord, SonarMetadata
from . import catalogue

MAX_FINDINGS = 500


class FindingsLedger:
    def __init__(self) -> None:
        self._findings: list[FindingRecord] = []
        self._lock = threading.RLock()

    def record_survey(
        self, metadata: SonarMetadata, detections: list[Detection]
    ) -> list[FindingRecord]:
        """Replace this survey's entries with the results of the latest run."""
        now = datetime.now(timezone.utc)
        fresh: list[FindingRecord] = []

        for det in detections:
            entry = catalogue.entry_for(det.label)
            fresh.append(
                FindingRecord(
                    finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                    survey_id=det.survey_id,
                    source_file=metadata.filename,
                    detected_at=det.detected_at or now,
                    label=det.label.value,
                    display_name=entry.display_name,
                    category=entry.category,
                    severity=det.severity,
                    confidence=det.confidence,
                    size_plausibility=det.size_plausibility,
                    latitude=det.geo.latitude,
                    longitude=det.geo.longitude,
                    horizontal_uncertainty_m=det.geo.horizontal_uncertainty_m,
                    length_m=det.length_m,
                    width_m=det.width_m,
                    height_estimate_m=det.height_estimate_m,
                    operational_note=entry.operational_note,
                )
            )

        with self._lock:
            self._findings = [f for f in self._findings if f.survey_id != metadata.survey_id]
            self._findings.extend(fresh)
            # Newest first; the dashboard reads the head of this list.
            self._findings.sort(key=lambda f: f.detected_at, reverse=True)
            if len(self._findings) > MAX_FINDINGS:
                del self._findings[MAX_FINDINGS:]
        return fresh

    def all(self, limit: int | None = None, category: str | None = None) -> list[FindingRecord]:
        with self._lock:
            items = list(self._findings)
        if category:
            items = [f for f in items if f.category.lower() == category.lower()]
        return items[:limit] if limit else items

    def summary(self) -> tuple[dict[str, int], dict[str, int]]:
        with self._lock:
            items = list(self._findings)
        return (
            dict(Counter(f.category for f in items)),
            dict(Counter(f.display_name for f in items)),
        )

    def clear(self) -> int:
        with self._lock:
            count = len(self._findings)
            self._findings.clear()
        return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._findings)


ledger = FindingsLedger()

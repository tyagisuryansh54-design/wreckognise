"""In-memory survey registry.

A prototype-scale store deliberately kept behind a small interface: swapping it
for PostGIS or TimescaleDB means reimplementing these five methods and nothing
else. Access is mutex-guarded because FastAPI runs sync handlers in a threadpool.
"""

from __future__ import annotations

import threading

from .sonar_reader import SonarSurvey


class SurveyStore:
    def __init__(self) -> None:
        self._surveys: dict[str, SonarSurvey] = {}
        self._lock = threading.RLock()

    def put(self, survey: SonarSurvey) -> None:
        with self._lock:
            self._surveys[survey.survey_id] = survey

    def get(self, survey_id: str) -> SonarSurvey | None:
        with self._lock:
            return self._surveys.get(survey_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._surveys.keys())

    def all(self) -> list[SonarSurvey]:
        with self._lock:
            return list(self._surveys.values())

    def delete(self, survey_id: str) -> bool:
        with self._lock:
            return self._surveys.pop(survey_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._surveys)


store = SurveyStore()

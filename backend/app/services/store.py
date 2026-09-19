"""In-memory survey registry.

A prototype-scale store deliberately kept behind a small interface: swapping it
for PostGIS or TimescaleDB means reimplementing these five methods and nothing
else. Access is mutex-guarded because FastAPI runs sync handlers in a threadpool.
"""

from __future__ import annotations

import threading

from .sonar_reader import SonarSurvey


class SurveyStore:
    """Survey registry, partitioned by owner.

    Ownership is enforced HERE rather than in each route, because the safe
    behaviour has to be the default one. A route that forgets to pass an owner
    gets the anonymous partition, not everybody's data.

    `owner=None` means unowned, which is what every survey is when
    authentication is switched off -- the single-operator deployment this
    started as. Those stay mutually visible; that is the same behaviour the
    service had before accounts existed. Once a survey has an owner, only that
    owner can reach it.

    A mismatch is reported to callers as absent rather than forbidden. "You may
    not see this" confirms the id exists, and survey ids are the only thing an
    outsider would need to guess.
    """

    def __init__(self) -> None:
        self._surveys: dict[str, SonarSurvey] = {}
        self._owners: dict[str, str | None] = {}
        self._report_owners: dict[str, str | None] = {}
        self._lock = threading.RLock()

    def put(self, survey: SonarSurvey, owner: str | None = None) -> None:
        with self._lock:
            self._surveys[survey.survey_id] = survey
            self._owners[survey.survey_id] = owner

    def get(self, survey_id: str, owner: str | None = None) -> SonarSurvey | None:
        with self._lock:
            survey = self._surveys.get(survey_id)
            if survey is None or not self._may_access(survey_id, owner):
                return None
            return survey

    def record_report(self, filename: str, owner: str | None) -> None:
        """Remember who a generated report belongs to.

        Recorded explicitly rather than inferred from the filename. Reports are
        named `RPT-<uuid>`, carrying no survey id at all -- an earlier version
        of the download guard tried to parse one out and denied every report to
        everybody, including its author.
        """
        with self._lock:
            self._report_owners[filename] = owner

    def may_access_report(self, filename: str, owner: str | None) -> bool:
        with self._lock:
            if filename not in self._report_owners:
                # Generated before ownership was tracked, or by a deployment
                # with auth off. Unowned, like the surveys of that era.
                return True
            stored = self._report_owners[filename]
            return stored is None or stored == owner

    def owner_of(self, survey_id: str) -> str | None:
        with self._lock:
            return self._owners.get(survey_id)

    def may_access(self, survey_id: str, owner: str | None) -> bool:
        with self._lock:
            return survey_id in self._surveys and self._may_access(survey_id, owner)

    def list_ids(self, owner: str | None = None) -> list[str]:
        with self._lock:
            return [i for i in self._surveys if self._may_access(i, owner)]

    def all(self, owner: str | None = None) -> list[SonarSurvey]:
        with self._lock:
            return [s for i, s in self._surveys.items() if self._may_access(i, owner)]

    def delete(self, survey_id: str, owner: str | None = None) -> bool:
        with self._lock:
            if survey_id not in self._surveys or not self._may_access(survey_id, owner):
                return False
            del self._surveys[survey_id]
            self._owners.pop(survey_id, None)
            return True

    def _may_access(self, survey_id: str, owner: str | None) -> bool:
        """Caller holds the lock."""
        stored = self._owners.get(survey_id)
        if stored is None:
            return True          # unowned: the pre-accounts behaviour
        return stored == owner

    def __len__(self) -> int:
        with self._lock:
            return len(self._surveys)


store = SurveyStore()

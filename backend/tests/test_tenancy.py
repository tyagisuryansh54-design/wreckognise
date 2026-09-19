"""Data isolation between accounts.

Run from the `backend/` directory:

    python -m tests.test_tenancy

The question this answers is the one a customer actually asks: if two companies
both use this, can either see the other's survey? Every route that reaches a
stored survey is exercised from a second account, and the artefact URLs are
checked separately, because those are served outside the session entirely.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["WRECKOGNISE_AUTH_USERNAME"] = "alice"
os.environ["WRECKOGNISE_AUTH_PASSWORD"] = "alice-long-passphrase"
os.environ["WRECKOGNISE_REQUIRE_AUTH"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import auth  # noqa: E402

FAILURES: list[str] = []

BOB_PASSWORD = "bob-long-passphrase"


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def sign_in(username: str, password: str, n: int) -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-Forwarded-For": f"198.18.0.{n}"},
    )
    assert r.status_code == 200, f"{username} could not sign in: {r.text[:200]}"
    return client


def main() -> int:
    print("=" * 62)
    print("  Wreckognise tenancy tests")
    print("=" * 62)

    # A second account, created directly: there is no self-registration route,
    # which is itself the intended posture for now.
    auth.users.add("bob", BOB_PASSWORD, display_name="bob")

    with TestClient(app):
        alice = sign_in("alice", "alice-long-passphrase", 1)
        bob = sign_in("bob", BOB_PASSWORD, 2)

        created = alice.post("/api/ingest/demo")
        check("alice ingests a survey", created.status_code == 200, created.text[:120])
        body = created.json()
        survey_id = body["survey_id"]
        artefact = body["filtered_waterfall_png"]

        print("\n-- alice reaches her own survey --")
        check("metadata", alice.get(f"/api/ingest/{survey_id}/metadata").status_code == 200)
        check("telemetry", alice.get(f"/api/ingest/{survey_id}/telemetry").status_code == 200)
        check("detect", alice.post(f"/api/inference/{survey_id}/detect").status_code == 200)
        check("geojson", alice.get(f"/api/reports/{survey_id}/geojson").status_code == 200)
        check(
            "listing shows it",
            any(s["survey_id"] == survey_id for s in alice.get("/api/ingest/surveys").json()["surveys"]),
        )

        print("\n-- bob reaches none of it --")
        for label, response in (
            ("metadata", bob.get(f"/api/ingest/{survey_id}/metadata")),
            ("telemetry", bob.get(f"/api/ingest/{survey_id}/telemetry")),
            ("detect", bob.post(f"/api/inference/{survey_id}/detect")),
            ("geojson", bob.get(f"/api/reports/{survey_id}/geojson")),
            (
                "report generate",
                bob.post("/api/reports/generate", json={"survey_id": survey_id, "format": "json"}),
            ),
            ("delete", bob.delete(f"/api/ingest/{survey_id}")),
        ):
            check(
                f"{label} -> 404 (not 403, which would confirm it exists)",
                response.status_code == 404,
                f"got {response.status_code}",
            )

        listing = bob.get("/api/ingest/surveys").json()
        check("bob's listing is empty", listing["count"] == 0, str(listing["count"]))
        check(
            "count matches the visible list",
            listing["count"] == len(listing["surveys"]),
            f"count={listing['count']} len={len(listing['surveys'])}",
        )

        print("\n-- artefacts --")
        check("alice's signed URL works", alice.get(artefact).status_code == 200)
        check(
            "an unsigned artefact URL is refused",
            alice.get(artefact.split("?")[0]).status_code == 404,
        )
        check(
            "the old open mounts are gone",
            bob.get("/static/uploads/anything.xtf").status_code == 404
            and bob.get("/static/reports/anything.md").status_code == 404,
        )

        print("\n-- alice keeps control of her own data --")
        check("she can delete it", alice.delete(f"/api/ingest/{survey_id}").status_code == 200)
        check(
            "and it is gone afterwards",
            alice.get(f"/api/ingest/{survey_id}/metadata").status_code == 404,
        )

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("  all tenancy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

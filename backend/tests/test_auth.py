"""Authentication tests: credentials, sessions, enumeration, throttling.

Run from the `backend/` directory:

    python -m tests.test_auth

Auth is configured by environment variable and settings are read once at
import, so this module sets them before importing the app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

USERNAME = "operator"
PASSWORD = "a-long-enough-passphrase"
os.environ["WRECKOGNISE_AUTH_USERNAME"] = USERNAME
os.environ["WRECKOGNISE_AUTH_PASSWORD"] = PASSWORD
os.environ["WRECKOGNISE_REQUIRE_AUTH"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def ip(n: int) -> dict[str, str]:
    return {"X-Forwarded-For": f"203.0.113.{n}"}


def test_password_hashing() -> None:
    print("\n-- password storage --")
    h = auth.hash_password(PASSWORD)
    check("scrypt scheme", h.startswith("scrypt$"), h.split("$")[0])
    check("plaintext absent from the hash", PASSWORD not in h)
    check("verifies", auth.verify_password(PASSWORD, h))
    check("rejects a wrong password", not auth.verify_password("nope", h))
    check("salted: two hashes of one password differ", auth.hash_password(PASSWORD) != h)
    check(
        "malformed hash is rejected, not raised",
        auth.verify_password(PASSWORD, "garbage") is False,
    )


def test_login_and_session(client: TestClient) -> None:
    print("\n-- login and session lifecycle --")
    r = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers=ip(1),
    )
    check("valid credentials succeed", r.status_code == 200, f"got {r.status_code}")

    cookie = r.headers.get("set-cookie", "")
    check("cookie is HttpOnly", "HttpOnly" in cookie, cookie)
    # lax here, none in production: strict never crossed the Vercel->Render
    # site boundary, so login 200'd and nothing after it was authenticated.
    check("cookie is SameSite=lax outside production", "samesite=lax" in cookie.lower(), cookie)
    check("cookie is Path=/", "Path=/" in cookie)
    check("password absent from the response", PASSWORD not in r.text)

    check(
        "/me returns the signed-in user",
        client.get("/api/auth/me").json()["username"] == USERNAME,
    )
    check("protected route reachable", client.get("/api/catalogue").status_code == 200)

    client.post("/api/auth/logout", headers=ip(1))
    check("session dies on logout", client.get("/api/auth/me").status_code == 401)
    check("protected route closed again", client.get("/api/catalogue").status_code == 401)


def test_no_enumeration(client: TestClient) -> None:
    print("\n-- user enumeration --")
    unknown = client.post(
        "/api/auth/login", json={"username": "nobody", "password": "x"}, headers=ip(2)
    )
    wrong = client.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrong"}, headers=ip(3)
    )
    check("unknown user -> 401", unknown.status_code == 401, f"got {unknown.status_code}")
    check("wrong password -> 401", wrong.status_code == 401, f"got {wrong.status_code}")
    check(
        "identical message for both",
        unknown.json()["detail"] == wrong.json()["detail"],
        f"{unknown.json()['detail']!r} vs {wrong.json()['detail']!r}",
    )


def test_gate(client: TestClient) -> None:
    print("\n-- the gate --")
    check("health stays public", client.get("/api/health", headers=ip(4)).status_code == 200)
    check(
        "status stays public",
        client.get("/api/auth/status", headers=ip(4)).status_code == 200,
    )
    check("catalogue is protected", client.get("/api/catalogue", headers=ip(4)).status_code == 401)
    check("ingest is protected", client.post("/api/ingest/demo", headers=ip(4)).status_code == 401)


def test_password_change_revokes(client: TestClient) -> None:
    print("\n-- password change ends other sessions --")
    other = TestClient(app)
    other.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, headers=ip(5)
    )
    check("second session established", other.get("/api/auth/me").status_code == 200)

    client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, headers=ip(6)
    )
    new_password = "another-long-passphrase"
    r = client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": new_password},
        headers=ip(6),
    )
    check("password changed", r.status_code == 200, r.text[:120])
    check("the other session was revoked", other.get("/api/auth/me").status_code == 401)
    check("the caller stays signed in", client.get("/api/auth/me").status_code == 200)

    # Restore, so ordering between tests cannot matter.
    client.post(
        "/api/auth/password",
        json={"current_password": new_password, "new_password": PASSWORD},
        headers=ip(6),
    )
    client.post("/api/auth/logout", headers=ip(6))


def test_csrf_origin_check(client: TestClient) -> None:
    print("\n-- CSRF origin check --")
    client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, headers=ip(8)
    )
    body = {"current_password": "x", "new_password": "y"}
    evil = client.post(
        "/api/auth/password", json=body, headers={"Origin": "https://evil.example", **ip(8)}
    )
    check("unsafe request from a foreign origin -> 403", evil.status_code == 403, str(evil.status_code))
    ours = client.post(
        "/api/auth/password",
        json=body,
        headers={"Origin": settings.cors_origin_list[0], **ip(8)},
    )
    check("same request from our origin is not refused as CSRF", ours.status_code != 403, str(ours.status_code))
    none = client.post("/api/auth/password", json=body, headers=ip(8))
    check("no Origin (non-browser client) is not refused as CSRF", none.status_code != 403, str(none.status_code))
    client.post("/api/auth/logout", headers=ip(8))


def test_login_throttled(client: TestClient) -> None:
    print("\n-- login throttling --")
    headers = ip(7)
    statuses = [
        client.post(
            "/api/auth/login",
            json={"username": USERNAME, "password": "wrong"},
            headers=headers,
        ).status_code
        for _ in range(settings.rate_limit_auth + 2)
    ]
    check("attempts eventually return 429", 429 in statuses, f"statuses {statuses}")
    # The AUTH tier, not the heavy one. Login guards credential guessing and
    # keeps a deliberately tight budget; ingest and inference are expensive but
    # legitimate to repeat, and sharing one number throttled an operator's
    # rebuild as if it were a password attempt.
    check(
        "throttle engages only at the configured limit",
        statuses[: settings.rate_limit_auth].count(429) == 0,
        f"first {settings.rate_limit_auth}: {statuses[: settings.rate_limit_auth]}",
    )


def main() -> int:
    print("=" * 62)
    print("  Wreckognise auth tests")
    print("=" * 62)
    check("auth is enabled for this run", settings.auth_enabled)
    check("gate is on for this run", settings.require_auth)

    test_password_hashing()
    with TestClient(app) as client:
        test_login_and_session(client)
        test_no_enumeration(client)
        test_gate(client)
        test_password_change_revokes(client)
        test_csrf_origin_check(client)
        test_login_throttled(client)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("  all auth checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

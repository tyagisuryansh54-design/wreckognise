"""Security-hardening tests.

Run from the `backend/` directory:

    python -m tests.test_security

Note on the login tests the brief asked for: there are none, because there is
no login. This service has no authentication, no users and no session state --
see the module docstring in app/middleware.py. Asserting that "valid logins
still succeed" would require first inventing an auth system, and a test that
passes against code written to make it pass proves nothing. What IS asserted
here is that the real abuse surface is covered: headers, payload ceilings, the
throttle, and that ordinary traffic still works.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def unique_ip(n: int) -> dict[str, str]:
    """Each test gets its own client address so budgets do not bleed across."""
    return {"X-Forwarded-For": f"198.51.100.{n}"}


def test_headers_present(client: TestClient) -> None:
    print("\n-- security headers --")
    r = client.get("/api/health", headers=unique_ip(10))
    h = r.headers
    check("request succeeds", r.status_code == 200, f"got {r.status_code}")
    check("X-Content-Type-Options", h.get("x-content-type-options") == "nosniff")
    check("X-Frame-Options", h.get("x-frame-options") == "DENY")
    check(
        "Referrer-Policy",
        h.get("referrer-policy") == "strict-origin-when-cross-origin",
    )
    check("Cross-Origin-Opener-Policy", h.get("cross-origin-opener-policy") == "same-origin")


def test_production_only_headers(client: TestClient) -> None:
    print("\n-- HSTS and CSP are production-gated --")
    r = client.get("/api/health", headers=unique_ip(11))
    check("no HSTS in development", "strict-transport-security" not in r.headers)

    original = settings.environment
    try:
        settings.environment = "production"
        r = client.get("/api/health", headers=unique_ip(12))
        hsts = r.headers.get("strict-transport-security", "")
        csp = r.headers.get("content-security-policy", "")
        check("HSTS in production", "max-age=63072000" in hsts, hsts)
        check("HSTS includeSubDomains", "includeSubDomains" in hsts)
        check("HSTS preload", "preload" in hsts)
        check("CSP present", "default-src 'self'" in csp)
        check("CSP denies framing", "frame-ancestors 'none'" in csp)
        check("CSP blocks plugins", "object-src 'none'" in csp)
        check("CSP allows Esri basemap", "server.arcgisonline.com" in csp)
        check("CSP allows Google Fonts", "fonts.gstatic.com" in csp)
    finally:
        settings.environment = original


def test_body_size_limit(client: TestClient) -> None:
    print("\n-- JSON payload ceiling --")
    oversized = {"survey_id": "X" * (settings.max_json_body_bytes + 2048)}
    r = client.post("/api/reports/generate", json=oversized, headers=unique_ip(13))
    check("oversized JSON rejected with 413", r.status_code == 413, f"got {r.status_code}")
    check(
        "413 still carries security headers",
        r.headers.get("x-content-type-options") == "nosniff",
    )

    r = client.post(
        "/api/reports/generate",
        json={"survey_id": "SVY-DOES-NOT-EXIST", "format": "json"},
        headers=unique_ip(14),
    )
    check(
        "normal-sized JSON passes the ceiling",
        r.status_code != 413,
        f"got {r.status_code}",
    )


def test_upload_route_exempt(client: TestClient) -> None:
    print("\n-- upload route bypasses the JSON ceiling --")
    blob = io.BytesIO(b"\x00" * (settings.max_json_body_bytes + 4096))
    r = client.post(
        "/api/ingest/upload",
        files={"file": ("probe.bin", blob, "application/octet-stream")},
        headers=unique_ip(15),
    )
    # 415 = it reached the handler and was judged on its extension, which is
    # the point: the body ceiling did not intercept a multipart upload.
    check(
        "large multipart is not blocked by the JSON ceiling",
        r.status_code == 415,
        f"got {r.status_code}",
    )


def test_rate_limit(client: TestClient) -> None:
    print("\n-- throttle --")
    limit = settings.rate_limit_heavy
    headers = unique_ip(16)

    statuses = []
    for _ in range(limit + 3):
        r = client.post(
            "/api/ingest/upload",
            files={"file": ("probe.txt", io.BytesIO(b"x"), "text/plain")},
            headers=headers,
        )
        statuses.append(r.status_code)

    first = statuses[:limit]
    after = statuses[limit:]
    check(
        f"first {limit} heavy requests are not throttled",
        429 not in first,
        f"statuses {first}",
    )
    check("subsequent requests return 429", all(s == 429 for s in after), f"statuses {after}")

    r = client.post(
        "/api/ingest/upload",
        files={"file": ("probe.txt", io.BytesIO(b"x"), "text/plain")},
        headers=headers,
    )
    check("429 carries Retry-After", "retry-after" in r.headers, str(dict(r.headers)))
    check(
        "429 carries security headers",
        r.headers.get("x-frame-options") == "DENY",
    )

    other = client.get("/api/health", headers=unique_ip(17))
    check(
        "a different client is unaffected",
        other.status_code == 200,
        f"got {other.status_code}",
    )


def test_cors_not_credentialed(client: TestClient) -> None:
    print("\n-- CORS --")
    origin = settings.cors_origin_list[0]
    r = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            **unique_ip(18),
        },
    )
    check("preflight allowed for a known origin", r.status_code in (200, 204), f"got {r.status_code}")
    # This assertion used to require the OPPOSITE, and that is how a broken
    # policy shipped: the browser client sends credentials:'include' on every
    # request, so a response without this header is rejected before any handler
    # runs -- for every route, not only authenticated ones.
    check(
        "credentials are advertised on preflight",
        r.headers.get("access-control-allow-credentials") == "true",
        r.headers.get("access-control-allow-credentials", "<absent>"),
    )

    simple = client.get("/api/health", headers={"Origin": origin, **unique_ip(20)})
    check(
        "credentials are advertised on a simple request",
        simple.headers.get("access-control-allow-credentials") == "true",
        simple.headers.get("access-control-allow-credentials", "<absent>"),
    )

    r = client.get("/api/health", headers={"Origin": "https://evil.example", **unique_ip(19)})
    check(
        "unknown origin gets no allow-origin header",
        r.headers.get("access-control-allow-origin") != "https://evil.example",
        r.headers.get("access-control-allow-origin", "<absent>"),
    )


def test_docs_gated(client: TestClient) -> None:
    print("\n-- interactive docs --")
    check("docs served in development", client.get("/docs").status_code == 200)
    check(
        "production disables docs by default",
        settings.expose_docs_in_production is False,
        "expose_docs_in_production must default to False",
    )


def main() -> int:
    print("=" * 62)
    print("  Wreckognise security tests")
    print("=" * 62)

    with TestClient(app) as client:
        test_headers_present(client)
        test_production_only_headers(client)
        test_body_size_limit(client)
        test_upload_route_exempt(client)
        test_rate_limit(client)
        test_cors_not_credentialed(client)
        test_docs_gated(client)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("  all security checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Security middleware: headers, payload ceilings, and abuse throttling.

Two threat models sit side by side here.

The first is resource exhaustion, and it applies whether or not anyone is
signed in: one upload costs 8-40 s of CPU and several hundred MB of RSS on a
512 MB instance, so a handful of concurrent requests is a denial of service
with no cleverness at all.

The second arrived with authentication (app/services/auth.py). Sessions are
cookie-borne, so the throttle now also stands in front of /api/auth/ -- an
unthrottled login endpoint is an offline password cracker with a network
interface.

AuthGate is deliberately separate from both. It answers "may this caller be
here", which is a different question from "is this request abusive", and
keeping them apart means the throttle still protects the login route itself,
which by definition cannot require a session.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import settings

logger = logging.getLogger("wreckognise.security")

# Paths that stream large binaries by design and must not be judged against the
# JSON body ceiling. The upload route enforces its own limit as it writes.
UPLOAD_PATHS = ("/api/ingest/upload",)

# Endpoints that cost real CPU: decode, denoise, inference, Eigen-CAM. These get
# the strict bucket. Matched as prefixes, with a suffix check for the detect and
# attention routes, which carry a survey id mid-path.
# The auth routes are here for a different reason from the rest: not CPU cost,
# but because an unthrottled login endpoint is an offline password cracker with
# a network interface. scrypt makes each guess expensive for the attacker AND
# for this instance, so the throttle protects both.
#
# Listed individually rather than by prefix. Covering all of /api/auth/ swept in
# /status, which every page load calls before it can decide whether to render a
# login screen -- twelve page views per five minutes per address, shared by
# everyone behind one office NAT. It fails safe (a probe that cannot answer
# never gates the app) but it is still wrong, and it was found by rate-limiting
# a health check from this machine.
EXPENSIVE_PREFIXES = ("/api/ingest/",)
EXPENSIVE_PATHS = ("/api/auth/login", "/api/auth/password")
EXPENSIVE_SUFFIXES = ("/detect", "/attention")


def client_ip(request: Request) -> str:
    """Best-effort client address.

    Render terminates TLS at a proxy, so the socket peer is always the proxy and
    X-Forwarded-For is the only source of the real address. That header is
    trivially spoofable by the client. This is stated rather than hidden: for an
    unauthenticated public service the throttle is a courtesy against accidental
    hammering and casual abuse, not a security boundary, and nothing here should
    be read as one. A determined attacker rotates the header and wins.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # The LAST entry, not the first. A proxy appends the address it saw to
        # whatever the client sent, so the first entry is client-controlled
        # and the last is the proxy's own observation. Keying on the first let
        # anyone rotate the login throttle away with a header.
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the standard hardening headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # The API serves rendered waterfalls to a different origin (the Vercel
        # frontend), so cross-origin *reads* of /static must stay possible.
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        if request.url.path.startswith("/static/processed/"):
            # Vary: Origin on EVERY artefact response, not only the ones that
            # carried an Origin (which is all CORSMiddleware does). The dashboard
            # shows a waterfall in a plain <img> first -- no Origin, so no ACAO
            # in the reply -- and the browser caches that reply. The relief view
            # then requests the same URL in CORS mode to read its pixels, the
            # cache answers with the ACAO-less copy, and the browser fails the
            # load as a CORS error on a file the server would gladly have
            # served. Keying the cache on Origin sends that request to the
            # server instead. Done here, outermost, so it can dedupe against
            # the copy CORSMiddleware may already have appended.
            vary = response.headers.get("vary", "")
            if "origin" not in vary.lower():
                response.headers["Vary"] = f"{vary}, Origin" if vary else "Origin"

        if settings.is_production:
            # Only meaningful over TLS, and only honest to send when the
            # deployment actually terminates TLS. Browsers ignore it on http://
            # anyway, but claiming it in development invites a local
            # misconfiguration that is painful to undo in the browser.
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
            response.headers["Content-Security-Policy"] = settings.csp_header

        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized non-upload payloads before a parser ever sees them.

    Every JSON route here takes a survey id and a handful of flags; nothing
    legitimate approaches a megabyte. Declared Content-Length is checked first
    because it costs nothing, then the received body is measured, since
    Content-Length is client-supplied and chunked requests omit it entirely.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(UPLOAD_PATHS):
            return await call_next(request)

        limit = settings.max_json_body_bytes
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            return self._too_large(request, int(declared), limit)

        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > limit:
                return self._too_large(request, len(body), limit)

        return await call_next(request)

    @staticmethod
    def _too_large(request: Request, size: int, limit: int) -> JSONResponse:
        logger.warning(
            "payload rejected | ip=%s path=%s bytes=%d limit=%d",
            client_ip(request),
            request.url.path,
            size,
            limit,
        )
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds the {limit // 1024} KB limit."},
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window throttle, per client address, with two tiers.

    A plain deque of timestamps per key rather than a token bucket: the windows
    are short, the traffic is small, and a deque makes the Retry-After exact
    instead of estimated. Idle keys are swept on write so a long-running
    instance cannot accumulate one entry per address seen.

    In-process state, which means it is per-worker and resets on deploy. That is
    the correct trade here -- the alternative is Redis, and adding a datastore to
    a single-instance demo to throttle a public endpoint is the kind of
    over-engineering that never gets maintained.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()
        self._last_sweep = time.monotonic()

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
            return await call_next(request)

        tier, limit, window = self._tier_for(request.url.path)
        if tier != "auth" and not settings.rate_limit_enabled:
            return await call_next(request)
        key = (client_ip(request), tier)

        allowed, retry_after = self._check(key, limit, window)
        if not allowed:
            logger.warning(
                "rate limit | ip=%s path=%s tier=%s limit=%d/%ds retry_after=%ds",
                key[0],
                request.url.path,
                tier,
                limit,
                window,
                retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Too many requests. This endpoint allows {limit} per "
                        f"{window} seconds; retry in {retry_after} s."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    @staticmethod
    def _tier_for(path: str) -> tuple[str, int, int]:
        if path in EXPENSIVE_PATHS:
            # Credential routes: the tight budget is the point.
            return "auth", settings.rate_limit_auth, settings.rate_limit_auth_window_s
        if path.startswith(EXPENSIVE_PREFIXES) or path.endswith(EXPENSIVE_SUFFIXES):
            return "heavy", settings.rate_limit_heavy, settings.rate_limit_heavy_window_s
        return "light", settings.rate_limit_light, settings.rate_limit_light_window_s

    def _check(self, key: tuple[str, str], limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            cutoff = now - window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, int(hits[0] + window - now) + 1)
            hits.append(now)
            return True, 0

    def _sweep(self, now: float) -> None:
        """Drop keys with no hits inside the longest window. Caller holds the lock."""
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        horizon = now - max(
            settings.rate_limit_heavy_window_s,
            settings.rate_limit_auth_window_s,
            settings.rate_limit_light_window_s,
        )
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= horizon]:
            del self._hits[key]


def _origin_allowed(origin: str) -> bool:
    """Same allow-list CORS uses: explicit origins, plus the optional regex."""
    if origin in settings.cors_origin_list:
        return True
    pattern = settings.cors_origin_regex
    return bool(pattern and re.fullmatch(pattern, origin))


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Require a live session for the API, once `require_auth` is on.

    A middleware rather than a dependency on each router, so a route added
    later is protected by default instead of protected only if someone
    remembers. Forgetting to opt in should not be the thing that exposes an
    endpoint.

    The exemption list is short and each entry earns its place: the login route
    cannot require a session to obtain one; /status is what the dashboard asks
    before it knows whether to render a login screen; health is the platform's
    probe and must answer while signed out; OPTIONS is a preflight that carries
    no cookie by design.
    """

    PUBLIC_PATHS = frozenset(
        {
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/status",
            "/api/health",
            "/",
        }
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not settings.require_auth
            or not settings.auth_enabled
            or request.method == "OPTIONS"
            or path in self.PUBLIC_PATHS
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        # Cross-site request forgery. The session cookie has to be SameSite=None
        # to cross the dashboard->API site boundary at all, so the cookie alone
        # no longer says where a request came from. Browsers attach Origin to
        # every cross-site unsafe request and it cannot be set by page script,
        # so an Origin that is present and not ours is a forgery. Absent means
        # a non-browser client (curl, the test suite), which CSRF cannot reach.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and not _origin_allowed(origin):
                logger.warning(
                    "csrf refused | ip=%s path=%s origin=%s",
                    client_ip(request), path, origin[:80],
                )
                return JSONResponse(status_code=403, content={"detail": "Origin not allowed."})

        # Imported here, not at module scope: auth imports config, config is
        # imported by this module, and a top-level import would close the loop.
        from .services import auth as auth_service

        session = auth_service.sessions.get(
            request.cookies.get(settings.session_cookie_name)
        )
        if session is None:
            logger.warning(
                "unauthenticated | ip=%s path=%s", client_ip(request), path
            )
            return JSONResponse(
                status_code=401, content={"detail": "Authentication required."}
            )
        return await call_next(request)

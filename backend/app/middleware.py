"""Security middleware: headers, payload ceilings, and abuse throttling.

Scope note, because it drives every decision in this file: Wreckognise has no
authentication. There are no users, no cookies, no sessions, no password store
and no database -- the survey registry is an in-memory dict. Every endpoint is
public by design; it is a demonstration dashboard, not a tenanted service.

So the threat model is not credential stuffing. It is resource exhaustion: a
single upload costs 8-40 s of CPU and several hundred MB of RSS on a 512 MB
instance, which means a handful of concurrent requests is a denial of service
without any cleverness at all. These middlewares defend the instance, and add
the browser-side headers that cost nothing and close off whole bug classes.

Ordering matters. Starlette runs middleware in reverse registration order, so
the throttle must be added LAST to run FIRST -- there is no point parsing or
size-checking a request that is about to be rejected anyway.
"""

from __future__ import annotations

import logging
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
EXPENSIVE_PREFIXES = ("/api/ingest/",)
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
        return forwarded.split(",")[0].strip()
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
            settings.rate_limit_heavy_window_s, settings.rate_limit_light_window_s
        )
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= horizon]:
            del self._hits[key]

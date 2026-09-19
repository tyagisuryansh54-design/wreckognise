"""Short-lived signed URLs for survey artefacts.

Why these exist rather than a cookie check.

The dashboard is served from one origin and the API from another, and the
session cookie is SameSite=strict. A browser does not attach a strict cookie to
a cross-origin subresource request, so an <img src> pointing at the API arrives
with no cookie at all -- authenticating those PNGs by session would blank every
waterfall on the page while looking, from the server's side, like a correct
rejection. Relaxing the cookie to SameSite=none to fix an image tag would trade
a working image for CSRF exposure on every other route.

So the artefact URL carries its own proof: an HMAC over the filename and an
expiry, verified without any session state. This is what S3 presigned URLs do,
for the same reason.

What a signature is and is not. It proves the server issued this URL to someone
who was authorised at the time, and that it has not expired or been edited. It
does not re-check ownership at fetch time, so anyone the URL is forwarded to can
read that one file until it expires. Artefacts are therefore signed for minutes,
not days.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from hashlib import sha256

from ..config import settings

logger = logging.getLogger("wreckognise.security")

_runtime_secret: str | None = None


def secret() -> str:
    """The signing key, configured or generated.

    A generated key lives only as long as the process, so existing URLs stop
    verifying after a restart. That matches the artefacts themselves, which sit
    on an ephemeral disk and do not survive a deploy either -- a signature
    outliving its file would be the odd outcome, not this one.
    """
    global _runtime_secret
    if settings.secret_key:
        return settings.secret_key
    if _runtime_secret is None:
        _runtime_secret = secrets.token_urlsafe(48)
        logger.warning(
            "signing | no WRECKOGNISE_SECRET_KEY set -- generated an ephemeral key; "
            "artefact links will stop working after a restart"
        )
    return _runtime_secret


def sign(name: str, ttl_seconds: int | None = None) -> str:
    """Return `name?exp=<unix>&sig=<hex>`, ready to append to the artefact route."""
    ttl = ttl_seconds if ttl_seconds is not None else settings.artefact_url_ttl_seconds
    expires = int(time.time()) + ttl
    return f"{name}?exp={expires}&sig={_digest(name, expires)}"


def verify(name: str, exp: str | None, sig: str | None) -> bool:
    """Constant-time signature check. False on anything missing or malformed."""
    if not exp or not sig:
        return False
    try:
        expires = int(exp)
    except (TypeError, ValueError):
        return False
    if expires < time.time():
        return False
    return hmac.compare_digest(_digest(name, expires), sig)


def _digest(name: str, expires: int) -> str:
    return hmac.new(
        secret().encode("utf-8"), f"{name}:{expires}".encode("utf-8"), sha256
    ).hexdigest()

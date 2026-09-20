"""Authentication endpoints: login, logout, current user, password change."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import settings
from ..middleware import client_ip
from ..models.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    SessionResponse,
    UserResponse,
)
from ..services import auth

logger = logging.getLogger("wreckognise.security")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for every failure mode. "No such user" and "wrong password" are
# the same sentence and the same status code, because telling them apart turns
# the endpoint into a directory of who holds an account.
INVALID = "Invalid credentials."


# The dashboard (Vercel) and the API (Render) are different SITES, and a
# browser never attaches a SameSite=strict cookie to a cross-site request --
# nor stores one set by a cross-site response. "strict" meant login answered
# 200 and nothing after it was ever authenticated. None is the only value that
# crosses the boundary; it requires Secure, which production sets, and it is
# why AuthGate checks Origin on unsafe methods. Lax locally, where the Vite
# proxy keeps everything same-site.
_SAMESITE = "none" if settings.is_production else "lax"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,            # unreadable from JavaScript, so XSS cannot lift it
        secure=settings.is_production,   # refuse to travel over plaintext
        samesite=_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite=_SAMESITE,
    )


def current_user(request: Request) -> auth.User:
    """Dependency for protected routes. 401 when there is no live session."""
    session = auth.sessions.get(request.cookies.get(settings.session_cookie_name))
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = auth.users.get(session.username)
    if user is None:
        # The account was removed while a session was still open.
        auth.sessions.revoke(session.token)
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def owner_key(request: Request) -> str | None:
    """Partition key for stored data.

    None when authentication is switched off, which puts every survey in the
    shared anonymous partition -- exactly how the service behaved before
    accounts existed. With auth on, it is the signed-in username, and the store
    refuses anything belonging to anyone else.
    """
    if not settings.auth_enabled:
        return None
    session = auth.sessions.get(request.cookies.get(settings.session_cookie_name))
    return session.username if session else None


def optional_user(request: Request) -> auth.User | None:
    session = auth.sessions.get(request.cookies.get(settings.session_cookie_name))
    return auth.users.get(session.username) if session else None


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
    """Exchange a username and password for a session cookie."""
    client = client_ip(request)
    user = auth.authenticate(payload.username, payload.password)

    if user is None:
        # Logged with the username truncated and the password absent. Enough to
        # spot a pattern across attempts; not enough to become a credential
        # leak if the logs are ever exposed.
        shown = payload.username.strip().lower()[:3]
        logger.warning(
            "login failed | ip=%s user=%s*** reason=invalid-credentials", client, shown
        )
        raise HTTPException(status_code=401, detail=INVALID)

    session = auth.sessions.create(user.username, settings.session_ttl_seconds)
    _set_session_cookie(response, session.token)
    logger.info("login ok | ip=%s user=%s", client, user.username)
    return SessionResponse(
        user=UserResponse(
            username=user.username, display_name=user.display_name, role=user.role
        ),
        expires_in=settings.session_ttl_seconds,
    )


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    """End this session server-side and clear the cookie."""
    token = request.cookies.get(settings.session_cookie_name)
    revoked = auth.sessions.revoke(token)
    _clear_session_cookie(response)
    return {"ok": True, "revoked": revoked}


@router.get("/me", response_model=UserResponse)
async def me(user: auth.User = Depends(current_user)) -> UserResponse:
    """Who the caller is. The dashboard uses this to restore state on reload."""
    return UserResponse(
        username=user.username, display_name=user.display_name, role=user.role
    )


@router.post("/password")
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    user: auth.User = Depends(current_user),
) -> dict:
    """Change the caller's password and end every other session they hold."""
    if not auth.verify_password(payload.current_password, user.password_hash):
        logger.warning("password change denied | user=%s reason=bad-current", user.username)
        raise HTTPException(status_code=401, detail=INVALID)
    if len(payload.new_password) < settings.min_password_length:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {settings.min_password_length} characters.",
        )

    auth.users.set_password(user.username, payload.new_password)

    # Every existing session dies, including this one, then a fresh session is
    # issued to the caller. A password change that leaves a stolen session alive
    # somewhere else has not actually changed anything.
    ended = auth.sessions.revoke_all_for(user.username)
    session = auth.sessions.create(user.username, settings.session_ttl_seconds)
    _set_session_cookie(response, session.token)
    logger.info("password changed | user=%s sessions_ended=%d", user.username, ended)
    return {"ok": True, "sessions_ended": ended}


@router.get("/status")
async def status(user: auth.User | None = Depends(optional_user)) -> dict:
    """Unauthenticated probe: is auth on, and is this caller signed in?

    The dashboard needs this before it can decide whether to show a login
    screen at all -- without it, a deployment with authentication disabled
    would still gate itself behind one.
    """
    return {
        "auth_enabled": settings.auth_enabled,
        "auth_required": settings.require_auth,
        "authenticated": user is not None,
        "username": user.username if user else None,
    }

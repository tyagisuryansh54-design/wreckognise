"""Credential verification and server-side session state.

Two deliberate choices, both about the 512 MB instance this runs on.

**scrypt, not bcrypt.** `hashlib.scrypt` is in the standard library, so there is
no new dependency to install, audit or keep patched. It is memory-hard, which
is the property that matters against GPU cracking, and the cost parameters are
stored alongside each hash so they can be raised later without invalidating
existing passwords.

**Sessions are server-side and opaque.** The cookie carries a random token and
nothing else -- no user id, no claims, no signature to verify. That makes logout
mean something: deleting the row ends the session immediately, everywhere.
A self-contained JWT cannot be revoked before it expires without keeping a
denylist, at which point it is a session table with extra steps.

Both the user store and the session store live behind small interfaces, because
they are in memory today and belong in Postgres tomorrow. Sessions therefore do
not survive a restart, which means a deploy logs everyone out. That is stated
here rather than discovered: it is acceptable for a small team and unacceptable
for customers, and it is fixed by the same migration that gives surveys
persistence.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("wreckognise.security")

# scrypt cost. n=2^14 with r=8 puts one hash at roughly 16 MB and ~50 ms here --
# enough to make offline cracking expensive without letting a burst of logins
# exhaust a small instance.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return `scrypt$n$r$p$salt$hash`, all parameters recoverable from the string."""
    salt = salt or os.urandom(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check against a stored hash. False on anything malformed."""
    try:
        scheme, n, r, p, salt_hex, want_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(want_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), want_hex)


# A hash of a value nobody can supply. Verifying against this when the account
# does not exist keeps the work -- and therefore the response time -- the same
# whether or not the username is real, so the endpoint cannot be used to
# enumerate accounts by timing it.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


@dataclass
class User:
    username: str
    password_hash: str
    display_name: str = ""
    role: str = "operator"


@dataclass
class Session:
    token: str
    username: str
    created_at: float
    expires_at: float
    last_seen: float = field(default_factory=time.time)


class UserStore:
    """In-memory user registry. Swap for a table; the four methods are the contract."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._lock = threading.RLock()

    def add(self, username: str, password: str, display_name: str = "", role: str = "operator") -> User:
        user = User(
            username=username.strip().lower(),
            password_hash=hash_password(password),
            display_name=display_name or username,
            role=role,
        )
        with self._lock:
            self._users[user.username] = user
        return user

    def get(self, username: str) -> User | None:
        with self._lock:
            return self._users.get(username.strip().lower())

    def set_password(self, username: str, password: str) -> bool:
        with self._lock:
            user = self._users.get(username.strip().lower())
            if user is None:
                return False
            user.password_hash = hash_password(password)
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._users)


class SessionStore:
    """Opaque server-side sessions, revocable individually or per user."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self, username: str, ttl_seconds: int) -> Session:
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(32),
            username=username,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._sweep(now)
            self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        now = time.time()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                del self._sessions[token]
                return None
            session.last_seen = now
            return session

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def revoke_all_for(self, username: str) -> int:
        """End every session a user holds.

        Called on password change, and the reason the session store exists at
        all: changing a password while a stolen session stays valid elsewhere
        is the failure this prevents.
        """
        username = username.strip().lower()
        with self._lock:
            doomed = [t for t, s in self._sessions.items() if s.username == username]
            for token in doomed:
                del self._sessions[token]
        return len(doomed)

    def _sweep(self, now: float) -> None:
        """Drop expired rows. Caller holds the lock."""
        for token in [t for t, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[token]

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


users = UserStore()
sessions = SessionStore()


def authenticate(username: str, password: str) -> User | None:
    """Verify a credential pair.

    Always performs a full hash comparison, even for an unknown username, so an
    attacker cannot tell a missing account from a wrong password by measuring
    how long the answer took.
    """
    user = users.get(username)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def bootstrap(username: str, password: str) -> bool:
    """Seed the first account from configuration, once.

    Returns False when no credentials are configured, which is the signal to
    leave authentication switched off entirely rather than start with an
    account whose password is a default someone might never change.
    """
    if not username or not password:
        return False
    if users.get(username) is not None:
        return True
    users.add(username, password, display_name=username, role="admin")
    logger.info("auth | bootstrapped account '%s'", username)
    return True

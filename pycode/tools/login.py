"""Client-cookie login helpers backed by a small SQLite user database."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path


DEFAULT_USER_ID = "manufacturer"
ADMIN_USER_ID = "admin"
AUTH_COOKIE_NAME = "divian_hub_login"
MAX_PASSWORD_LENGTH = 15
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


@dataclass(frozen=True)
class AuthUser:
    """Represent an authenticated application user."""

    user_id: str
    display_name: str
    is_admin: bool = False


DEFAULT_USER = AuthUser(DEFAULT_USER_ID, "default/manufacturer", False)


def password_hash(password: str) -> str:
    """Return the SHA256 hex digest for a password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_login_database(path: Path) -> None:
    """Create and seed the login database if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                password_hash TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO users (user_id, display_name, password_hash, is_admin)
            VALUES (?, ?, NULL, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                password_hash = NULL,
                is_admin = 0
            """,
            (DEFAULT_USER_ID, "default/manufacturer"),
        )
        conn.execute(
            """
            INSERT INTO users (user_id, display_name, password_hash, is_admin)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                password_hash = excluded.password_hash,
                is_admin = 1
            """,
            (ADMIN_USER_ID, "admin", password_hash("4lb4TRO5S2")),
        )
        existing_secret = conn.execute("SELECT value FROM settings WHERE key = ?", ("cookie_secret",)).fetchone()
        if existing_secret is None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("cookie_secret", secrets.token_hex(32)),
            )
        conn.commit()


def authenticate_password(path: Path, password: str) -> AuthUser | None:
    """Return the matching password user, or None when no hash matches."""
    if len(password) > MAX_PASSWORD_LENGTH:
        return None

    candidate_hash = password_hash(password)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT user_id, display_name, password_hash, is_admin
            FROM users
            WHERE password_hash IS NOT NULL
            """
        ).fetchall()

    for row in rows:
        saved_hash = str(row["password_hash"] or "")
        if hmac.compare_digest(candidate_hash, saved_hash):
            return AuthUser(str(row["user_id"]), str(row["display_name"]), bool(row["is_admin"]))
    return None


def user_from_cookie(path: Path, cookie_header: str | None) -> AuthUser:
    """Read and verify the client-side login cookie."""
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header or "")
    except Exception:
        return DEFAULT_USER

    morsel = cookie.get(AUTH_COOKIE_NAME)
    if morsel is None:
        return DEFAULT_USER

    payload_part, separator, signature = morsel.value.partition(".")
    if not separator or not payload_part or not signature:
        return DEFAULT_USER

    expected_signature = _sign_payload(path, payload_part)
    if not hmac.compare_digest(signature, expected_signature):
        return DEFAULT_USER

    try:
        payload_bytes = base64.urlsafe_b64decode(_pad_base64(payload_part))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return DEFAULT_USER

    if int(payload.get("expires_at", 0) or 0) < int(time.time()):
        return DEFAULT_USER

    user_id = str(payload.get("user_id", "")).strip()
    if not user_id:
        return DEFAULT_USER

    with _connect(path) as conn:
        row = conn.execute(
            "SELECT user_id, display_name, is_admin FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        return DEFAULT_USER
    return AuthUser(str(row["user_id"]), str(row["display_name"]), bool(row["is_admin"]))


def make_login_cookie(path: Path, user: AuthUser) -> str:
    """Build a signed HttpOnly cookie for the user login state."""
    payload = {"user_id": user.user_id, "expires_at": int(time.time()) + COOKIE_MAX_AGE_SECONDS}
    payload_part = _base64_json(payload)
    signature = _sign_payload(path, payload_part)
    return (
        f"{AUTH_COOKIE_NAME}={payload_part}.{signature}; "
        f"Max-Age={COOKIE_MAX_AGE_SECONDS}; Path=/; HttpOnly; SameSite=Lax"
    )


def make_logout_cookie() -> str:
    """Build a cookie header that clears the login state."""
    return f"{AUTH_COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _cookie_secret(path: Path) -> bytes:
    ensure_login_database(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", ("cookie_secret",)).fetchone()
    if row is None:
        raise RuntimeError("login cookie secret is missing")
    return str(row["value"]).encode("utf-8")


def _sign_payload(path: Path, payload_part: str) -> str:
    digest = hmac.new(_cookie_secret(path), payload_part.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _base64_json(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pad_base64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")

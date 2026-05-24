from __future__ import annotations

import hmac
import secrets
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import redirect, request, session, url_for
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .config import GOOGLE_ALLOWED_EMAILS, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class AuthError(RuntimeError):
    pass


def google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def current_user() -> dict | None:
    user = session.get("user")
    return user if isinstance(user, dict) else None


def is_logged_in() -> bool:
    return current_user() is not None


def ensure_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_logged_in():
            return view(*args, **kwargs)
        return redirect(url_for("login_page", next=request.full_path or "/"))

    return wrapped


def build_google_auth_url(next_path: str = "/") -> str:
    if not google_oauth_configured():
        raise AuthError("Google OAuth is not configured")

    oauth_state = secrets.token_urlsafe(32)
    session["oauth_state"] = oauth_state
    session["post_login_next"] = safe_next_path(next_path)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": url_for("google_auth_callback", _external=True),
        "response_type": "code",
        "scope": "openid email profile",
        "state": oauth_state,
        "prompt": "select_account",
        "access_type": "offline",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def complete_google_login(code: str, state: str) -> dict:
    expected_state = session.pop("oauth_state", None)
    if not expected_state or not hmac.compare_digest(str(expected_state), str(state or "")):
        raise AuthError("Invalid OAuth state")

    token_response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": url_for("google_auth_callback", _external=True),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if not token_response.ok:
        raise AuthError("Google token exchange failed")

    id_token_value = token_response.json().get("id_token")
    if not id_token_value:
        raise AuthError("Google did not return an ID token")

    claims = id_token.verify_oauth2_token(
        id_token_value,
        google_requests.Request(),
        GOOGLE_CLIENT_ID,
    )

    issuer = claims.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise AuthError("Invalid Google token issuer")
    if not claims.get("email_verified"):
        raise AuthError("Google email is not verified")

    email = str(claims.get("email") or "").lower()
    if not email or email not in GOOGLE_ALLOWED_EMAILS:
        raise AuthError("This Google account is not allowed")

    user = {
        "email": email,
        "name": claims.get("name") or email,
        "picture": claims.get("picture") or "",
    }
    session.permanent = True
    session["user"] = user
    ensure_csrf_token()
    return user


def safe_next_path(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value

"""Signed, httpOnly session cookies carrying only the user ID."""

import uuid

from fastapi import Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings

SESSION_COOKIE = "hb_session"
OAUTH_STATE_COOKIE = "hb_oauth_state"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="hb-session")


def _max_age() -> int:
    return get_settings().session_max_age_days * 86400


def read_session(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        return uuid.UUID(_serializer().loads(token, max_age=_max_age()))
    except (BadSignature, ValueError):
        return None


def set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=not get_settings().is_dev,
        samesite="lax",
        path="/",
    )


def start_session(response: Response, user_id: uuid.UUID) -> None:
    set_cookie(response, SESSION_COOKIE, _serializer().dumps(str(user_id)), _max_age())


def end_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import Session
from app.core.config import get_settings
from app.core.sessions import OAUTH_STATE_COOKIE, end_session, set_cookie, start_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"


@router.get("/github/login")
async def github_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GitHub login is not configured")
    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": "read:user",
            "state": state,
        }
    )
    response = RedirectResponse(f"{GITHUB_AUTHORIZE}?{query}")
    set_cookie(response, OAUTH_STATE_COOKIE, state, max_age=600)
    return response


@router.get("/github/callback")
async def github_callback(request: Request, session: Session, code: str, state: str):
    settings = get_settings()
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Login expired; try again")

    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            GITHUB_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "GitHub login failed")
        user_res = await client.get(
            GITHUB_USER,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        user_res.raise_for_status()
        profile = user_res.json()

    user = await _upsert_user(session, profile["id"], profile["login"], profile.get("avatar_url"))
    response = RedirectResponse(f"{settings.frontend_origin}/today")
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    start_session(response, user.id)
    return response


@router.post("/dev-login", status_code=status.HTTP_204_NO_CONTENT)
async def dev_login(session: Session, response: Response) -> None:
    """Local development only: sign in as a fixed dev user without GitHub."""
    if not get_settings().is_dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user = await _upsert_user(session, github_id=0, login="dev", avatar_url=None)
    start_session(response, user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    end_session(response)


async def _upsert_user(session, github_id: int, login: str, avatar_url: str | None) -> User:
    user = await session.scalar(select(User).where(User.github_id == github_id))
    if user is None:
        user = User(github_id=github_id, github_login=login, avatar_url=avatar_url)
        session.add(user)
    else:
        user.github_login, user.avatar_url = login, avatar_url
    await session.commit()
    return user

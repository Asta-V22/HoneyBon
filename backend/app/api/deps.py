from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sessions import SESSION_COOKIE, read_session
from app.db.session import get_session
from app.models import User

Session = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_queue(request: Request) -> ArqRedis:
    return request.app.state.queue


RedisDep = Annotated[Redis, Depends(get_redis)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


async def current_user(request: Request, session: Session) -> User:
    user_id = read_session(request.cookies.get(SESSION_COOKIE))
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def enforce_rate_limit(redis: Redis, key: str, limit: int, window_s: int) -> None:
    """Fixed-window counter per user and action."""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_s)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests; slow down.")

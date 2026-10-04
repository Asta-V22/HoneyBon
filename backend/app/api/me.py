from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, Session
from app.api.schemas import MeOut, MeUpdate, ProviderKeyIn, ProviderKeyOut, SubmissionOut
from app.core.crypto import encrypt_secret
from app.core.sessions import end_session
from app.models import ProviderCredential, Submission, User
from app.providers import PROVIDER_MODELS, PROVIDERS

router = APIRouter(prefix="/me", tags=["account"])


async def _me(session: Session, user: User) -> MeOut:
    creds = (
        await session.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.user_id == user.id)
            .order_by(ProviderCredential.provider)
        )
    ).all()
    return MeOut(
        id=user.id,
        github_login=user.github_login,
        avatar_url=user.avatar_url,
        default_provider=user.default_provider,
        default_model=user.default_model,
        capture_mode=user.capture_mode,
        providers=[ProviderKeyOut.model_validate(c) for c in creds],
        available_providers=sorted(PROVIDERS),
        provider_models=PROVIDER_MODELS,
    )


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown provider: {provider}")


@router.get("", response_model=MeOut)
async def get_me(user: CurrentUser, session: Session) -> MeOut:
    return await _me(session, user)


@router.patch("", response_model=MeOut)
async def update_me(body: MeUpdate, user: CurrentUser, session: Session) -> MeOut:
    fields = body.model_dump(exclude_unset=True)
    if fields.get("default_provider"):
        _check_provider(fields["default_provider"])
    for key, value in fields.items():
        setattr(user, key, value)
    await session.commit()
    return await _me(session, user)


@router.put("/providers/{provider}", response_model=MeOut)
async def save_provider_key(
    provider: str, body: ProviderKeyIn, user: CurrentUser, session: Session
) -> MeOut:
    _check_provider(provider)
    key = body.api_key.strip()
    cred = await session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.user_id == user.id, ProviderCredential.provider == provider
        )
    )
    if cred is None:
        cred = ProviderCredential(user_id=user.id, provider=provider)
        session.add(cred)
    cred.encrypted_key = encrypt_secret(key)
    cred.last_four = key[-4:]
    cred.base_url = body.base_url or None
    if user.default_provider is None:
        user.default_provider = provider
    await session.commit()
    return await _me(session, user)


@router.delete("/providers/{provider}", response_model=MeOut)
async def delete_provider_key(provider: str, user: CurrentUser, session: Session) -> MeOut:
    await session.execute(
        delete(ProviderCredential).where(
            ProviderCredential.user_id == user.id, ProviderCredential.provider == provider
        )
    )
    if user.default_provider == provider:
        user.default_provider = None
        user.default_model = None
    await session.commit()
    return await _me(session, user)


@router.get("/export")
async def export_data(user: CurrentUser, session: Session) -> dict[str, Any]:
    submissions = (
        await session.scalars(
            select(Submission)
            .where(Submission.user_id == user.id)
            .options(selectinload(Submission.problem), selectinload(Submission.reviews))
            .order_by(Submission.created_at)
        )
    ).all()
    return {
        "user": {"github_login": user.github_login, "capture_mode": user.capture_mode},
        "submissions": [
            {
                **SubmissionOut.model_validate(s).model_dump(mode="json", exclude={"review"}),
                "reviews": [
                    {"provider": r.provider, "model": r.model, "review": r.review_json}
                    for r in s.reviews
                ],
            }
            for s in submissions
        ],
    }


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: CurrentUser, session: Session, response: Response) -> None:
    await session.delete(user)
    await session.commit()
    end_session(response)

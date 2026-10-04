import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    CaptureMode,
    ChatMessageStatus,
    ChatRole,
    ImportAnalysisMode,
    ImportStatus,
    SubmissionSource,
    SubmissionStatus,
)


def _enum(cls: type[StrEnum]) -> Enum:
    # Stored as varchar + CHECK so adding a value never needs ALTER TYPE.
    return Enum(
        cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        name=cls.__name__.lower(),
    )


class _UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(_UUIDPk, _Timestamps, Base):
    __tablename__ = "users"

    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    github_login: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    default_provider: Mapped[str | None] = mapped_column(String(32))
    default_model: Mapped[str | None] = mapped_column(String(100))
    capture_mode: Mapped[CaptureMode] = mapped_column(
        _enum(CaptureMode), default=CaptureMode.ANALYZE
    )


class ProviderCredential(_UUIDPk, _Timestamps, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
    last_four: Mapped[str] = mapped_column(String(4))
    base_url: Mapped[str | None] = mapped_column(String(500))  # OpenAI-compatible providers


class ExtensionToken(_UUIDPk, _Timestamps, Base):
    __tablename__ = "extension_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Problem(_UUIDPk, _Timestamps, Base):
    """Shared metadata only; problem statements are never stored."""

    __tablename__ = "problems"
    __table_args__ = (UniqueConstraint("platform", "slug"),)

    platform: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    difficulty: Mapped[str | None] = mapped_column(String(16))
    topic_tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    url: Mapped[str | None] = mapped_column(String(500))
    frontend_id: Mapped[str | None] = mapped_column(String(16))  # visible problem number


class Submission(_UUIDPk, _Timestamps, Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"), index=True)
    code: Mapped[str] = mapped_column(Text)
    # User-pasted statement for non-LeetCode problems; LeetCode statements are never stored.
    statement: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(32))
    source: Mapped[SubmissionSource] = mapped_column(_enum(SubmissionSource))
    status: Mapped[SubmissionStatus] = mapped_column(
        _enum(SubmissionStatus), default=SubmissionStatus.QUEUED
    )
    # Platform submission ID; guarantees the same submission is never captured twice.
    external_id: Mapped[str | None] = mapped_column(String(64))
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    problem: Mapped[Problem] = relationship()
    reviews: Mapped[list["Review"]] = relationship(back_populates="submission")


class Review(_UUIDPk, _Timestamps, Base):
    __tablename__ = "reviews"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    served_model: Mapped[str | None] = mapped_column(String(100))  # differs after a fallback
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    # Denormalized from review_json for analytics queries.
    used_technique: Mapped[str | None] = mapped_column(String(32), index=True)
    optimal_techniques: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    time_class: Mapped[str | None] = mapped_column(String(16))
    space_class: Mapped[str | None] = mapped_column(String(16))
    optimal_time_class: Mapped[str | None] = mapped_column(String(16))
    optimal_space_class: Mapped[str | None] = mapped_column(String(16))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    repair_attempted: Mapped[bool] = mapped_column(default=False)

    submission: Mapped[Submission] = relationship(back_populates="reviews")


class ChatThread(_UUIDPk, _Timestamps, Base):
    __tablename__ = "chat_threads"
    __table_args__ = (UniqueConstraint("user_id", "problem_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    summarized_through: Mapped[int] = mapped_column(Integer, default=0)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="thread", order_by="ChatMessage.seq"
    )


class ChatMessage(_UUIDPk, _Timestamps, Base):
    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    # Insertion order; a user turn and its reply share a transaction, so created_at ties.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), index=True)
    role: Mapped[ChatRole] = mapped_column(_enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[ChatMessageStatus] = mapped_column(
        _enum(ChatMessageStatus), default=ChatMessageStatus.DONE
    )
    error: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(100))
    quoted_selection: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")


class ImportJob(_UUIDPk, _Timestamps, Base):
    __tablename__ = "import_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    repository: Mapped[str] = mapped_column(String(300))
    status: Mapped[ImportStatus] = mapped_column(_enum(ImportStatus), default=ImportStatus.PENDING)
    analysis_mode: Mapped[ImportAnalysisMode | None] = mapped_column(_enum(ImportAnalysisMode))
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_folders: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)

"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.tables import (
    ChatMessage,
    ChatThread,
    ExtensionToken,
    ImportJob,
    Problem,
    ProviderCredential,
    Review,
    Submission,
    User,
)

__all__ = [
    "ChatMessage",
    "ChatThread",
    "ExtensionToken",
    "ImportJob",
    "Problem",
    "ProviderCredential",
    "Review",
    "Submission",
    "User",
]

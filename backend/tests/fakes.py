import json
from typing import Any, ClassVar

from app.providers.base import (
    ProviderError,
    StructuredRequest,
    StructuredResult,
    Usage,
)


class ScriptedAdapter:
    """Returns queued raw responses in order and records every request."""

    name: ClassVar[str] = "anthropic"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[StructuredRequest] = []

    async def review(self, request: StructuredRequest) -> StructuredResult:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        raw = item if isinstance(item, str) else json.dumps(item)
        return StructuredResult(raw=raw, usage=Usage(100, 50), latency_ms=10, model=request.model)

    async def chat(self, request):  # pragma: no cover - unused in tests
        raise ProviderError("not scripted")
        yield


class ChatAdapter:
    """Streams each scripted reply in small chunks and records chat requests."""

    name: ClassVar[str] = "anthropic"

    def __init__(self, replies: list[Any], summary: str = "SUMMARY") -> None:
        self.replies = list(replies)
        self.summary = summary
        self.requests = []

    async def review(self, request):  # pragma: no cover - unused in chat tests
        raise ProviderError("not scripted")

    async def chat(self, request):
        from app.chat.prompts import SUMMARY_SYSTEM_PROMPT
        from app.providers.base import ChatChunk

        self.requests.append(request)
        reply = self.summary if request.system == SUMMARY_SYSTEM_PROMPT else self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        for i in range(0, len(reply), 5):
            yield ChatChunk(text=reply[i : i + 5])
        yield ChatChunk(usage=Usage(300, len(reply)))

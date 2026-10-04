"""One adapter interface for every LLM provider: a structured review call and a streaming chat call.

Adapters only talk to the provider. Prompt building, validation and the repair retry live in the
review pipeline, so every provider is held to the same contract.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Protocol


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class StructuredRequest:
    model: str
    system: str
    messages: list[dict[str, str]]
    json_schema: dict[str, Any]
    max_tokens: int = 8192


@dataclass(frozen=True)
class StructuredResult:
    raw: str  # Unvalidated JSON text; the pipeline validates it.
    usage: Usage
    latency_ms: int


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    messages: list[ChatMessage]
    max_tokens: int = 4096


@dataclass(frozen=True)
class ChatChunk:
    text: str = ""
    usage: Usage | None = field(default=None)  # Set on the final chunk only.


class ProviderError(Exception):
    """A provider call failed in a way the user should see (bad key, rate limit, outage)."""


class ProviderAdapter(Protocol):
    name: ClassVar[str]

    def __init__(self, api_key: str, base_url: str | None = None) -> None: ...

    async def review(self, request: StructuredRequest) -> StructuredResult: ...

    def chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...

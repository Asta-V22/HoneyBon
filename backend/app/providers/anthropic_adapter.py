import time
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import anthropic

from app.providers.base import (
    ChatChunk,
    ChatRequest,
    Message,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    Usage,
)

# Models that accept server-side refusal fallbacks in "default" (route-by-category) mode.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AnthropicAdapter:
    name: ClassVar[str] = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
        self._first_party = base_url is None

    def _fallbacks(self, model: str) -> dict[str, Any]:
        if self._first_party and model in _FALLBACK_MODELS:
            return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        return {}

    @staticmethod
    def _messages(messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def review(self, request: StructuredRequest) -> StructuredResult:
        started = time.monotonic()
        try:
            # Streamed so long, code-heavy outputs never hit HTTP timeouts.
            async with self._client.beta.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=self._messages(request.messages),
                output_config={"format": {"type": "json_schema", "schema": request.json_schema}},
                **self._fallbacks(request.model),
            ) as stream:
                message = await stream.get_final_message()
        except Exception as exc:
            raise _translate(exc) from exc

        if message.stop_reason == "refusal":
            raise ProviderError("The model declined to review this submission.")
        text = "".join(block.text for block in message.content if block.type == "text")
        return StructuredResult(
            raw=text,
            usage=Usage(message.usage.input_tokens, message.usage.output_tokens),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=message.model,
        )

    async def chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        try:
            async with self._client.beta.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=self._messages(request.messages),
                **self._fallbacks(request.model),
            ) as stream:
                async for text in stream.text_stream:
                    yield ChatChunk(text=text)
                final = await stream.get_final_message()
        except Exception as exc:
            raise _translate(exc) from exc
        yield ChatChunk(usage=Usage(final.usage.input_tokens, final.usage.output_tokens))


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderError("Anthropic rejected the API key. Check it in Settings.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return ProviderError("This Anthropic key cannot use the selected model.")
    if isinstance(exc, anthropic.NotFoundError):
        return ProviderError("Unknown Anthropic model. Check the model name in Settings.")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError("Anthropic rate limit reached. Try again shortly.", retryable=True)
    if isinstance(exc, anthropic.BadRequestError):
        return ProviderError(f"Anthropic rejected the request: {exc.message}")
    if isinstance(exc, anthropic.APIStatusError):
        return ProviderError(
            f"Anthropic error ({exc.status_code}).", retryable=exc.status_code >= 500
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError("Could not reach Anthropic.", retryable=True)
    return exc

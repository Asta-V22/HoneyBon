import asyncio
import time
from collections.abc import AsyncIterator
from typing import ClassVar

from google import genai
from google.genai import errors, types

from app.providers.base import (
    ChatChunk,
    ChatRequest,
    Message,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    Usage,
)

MAX_RETRIES = 2
RETRY_BACKOFF_S = 2.0


class GeminiAdapter:
    name: ClassVar[str] = "gemini"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        http_options = types.HttpOptions(base_url=base_url) if base_url else None
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    @staticmethod
    def _contents(messages: list[Message]) -> list[types.Content]:
        return [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
        ]

    @staticmethod
    def _usage(meta: types.GenerateContentResponseUsageMetadata | None) -> Usage:
        if meta is None:
            return Usage()
        # Thinking tokens are billed as output.
        output = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
        return Usage(meta.prompt_token_count or 0, output)

    async def review(self, request: StructuredRequest) -> StructuredResult:
        started = time.monotonic()
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            max_output_tokens=request.max_tokens,
            response_mime_type="application/json",
            response_json_schema=request.json_schema,
        )
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=request.model, contents=self._contents(request.messages), config=config
                )
                break
            except Exception as exc:
                error = _translate(exc)
                # Overloads (503) and rate limits (429) are usually brief; retry like the
                # Anthropic SDK does before failing the review.
                if (
                    not (isinstance(error, ProviderError) and error.retryable)
                    or attempt == MAX_RETRIES
                ):
                    raise error from exc
                await asyncio.sleep(RETRY_BACKOFF_S * 2**attempt)
        return StructuredResult(
            raw=response.text or "",
            usage=self._usage(response.usage_metadata),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=request.model,
        )

    async def chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        usage = None
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=request.model,
                contents=self._contents(request.messages),
                config=types.GenerateContentConfig(
                    system_instruction=request.system, max_output_tokens=request.max_tokens
                ),
            )
            async for chunk in stream:
                if chunk.usage_metadata is not None:
                    usage = chunk.usage_metadata
                if chunk.text:
                    yield ChatChunk(text=chunk.text)
        except Exception as exc:
            raise _translate(exc) from exc
        yield ChatChunk(usage=self._usage(usage))


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, errors.ClientError):
        if exc.code in (401, 403):
            return ProviderError("Gemini rejected the API key. Check it in Settings.")
        if exc.code == 404:
            return ProviderError("Unknown Gemini model. Check the model name in Settings.")
        if exc.code == 429:
            return ProviderError("Gemini rate limit reached. Try again shortly.", retryable=True)
        return ProviderError(f"Gemini rejected the request: {exc.message}")
    if isinstance(exc, errors.ServerError):
        if exc.code == 503:
            return ProviderError(
                "Gemini is overloaded right now. Try again shortly.", retryable=True
            )
        return ProviderError(f"Gemini error ({exc.code}).", retryable=True)
    return exc

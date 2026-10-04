import json
import time
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import groq

from app.core.config import get_settings
from app.providers.base import (
    ChatChunk,
    ChatRequest,
    Message,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    Usage,
)

# Models with JSON-schema structured outputs on Groq; the rest only have JSON object mode.
_STRICT_SCHEMA_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"}
_BEST_EFFORT_SCHEMA_MODELS = {"openai/gpt-oss-safeguard-20b"}

_MIN_OUTPUT_TOKENS = 1500
_CHARS_PER_TOKEN = 3  # deliberately conservative estimate


def _reasoning(model: str) -> dict[str, Any]:
    # Keep reasoning out of the message content (it would break the JSON) and cheap, since the
    # free tier charges max tokens against an 8K-per-minute budget.
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low", "include_reasoning": False}
    if model.startswith("qwen/"):
        return {"reasoning_effort": "low", "reasoning_format": "hidden"}
    return {}


class GroqAdapter:
    name: ClassVar[str] = "groq"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        # The SDK retries 429s itself, honouring Groq's retry-after header.
        self._client = groq.AsyncGroq(api_key=api_key, base_url=base_url, max_retries=4)

    @staticmethod
    def _messages(system: str, messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]

    @staticmethod
    def _output_budget(
        system: str,
        messages: list[Message],
        max_tokens: int,
        extra_chars: int = 0,
        min_output: int = _MIN_OUTPUT_TOKENS,
    ) -> int:
        """Groq rejects any request whose prompt plus max tokens exceeds the per-minute limit."""
        prompt_chars = len(system) + sum(len(m.content) for m in messages) + extra_chars
        limit = get_settings().groq_request_token_limit
        budget = min(max_tokens, limit - prompt_chars // _CHARS_PER_TOKEN - 200)
        if budget < min_output:
            raise ProviderError(_TOO_LARGE)
        return budget

    async def review(self, request: StructuredRequest) -> StructuredResult:
        system = request.system
        if request.model in _STRICT_SCHEMA_MODELS or request.model in _BEST_EFFORT_SCHEMA_MODELS:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "review",
                    "strict": request.model in _STRICT_SCHEMA_MODELS,
                    "schema": request.json_schema,
                },
            }
        else:
            response_format = {"type": "json_object"}
            system += (
                "\n\nRespond with a single JSON object matching this JSON Schema:\n"
                + json.dumps(request.json_schema)
            )

        started = time.monotonic()
        try:
            completion = await self._client.chat.completions.create(
                model=request.model,
                messages=self._messages(system, request.messages),
                max_completion_tokens=self._output_budget(
                    system,
                    request.messages,
                    request.max_tokens,
                    extra_chars=len(json.dumps(request.json_schema)),
                ),
                response_format=response_format,
                **_reasoning(request.model),
            )
        except Exception as exc:
            raise _translate(exc) from exc

        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise ProviderError(
                "Groq stopped before finishing: the review needs more output tokens than your "
                "Groq plan allows per request. Try another provider."
            )
        usage = completion.usage
        return StructuredResult(
            raw=choice.message.content or "",
            usage=Usage(usage.prompt_tokens, usage.completion_tokens) if usage else Usage(),
            latency_ms=int((time.monotonic() - started) * 1000),
            model=completion.model or request.model,
        )

    async def chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        usage = Usage()
        try:
            stream = await self._client.chat.completions.create(
                model=request.model,
                messages=self._messages(request.system, request.messages),
                max_completion_tokens=self._output_budget(
                    request.system, request.messages, request.max_tokens, min_output=400
                ),
                stream=True,
                **_reasoning(request.model),
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield ChatChunk(text=chunk.choices[0].delta.content)
                x_groq = getattr(chunk, "x_groq", None)
                if x_groq is not None and getattr(x_groq, "usage", None) is not None:
                    usage = Usage(x_groq.usage.prompt_tokens, x_groq.usage.completion_tokens)
        except Exception as exc:
            raise _translate(exc) from exc
        yield ChatChunk(usage=usage)


_TOO_LARGE = (
    "This request is larger than your Groq plan's per-minute token limit allows in one request. "
    "Try another provider, or raise GROQ_REQUEST_TOKEN_LIMIT if you are on a paid Groq plan."
)


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, groq.AuthenticationError):
        return ProviderError("Groq rejected the API key. Check it in Settings.")
    if isinstance(exc, groq.PermissionDeniedError):
        return ProviderError("This Groq key cannot use the selected model.")
    if isinstance(exc, groq.NotFoundError):
        return ProviderError("Unknown Groq model. Check the model name in Settings.")
    if isinstance(exc, groq.RateLimitError):
        return ProviderError("Groq rate limit reached. Try again in a minute.", retryable=True)
    if isinstance(exc, groq.APIStatusError) and exc.status_code == 413:
        return ProviderError(_TOO_LARGE)
    if isinstance(exc, groq.BadRequestError):
        return ProviderError(f"Groq rejected the request: {exc.message}")
    if isinstance(exc, groq.APIStatusError):
        return ProviderError(f"Groq error ({exc.status_code}).", retryable=exc.status_code >= 500)
    if isinstance(exc, groq.APIConnectionError):
        return ProviderError("Could not reach Groq.", retryable=True)
    return exc

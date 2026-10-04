from types import SimpleNamespace

import groq
import httpx
import pytest

from app.providers import groq_adapter
from app.providers.base import Message, ProviderError, StructuredRequest
from app.reviews.provider_schema import provider_schema
from app.reviews.schema import ReviewPartA

SCHEMA = provider_schema(ReviewPartA)


def _request(model: str, prompt: str = "review this", max_tokens: int = 32000):
    return StructuredRequest(model, "system prompt", [Message("user", prompt)], SCHEMA, max_tokens)


def _completion(content="{}", finish_reason="stop"):
    return SimpleNamespace(
        model="served-model",
        choices=[
            SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))
        ],
        usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=900),
    )


def _adapter(monkeypatch, outcome):
    adapter = groq_adapter.GroqAdapter(api_key="test")
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(adapter._client.chat.completions, "create", create)
    return adapter, calls


def _status_error(cls, status: int):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com"))
    return cls("error", response=response, body=None)


async def test_strict_schema_and_hidden_reasoning_for_gpt_oss(monkeypatch):
    adapter, calls = _adapter(monkeypatch, _completion('{"ok": true}'))
    result = await adapter.review(_request("openai/gpt-oss-120b"))
    sent = calls[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"] == SCHEMA
    assert sent["include_reasoning"] is False and sent["reasoning_effort"] == "low"
    assert sent["messages"][0] == {"role": "system", "content": "system prompt"}
    assert result.raw == '{"ok": true}' and result.usage.input_tokens == 1200


async def test_qwen_hides_reasoning_from_content(monkeypatch):
    adapter, calls = _adapter(monkeypatch, _completion())
    await adapter.review(_request("qwen/qwen3.8-27b"))
    assert calls[0]["reasoning_format"] == "hidden" and "include_reasoning" not in calls[0]


async def test_other_models_get_json_mode_with_schema_in_prompt(monkeypatch):
    adapter, calls = _adapter(monkeypatch, _completion())
    await adapter.review(_request("some/new-model"))
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert '"verdict"' in calls[0]["messages"][0]["content"]


async def test_prompt_plus_output_stays_under_the_per_minute_limit(monkeypatch):
    adapter, calls = _adapter(monkeypatch, _completion())
    await adapter.review(_request("openai/gpt-oss-20b", prompt="x" * 6000))
    budget = calls[0]["max_completion_tokens"]
    assert 1500 <= budget < 8000 - 6000 // 3


async def test_oversized_prompt_fails_before_calling_groq(monkeypatch):
    adapter, calls = _adapter(monkeypatch, _completion())
    with pytest.raises(ProviderError, match="per-minute token limit"):
        await adapter.review(_request("openai/gpt-oss-20b", prompt="x" * 30000))
    assert calls == []


async def test_truncated_output_is_reported_clearly(monkeypatch):
    adapter, _ = _adapter(monkeypatch, _completion('{"verdict":', finish_reason="length"))
    with pytest.raises(ProviderError, match="stopped before finishing"):
        await adapter.review(_request("openai/gpt-oss-120b"))


@pytest.mark.parametrize(
    ("error", "message", "retryable"),
    [
        (_status_error(groq.AuthenticationError, 401), "API key", False),
        (_status_error(groq.RateLimitError, 429), "rate limit", True),
        (_status_error(groq.APIStatusError, 413), "per-minute token limit", False),
        (_status_error(groq.NotFoundError, 404), "Unknown Groq model", False),
    ],
)
async def test_errors_are_translated(monkeypatch, error, message, retryable):
    adapter, _ = _adapter(monkeypatch, error)
    with pytest.raises(ProviderError, match=message) as info:
        await adapter.review(_request("openai/gpt-oss-120b"))
    assert info.value.retryable is retryable

import pytest
from google.genai import errors

from app.providers import gemini_adapter
from app.providers.base import Message, ProviderError, StructuredRequest

REQUEST = StructuredRequest("gemini-x", "sys", [Message("user", "hi")], {"type": "object"})


class _Response:
    text = "{}"
    usage_metadata = None


def _adapter(monkeypatch, outcomes):
    monkeypatch.setattr(gemini_adapter, "RETRY_BACKOFF_S", 0)
    adapter = gemini_adapter.GeminiAdapter(api_key="test")
    calls = []

    async def generate_content(**kwargs):
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(adapter._client.aio.models, "generate_content", generate_content)
    return adapter, calls


def _server_error(code: int) -> errors.ServerError:
    return errors.ServerError(code, {"error": {"code": code, "message": "overloaded"}})


async def test_overload_is_retried(monkeypatch):
    adapter, calls = _adapter(monkeypatch, [_server_error(503), _server_error(503), _Response()])
    result = await adapter.review(REQUEST)
    assert result.raw == "{}" and len(calls) == 3


async def test_gives_up_after_retries(monkeypatch):
    adapter, calls = _adapter(monkeypatch, [_server_error(503)] * 3)
    with pytest.raises(ProviderError, match="overloaded"):
        await adapter.review(REQUEST)
    assert len(calls) == 3


async def test_bad_key_is_not_retried(monkeypatch):
    error = errors.ClientError(401, {"error": {"code": 401, "message": "bad key"}})
    adapter, calls = _adapter(monkeypatch, [error])
    with pytest.raises(ProviderError, match="API key"):
        await adapter.review(REQUEST)
    assert len(calls) == 1

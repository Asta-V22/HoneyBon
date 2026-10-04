"""Provider registry. The generic OpenAI-compatible adapter arrives later."""

from app.providers.anthropic_adapter import AnthropicAdapter
from app.providers.base import ProviderAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.groq_adapter import GroqAdapter

PROVIDERS: dict[str, type[ProviderAdapter]] = {
    AnthropicAdapter.name: AnthropicAdapter,
    GeminiAdapter.name: GeminiAdapter,
    GroqAdapter.name: GroqAdapter,
}

# Models offered in the model pickers; the first is the provider's default. Any other model
# name can still be typed in by hand.
PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5", "claude-fable-5-1"],
    "gemini": [
        "gemini-3-flash-preview",  # the only one that completed reviews reliably in testing
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
    ],
    # Free-tier Groq models with strict JSON-schema structured outputs.
    "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
}

DEFAULT_MODELS: dict[str, str] = {name: models[0] for name, models in PROVIDER_MODELS.items()}


def get_adapter(name: str, api_key: str, base_url: str | None = None) -> ProviderAdapter:
    try:
        cls = PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown provider: {name}") from None
    return cls(api_key=api_key, base_url=base_url)

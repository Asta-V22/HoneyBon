"""Provider registry. Phase 1 adds the Anthropic and Gemini adapters; Phase 2 adds Groq."""

from app.providers.base import ProviderAdapter

_REGISTRY: dict[str, type[ProviderAdapter]] = {}


def register(adapter: type[ProviderAdapter]) -> type[ProviderAdapter]:
    _REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(name: str, api_key: str, base_url: str | None = None) -> ProviderAdapter:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown provider: {name}") from None
    return cls(api_key=api_key, base_url=base_url)


def available_providers() -> list[str]:
    return sorted(_REGISTRY)

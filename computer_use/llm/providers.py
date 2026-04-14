"""Provider profiles for provider-specific request extensions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProviderProfile:
    """Provider-specific request translation hooks."""

    name: str
    reasoning_field_name: str = 'reasoning'

    def build_extra_body(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
        provider_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {}

    def build_extra_headers(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
        provider_config: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        return {}


@dataclass(frozen=True)
class ArkProviderProfile(ProviderProfile):
    """Ark-specific OpenAI-compatible request translation."""

    name: str = 'ark'
    reasoning_field_name: str = 'reasoning_content'

    def build_extra_body(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
        provider_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        del provider_config
        extra_body: Dict[str, Any] = {}
        if thinking_mode is not None:
            extra_body['thinking'] = {'type': thinking_mode}
        if reasoning_effort is not None:
            extra_body['reasoning_effort'] = reasoning_effort
        return extra_body


@dataclass(frozen=True)
class OpenRouterProviderProfile(ProviderProfile):
    """OpenRouter request translation."""

    name: str = 'openrouter'

    def build_extra_headers(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
        provider_config: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        del thinking_mode, reasoning_effort
        config = dict(provider_config or {})
        headers: Dict[str, str] = {}
        http_referer = str(config.get('http_referer') or '').strip()
        title = str(config.get('title') or '').strip()
        if http_referer:
            headers['HTTP-Referer'] = http_referer
        if title:
            headers['X-OpenRouter-Title'] = title
        return headers


@dataclass(frozen=True)
class OpenAIProviderProfile(ProviderProfile):
    """OpenAI request translation."""

    name: str = 'openai'


@dataclass(frozen=True)
class OllamaProviderProfile(ProviderProfile):
    """Ollama request translation."""

    name: str = 'ollama'

    def build_extra_body(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
        provider_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        del reasoning_effort, provider_config
        if thinking_mode in ('enabled', 'disabled'):
            return {'thinking': {'type': thinking_mode}}
        return {}


_PROVIDER_PROFILES: Dict[str, ProviderProfile] = {
    'ark': ArkProviderProfile(),
    'openrouter': OpenRouterProviderProfile(),
    'openai': OpenAIProviderProfile(),
    'ollama': OllamaProviderProfile(),
}


def get_provider_profile(provider: str) -> ProviderProfile:
    """Return the registered provider profile."""
    normalized = str(provider or '').strip().lower()
    profile = _PROVIDER_PROFILES.get(normalized)
    if profile is None:
        raise ValueError(f'不支持的 provider: {provider}')
    return profile

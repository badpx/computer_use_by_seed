"""OpenAI SDK based chat completion adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised via factory error path
    OpenAI = None

from .providers import ProviderProfile, get_provider_profile


class OpenAiChatClient:
    """Thin provider-aware wrapper around OpenAI chat completions."""

    def __init__(
        self,
        sdk_client: Any,
        provider: str = 'ark',
        provider_profile: Optional[ProviderProfile] = None,
        provider_config: Optional[Dict[str, Any]] = None,
    ):
        self.sdk_client = sdk_client
        self.provider = provider
        self.provider_profile = provider_profile or get_provider_profile(provider)
        self.provider_config = dict(provider_config or {})
        self.reasoning_field_name = self.provider_profile.reasoning_field_name

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        thinking_mode: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        kwargs: Dict[str, Any] = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
        }
        if tools:
            kwargs['tools'] = tools
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens

        extra_body = self._build_extra_body(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
        )
        if extra_body:
            kwargs['extra_body'] = extra_body

        extra_headers = self._build_extra_headers(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
        )
        if extra_headers:
            kwargs['extra_headers'] = extra_headers

        return self.sdk_client.chat.completions.create(**kwargs)

    def _build_extra_body(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
    ) -> Dict[str, Any]:
        if self.provider_profile is None:
            return {}
        return self.provider_profile.build_extra_body(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
            provider_config=self.provider_config,
        )

    def _build_extra_headers(
        self,
        *,
        thinking_mode: Optional[str],
        reasoning_effort: Optional[str],
    ) -> Dict[str, str]:
        if self.provider_profile is None:
            return {}
        return self.provider_profile.build_extra_headers(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
            provider_config=self.provider_config,
        )

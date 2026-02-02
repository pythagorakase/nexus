"""Cloud LLM backend for OpenAI/Anthropic providers."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Dict, Optional

from .base import LLMBackend, LLMResponse

logger = logging.getLogger("nexus.llm.cloud")


class CloudBackend(LLMBackend):
    """Cloud backend that delegates to OpenAI or Anthropic providers."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key_env: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.provider_name = provider
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self._provider = None

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Return a full completion from the cloud provider."""
        provider = self._resolve_provider(**kwargs)
        response = await asyncio.to_thread(provider.get_completion, prompt)
        return self._translate_response(response)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream completion tokens from the cloud provider.

        Currently returns a single chunk containing the full completion.
        """
        logger.debug("Cloud streaming not supported; returning full completion")
        response = await self.complete(prompt, **kwargs)
        yield response.content

    def is_available(self) -> bool:
        """Return True if the provider can be initialized.

        Requires either:
        - NEXUS_ALLOW_CLOUD=1 environment variable, OR
        - The configured API key env var to be present

        This prevents accidental cloud usage in auto mode.
        """
        # Safety check: require explicit opt-in or API key presence
        allow_cloud = os.environ.get("NEXUS_ALLOW_CLOUD", "").lower() in (
            "1",
            "true",
            "yes",
        )
        api_key_present = bool(self.api_key_env and os.environ.get(self.api_key_env))

        if not (allow_cloud or api_key_present):
            logger.debug(
                "Cloud backend disabled: NEXUS_ALLOW_CLOUD not set and API key not in env"
            )
            return False

        try:
            self._resolve_provider()
            return True
        except Exception as exc:
            logger.debug("Cloud backend unavailable: %s", exc)
            return False

    def _resolve_provider(self, **kwargs: Any) -> Any:
        system_prompt = kwargs.pop("system_prompt", self.system_prompt)
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        model = kwargs.pop("model", self.model)

        if kwargs:
            raise ValueError(f"Unsupported cloud parameters: {sorted(kwargs.keys())}")

        if self._provider and system_prompt == self.system_prompt and model == self.model:
            if temperature == self.temperature and max_tokens == self.max_tokens:
                return self._provider

        provider = self._build_provider(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if (
            system_prompt == self.system_prompt
            and model == self.model
            and temperature == self.temperature
            and max_tokens == self.max_tokens
        ):
            self._provider = provider

        return provider

    def _build_provider(
        self,
        *,
        model: str,
        system_prompt: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> Any:
        api_key = self._resolve_api_key()
        provider = self.provider_name.lower()

        if provider == "openai":
            from scripts.api_openai import OpenAIProvider

            options: Dict[str, Any] = {
                "api_key": api_key,
                "model": model,
                "system_prompt": system_prompt,
            }
            if temperature is not None:
                options["temperature"] = temperature
            if max_tokens is not None:
                options["max_output_tokens"] = max_tokens

            return OpenAIProvider(**options)

        if provider == "anthropic":
            from scripts.api_anthropic import AnthropicProvider

            options = {
                "api_key": api_key,
                "model": model,
                "system_prompt": system_prompt,
            }
            if temperature is not None:
                options["temperature"] = temperature
            if max_tokens is not None:
                options["max_tokens"] = max_tokens

            return AnthropicProvider(**options)

        raise ValueError(f"Unsupported cloud provider: {self.provider_name}")

    def _resolve_api_key(self) -> Optional[str]:
        if not self.api_key_env:
            return None

        api_key = os.environ.get(self.api_key_env)
        if api_key:
            return api_key

        logger.info(
            "API key env var %s not set; using 1Password helper",
            self.api_key_env,
        )
        return None

    def _translate_response(self, response: Any) -> LLMResponse:
        usage: Optional[Dict[str, Any]] = None
        if hasattr(response, "input_tokens") and hasattr(response, "output_tokens"):
            usage = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
                "cache_creation_tokens": getattr(response, "cache_creation_tokens", 0),
                "cache_read_tokens": getattr(response, "cache_read_tokens", 0),
            }

        return LLMResponse(
            content=str(getattr(response, "content", "")),
            model=str(getattr(response, "model", self.model)),
            usage=usage,
        )

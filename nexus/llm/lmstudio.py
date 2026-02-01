"""Shared LM Studio backend utilities."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, AsyncIterator, Dict, Iterator, Optional, Tuple

import requests

from .base import LLMBackend, LLMResponse

logger = logging.getLogger("nexus.llm.lmstudio")


class LMStudioBackend(LLMBackend):
    """Base LM Studio backend for OpenAI-compatible chat completions."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: Optional[str] = None,
        default_params: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.base_url = self._normalize_base_url(base_url)
        self._model = model
        self._default_params = default_params or {}
        self._timeout = timeout

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Return a full completion from the LM Studio backend."""
        return await asyncio.to_thread(self._complete_sync, prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream completion tokens from the LM Studio backend."""
        queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _worker() -> None:
            try:
                for chunk in self._stream_sync(prompt, **kwargs):
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:  # pragma: no cover - exercised in integration
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        threading.Thread(target=_worker, daemon=True).start()

        while True:
            kind, payload = await queue.get()
            if kind == "chunk":
                yield payload
                continue
            if kind == "error":
                raise payload
            break

    def is_available(self) -> bool:
        """Return True if the LM Studio server responds to a models probe."""
        try:
            response = requests.get(
                f"{self.base_url}/models",
                timeout=5,
            )
            if response.status_code != 200:
                logger.debug(
                    "LM Studio availability probe failed (%s): %s",
                    response.status_code,
                    response.text,
                )
                return False
            return True
        except requests.RequestException as exc:
            logger.debug("LM Studio availability probe failed: %s", exc)
            return False

    def _normalize_base_url(self, base_url: str) -> str:
        base = base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def _ensure_model_ready(self) -> None:
        """Ensure the backend has a model set before issuing requests."""
        if not self._model:
            raise RuntimeError(f"{self.name} backend requires a model to be set")

    def _complete_sync(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self._ensure_model_ready()
        payload, timeout = self._build_payload(prompt, **kwargs)
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
        content = self._extract_content(body)
        usage = body.get("usage") if isinstance(body, dict) else None
        return LLMResponse(content=content, model=str(payload["model"]), usage=usage)

    def _stream_sync(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        self._ensure_model_ready()
        payload, timeout = self._build_payload(prompt, stream=True, **kwargs)
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout,
            stream=True,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            if line == "[DONE]":
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON stream chunk: %s", line)
                continue
            delta = (
                payload.get("choices", [{}])[0]
                .get("delta", {})
                .get("content")
            )
            if delta:
                yield delta

    def _build_payload(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], float]:
        request_timeout = float(kwargs.pop("timeout", self._timeout))
        system_prompt = kwargs.pop("system_prompt", None)
        model = kwargs.pop("model", self._model)
        if not model:
            raise RuntimeError(f"{self.name} backend requires a model to be set")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        for key in (
            "temperature",
            "max_tokens",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "stop",
        ):
            if key in kwargs:
                value = kwargs.pop(key)
            else:
                value = self._default_params.get(key)
            if value is not None:
                payload[key] = value

        if kwargs:
            raise ValueError(f"Unsupported LM Studio parameters: {sorted(kwargs.keys())}")

        return payload, request_timeout

    def _extract_content(self, body: Any) -> str:
        if not isinstance(body, dict):
            raise RuntimeError("LM Studio response was not a JSON object")
        choices = body.get("choices")
        if not choices:
            raise RuntimeError("LM Studio response missing choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if content is None:
            raise RuntimeError("LM Studio response missing content")
        return str(content).strip()

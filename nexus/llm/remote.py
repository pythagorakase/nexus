"""Remote LM Studio backend for network-accessible inference."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .lmstudio import LMStudioBackend


class RemoteLMStudioBackend(LMStudioBackend):
    """LM Studio backend for remote hosts (no lifecycle management)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: Optional[str],
        default_params: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            name="remote",
            base_url=base_url,
            model=model,
            default_params=default_params,
            timeout=timeout,
        )

    def _ensure_model_ready(self) -> None:
        """Ensure a model identifier is configured for remote requests."""
        if not self._model:
            raise RuntimeError(
                "Remote LM Studio backend requires a model; "
                "set a model in configuration or pass one at call time."
            )

"""Local LM Studio backend using the ModelManager for lifecycle control."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .lmstudio import LMStudioBackend

logger = logging.getLogger("nexus.llm.local")


class LocalLMStudioBackend(LMStudioBackend):
    """LM Studio backend that ensures the local model is loaded."""

    def __init__(
        self,
        *,
        base_url: str,
        settings_path: Optional[str] = None,
        unload_on_exit: bool = True,
        default_params: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            name="local",
            base_url=base_url,
            model=None,
            default_params=default_params,
            timeout=timeout,
        )
        self._settings_path = settings_path
        self._unload_on_exit = unload_on_exit
        self._model_manager = None

    def _ensure_model_ready(self) -> None:
        """Ensure the default local model is loaded via ModelManager."""
        if self._model:
            return

        if self._model_manager is None:
            try:
                from nexus.agents.lore.utils.model_manager import ModelManager
            except Exception as exc:
                raise RuntimeError(
                    "LM Studio SDK is required for local backend initialization"
                ) from exc

            self._model_manager = ModelManager(
                self._settings_path,
                unload_on_exit=self._unload_on_exit,
            )

        self._model = self._model_manager.ensure_default_model()
        logger.info("Local LM Studio model ready: %s", self._model)

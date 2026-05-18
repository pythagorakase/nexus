"""
Local LLM Management for LORE

Handles initialization and interaction with local language models via LM Studio SDK.
"""

import logging
import requests
import json
import re
from typing import Optional, Dict, Any, List, Type, Union
from typing import Literal
from pathlib import Path
from pydantic import BaseModel, Field

try:
    import lmstudio as lms

    LMS_SDK_AVAILABLE = True
except ImportError:
    LMS_SDK_AVAILABLE = False

logger = logging.getLogger("nexus.lore.local_llm")

_LM_FINAL_CHANNEL_MARKERS = (
    "<|channel|>final<|message|>",
    "<|start_header_id|>assistant<|end_header_id|>",
)
_LM_CONTROL_TOKEN_RE = re.compile(r"<\|[^>]+?\|>")


# Pydantic models for structured responses
class QAResponse(BaseModel):
    """Structured Q&A response for LORE synthesis"""

    answer: str
    reasoning: str
    cited_chunk_ids: List[int] = Field(default_factory=list)


class SQLStep(BaseModel):
    """Structured planner step for agentic SQL."""

    action: Literal["sql", "final"]
    sql: Optional[str] = None


def _extract_final_channel_text(response: str) -> str:
    """Prefer assistant final-channel text when a local model leaks chat markers."""
    for marker in _LM_FINAL_CHANNEL_MARKERS:
        if marker in response:
            return response.rsplit(marker, 1)[-1]
    return response


def _parse_structured_json_text(response: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from local-model text, including leaked chat wrappers."""
    final_text = _extract_final_channel_text(response).strip()
    if not final_text:
        return None

    decoder = json.JSONDecoder()
    candidates = [final_text]
    candidates.append(_LM_CONTROL_TOKEN_RE.sub(" ", final_text).strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _end = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    return None


class LocalLLMManager:
    """Manages local LLM for LORE's reasoning capabilities via LM Studio SDK"""

    def __init__(
        self,
        settings: Dict[str, Any],
        settings_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
    ):
        """Initialize with LLM configuration from settings"""
        self.settings = settings
        self.settings_path = settings_path
        self.llm_config = (
            settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
        )
        self.system_prompt = system_prompt  # Store the system prompt for use in queries

        # LM Studio configuration
        self.base_url = self.llm_config.get("lmstudio_url", "http://localhost:1234/v1")
        self.model_name = self.llm_config.get("model_name", "local-model")
        self.required_model = self.llm_config.get(
            "required_model", None
        )  # Specific model to load if needed

        # Model path for reference (models stored in ~/.lmstudio/models)
        self.models_dir = Path.home() / ".lmstudio" / "models"

        # Initialize LM Studio client if SDK available
        self.client = None
        self.model = None
        self.loaded_model_id = None

        # Whether to unload model on object deletion
        # During active development we keep the local model resident unless the
        # user explicitly opts out. This avoids re-loading 70B+/120B models on
        # every turn, which can add 45-90 seconds of startup latency.
        self.unload_on_exit: bool = bool(self.llm_config.get("unload_on_exit", False))

        if LMS_SDK_AVAILABLE:
            self._initialize_sdk_client()
        else:
            logger.warning("LM Studio SDK not available, falling back to HTTP requests")
            self._verify_connection()

    def _initialize_sdk_client(self):
        """Initialize LM Studio SDK client - FAILS HARD if not available"""
        try:
            # Extract host from URL
            host = (
                self.base_url.replace("https://", "")
                .replace("http://", "")
                .replace("/v1", "")
                .strip("/")
            )

            # Configure default client (idempotent)
            try:
                lms.configure_default_client(host)
            except Exception as e:
                if "Default client is already created" in str(e):
                    logger.debug(
                        "Default LM Studio client already configured; reusing existing client"
                    )
                else:
                    raise

            # Use model manager to ensure correct model is loaded
            from nexus.llm import ModelManager

            manager = ModelManager(
                self.settings_path, unload_on_exit=self.unload_on_exit
            )
            model_id = manager.ensure_default_model()

            # Get the model handle - already loaded by manager
            self.model = lms.llm()
            self.loaded_model_id = model_id

            logger.info(
                f"LM Studio SDK initialized successfully with model: {self.loaded_model_id}"
            )

        except Exception as e:
            raise RuntimeError(
                f"FATAL: Cannot initialize LM Studio SDK!\n"
                f"Error: {e}\n"
                f"ACTION REQUIRED: Start LM Studio and ensure a model is available"
            )

    def _verify_connection(self):
        """Verify connection to LM Studio API - FAILS HARD if not available (fallback method)"""
        if not LMS_SDK_AVAILABLE:
            try:
                response = requests.get(f"{self.base_url}/models", timeout=5)
                if response.status_code == 200:
                    models = response.json().get("data", [])
                    if not models:
                        raise RuntimeError(
                            f"LM Studio is running but NO MODELS are loaded! Load a model in LM Studio first."
                        )
                    logger.info(
                        f"Connected to LM Studio (HTTP). Available models: {[m['id'] for m in models]}"
                    )
                    return True
                else:
                    raise RuntimeError(
                        f"LM Studio API returned status {response.status_code}. Is the server running?"
                    )
            except requests.exceptions.RequestException as e:
                raise RuntimeError(
                    f"FATAL: Cannot connect to LM Studio API at {self.base_url}!\n"
                    f"Error: {e}\n"
                    f"ACTION REQUIRED: Start LM Studio and enable the local server on port 1234"
                )
        return True

    def query(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Query the local LLM via LM Studio SDK or API.
        FAILS HARD if LM Studio is not available.

        Args:
            prompt: The prompt to send to the LLM
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            system_prompt: Optional system prompt

        Returns:
            LLM response as string

        Raises:
            RuntimeError: If LM Studio is not available or query fails
        """
        # Use provided parameters or fall back to config
        temp = (
            temperature
            if temperature is not None
            else self.llm_config.get("temperature", 0.7)
        )
        max_tok = (
            max_tokens
            if max_tokens is not None
            else self.llm_config.get("max_tokens", 2048)
        )

        if LMS_SDK_AVAILABLE and self.model:
            # Use SDK for cleaner API
            try:
                # Use provided system_prompt, fall back to instance prompt, or FAIL HARD
                if system_prompt:
                    effective_prompt = system_prompt
                elif self.system_prompt:
                    effective_prompt = self.system_prompt
                else:
                    raise RuntimeError(
                        "FATAL: No system prompt available for LLM query!"
                    )
                chat = lms.Chat(effective_prompt)
                chat.add_user_message(prompt)

                config = {
                    "temperature": temp,
                    "maxTokens": max_tok,
                    "topP": self.llm_config.get("top_p", 0.9),
                    "contextLength": self.llm_config.get("context_window", 65536),
                }

                # Add reasoning effort for GPT-OSS models
                if "gpt-oss" in str(self.loaded_model_id).lower():
                    # Get reasoning effort from settings or use high for Q&A
                    reasoning_effort = self.llm_config.get("reasoning_effort", "high")
                    config["reasoning"] = {"effort": reasoning_effort}
                    logger.debug(
                        f"Using {reasoning_effort} reasoning effort for GPT-OSS model"
                    )

                # Debug log the config being sent
                logger.debug(f"LLM query config: {config}")
                logger.debug(f"Prompt length: {len(prompt)} chars")

                result = self.model.respond(chat, config=config)

                return result.content.strip()

            except Exception as e:
                raise RuntimeError(
                    f"FATAL: LM Studio SDK query failed!\nError: {e}\nPrompt was: {prompt[:100]}..."
                )

        else:
            # Fallback to HTTP requests
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temp,
                "max_tokens": max_tok,
                "top_p": self.llm_config.get("top_p", 0.9),
                "stream": False,
            }

            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=60,
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    raise RuntimeError(
                        f"LM Studio API error {response.status_code}: {response.text}"
                    )

            except requests.exceptions.RequestException as e:
                raise RuntimeError(
                    f"FATAL: LM Studio query failed!\nError: {e}\nPrompt was: {prompt[:100]}..."
                )

    def is_available(self) -> bool:
        """Check if local LLM is available via LM Studio"""
        if LMS_SDK_AVAILABLE and self.model:
            return True
        return self._verify_connection()

    def _check_and_manage_loaded_model(self):
        """Check what model is loaded and manage lifecycle"""
        try:
            import requests

            response = requests.get(f"{self.base_url}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                if not models:
                    raise RuntimeError("No models loaded in LM Studio!")

                # Get currently loaded model
                current_model = models[0]["id"] if models else None
                self.loaded_model_id = current_model

                # Check if we need a specific model
                if self.required_model and current_model != self.required_model:
                    logger.info(
                        f"Current model {current_model} != required {self.required_model}"
                    )
                    # In production, we could unload and load the right model
                    # For now, just log the mismatch
                    logger.warning(
                        f"Required model {self.required_model} not loaded, using {current_model}"
                    )

                logger.info(f"Using loaded model: {current_model}")

        except Exception as e:
            logger.error(f"Failed to check loaded models: {e}")
            raise

    def unload_model(self):
        """Unload the current model to free resources"""
        if LMS_SDK_AVAILABLE and self.model:
            try:
                # Use model manager for proper unloading
                from nexus.llm import ModelManager

                manager = ModelManager(
                    self.settings_path, unload_on_exit=self.unload_on_exit
                )
                if manager.unload_model():
                    logger.info(f"Unloaded model: {self.loaded_model_id}")
                else:
                    logger.warning("Model unload may have failed")

                self.model = None
                self.loaded_model_id = None

            except Exception as e:
                logger.error(f"Failed to unload model: {e}")

    def ensure_model_loaded(self):
        """Ensure the required model is loaded"""
        if self.required_model and self.loaded_model_id != self.required_model:
            logger.warning(
                f"Model mismatch! Expected {self.required_model} but {self.loaded_model_id} is loaded."
            )
            logger.warning(
                f"Please load {self.required_model} in LM Studio before proceeding."
            )
            # In production, we'd fail hard here, but for testing we continue
            # raise RuntimeError(f"Wrong model loaded! Please load {self.required_model} in LM Studio")

    def __del__(self):
        """Cleanup on deletion - unload any loaded models"""
        if self.unload_on_exit and hasattr(self, "model") and self.model:
            try:
                self.unload_model()
            except:
                pass  # Best effort cleanup

    def __enter__(self):
        """Context manager entry - ensure model is loaded"""
        self.ensure_model_loaded()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up resources"""
        if self.unload_on_exit:
            self.unload_model()
        return False

    def list_available_models(self) -> List[str]:
        """List models available in LM Studio"""
        try:
            import requests

            response = requests.get(f"{self.base_url}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                return [m["id"] for m in models]
        except:
            pass
        return []

    def structured_query(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Union[BaseModel, Dict[str, Any]]:
        """
        Query the local LLM requesting structured output via LM Studio SDK when available.
        Falls back to plain text JSON parsing with `query()` when SDK structured mode is unavailable.
        """
        if LMS_SDK_AVAILABLE and self.model:
            chat = lms.Chat(
                system_prompt or "You are LORE, a narrative intelligence system."
            )
            chat.add_user_message(prompt)
            try:
                config = {
                    "temperature": (
                        temperature
                        if temperature is not None
                        else self.llm_config.get("temperature", 0.3)
                    ),
                    "maxTokens": (
                        max_tokens
                        if max_tokens is not None
                        else self.llm_config.get("max_tokens", 1024)
                    ),
                    "topP": self.llm_config.get("top_p", 0.9),
                    "contextLength": self.llm_config.get("context_window", 65536),
                }

                # Add reasoning effort for GPT-OSS models in structured queries too
                if "gpt-oss" in str(self.loaded_model_id).lower():
                    reasoning_effort = self.llm_config.get("reasoning_effort", "high")
                    config["reasoning"] = {"effort": reasoning_effort}
                    logger.debug(
                        f"Using {reasoning_effort} reasoning effort for structured query"
                    )

                result = self.model.respond(
                    chat,
                    response_format=response_model,
                    config=config,
                )
                if hasattr(result, "parsed") and result.parsed is not None:
                    return result.parsed
            except Exception as e:
                logger.error(
                    f"SDK structured_query failed: {e}; falling back to JSON parsing"
                )

        # Fallback: call plain query with JSON instructions and parse
        raw = self.query(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
        data = _parse_structured_json_text(raw)
        if data is not None:
            return data

        # Return raw content in a dict-like shape
        return {
            "answer": _extract_final_channel_text(raw).strip(),
            "reasoning": "unstructured",
        }

    async def structured_query_async(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Union[BaseModel, Dict[str, Any]]:
        """Query the local LLM through the HTTP API with an async timeout."""
        import httpx

        request_timeout = timeout if timeout is not None else 60.0
        schema = response_model.model_json_schema()
        model_id = self.loaded_model_id or self.model_name
        prompt_with_schema = (
            f"{prompt}\n\nReturn only valid JSON matching this schema:\n"
            f"{json.dumps(schema, sort_keys=True)}"
        )
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                    or "You are LORE, a narrative intelligence system.",
                },
                {"role": "user", "content": prompt_with_schema},
            ],
            "temperature": (
                temperature
                if temperature is not None
                else self.llm_config.get("temperature", 0.3)
            ),
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else self.llm_config.get("max_tokens", 1024)
            ),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Local structured query exceeded {request_timeout:.3f}s timeout"
            ) from exc

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str):
            parsed = json.loads(content)
        else:
            parsed = content
        return response_model.model_validate(parsed)

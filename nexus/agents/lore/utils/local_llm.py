"""
Local LLM Management for LORE

Handles initialization and interaction with local language models via LM Studio SDK.
"""

import logging
import requests
import json
import re
import unicodedata
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
_QUERY_PREFIX_RE = re.compile(
    r"^(?:query\s*)?(?:\d+[\.)]|[-*•])\s*|^query\s*\d*\s*:\s*",
    re.IGNORECASE,
)
_META_QUERY_PREFIXES = (
    "analysis ",
    "based on the current narrative context",
    "context analysis",
    "each query should",
    "format:",
    "generate ",
    "here are",
    "key entities",
    "let's ",
    "locations:",
    "no numbering",
    "the user wants",
    "thus produce",
    "user input",
    "we need",
    "we must",
    "we should",
    "we'll produce",
)
_META_QUERY_FRAGMENTS = (
    "complete question or search phrase",
    "exactly 3-5",
    "generate retrieval queries",
    "generate queries",
    "make sure",
    "need 3-5 queries",
    "no bullet",
    "numbering or bullets",
    "output exactly",
    "produce 4 queries",
    "query phrase",
    "one per line",
    "retrieval queries to search",
)
_GENERIC_RETRIEVAL_QUERIES = {
    "background info on key entities",
    "character relationships and interactions",
    "past events at",
    "relevant past events involving these characters",
}
_TEMPLATE_PLACEHOLDER_QUERY_PREFIXES = (
    "background information on key entities (",
    "history of locations (",
    "so there is a scene where someone maybe",
)
_MIN_RETRIEVAL_QUERIES = 3


# Pydantic models for structured responses
class NarrativeAnalysis(BaseModel):
    """Structured analysis of narrative context"""

    characters: List[str] = Field(description="Character names mentioned or relevant")
    locations: List[str] = Field(description="Locations mentioned or relevant")
    context_type: str = Field(
        description="Type of narrative context: dialogue/action/exploration/transition"
    )
    entities_for_retrieval: List[str] = Field(
        description="Key entities needing deeper context retrieval"
    )
    confidence_score: float = Field(
        default=0.8, description="Confidence in the analysis"
    )


class QAResponse(BaseModel):
    """Structured Q&A response for LORE synthesis"""

    answer: str
    reasoning: str
    cited_chunk_ids: List[int] = Field(default_factory=list)


class SQLStep(BaseModel):
    """Structured planner step for agentic SQL."""

    action: Literal["sql", "final"]
    sql: Optional[str] = None


class RetrievalQueries(BaseModel):
    """Structured retrieval query generation for Phase 4"""

    queries: List[str] = Field(
        min_length=3,
        max_length=5,
        description="Retrieval queries for finding relevant narrative context",
    )


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


def _has_well_formed_double_quotes(query: str) -> bool:
    """Return whether double quotes look like balanced phrase delimiters."""
    quote_positions = [match.start() for match in re.finditer('"', query)]
    if not quote_positions:
        return True
    if len(quote_positions) % 2 == 1:
        return False

    for pair_index, quote_index in enumerate(quote_positions):
        previous_char = query[quote_index - 1] if quote_index > 0 else ""
        next_char = query[quote_index + 1] if quote_index + 1 < len(query) else ""
        is_opening = pair_index % 2 == 0

        if is_opening:
            if (
                previous_char
                and not previous_char.isspace()
                and previous_char not in "([{:"
            ):
                return False
            if not next_char or next_char.isspace():
                return False
        else:
            if not previous_char or previous_char.isspace():
                return False
            if next_char and not next_char.isspace() and next_char not in ".,;:)]}":
                return False

    return True


def _clean_retrieval_query(query: Any) -> Optional[str]:
    """Normalize one candidate retrieval query and reject instruction/meta text."""
    if not isinstance(query, str):
        return None

    cleaned = unicodedata.normalize("NFKD", query)
    cleaned = cleaned.replace("\xa0", " ").replace("…", "...")
    cleaned = _LM_CONTROL_TOKEN_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split()).strip()
    cleaned = _QUERY_PREFIX_RE.sub("", cleaned).strip().strip("`")

    if len(cleaned) <= 10:
        return None

    lowered = cleaned.lower()
    normalized_lowered = lowered.rstrip(" .:")
    if normalized_lowered in _GENERIC_RETRIEVAL_QUERIES:
        return None
    # Use the raw lowered text: normalized_lowered strips the trailing dots.
    if lowered.endswith("..."):
        return None
    if normalized_lowered.startswith(_TEMPLATE_PLACEHOLDER_QUERY_PREFIXES):
        return None
    if cleaned.startswith(("{", "[")):
        return None
    if lowered.startswith(("select ", "with ")):
        return None
    if '"action"' in lowered or '"sql"' in lowered:
        return None
    if lowered.startswith(_META_QUERY_PREFIXES):
        return None
    if any(fragment in lowered for fragment in _META_QUERY_FRAGMENTS):
        return None
    if not any(character.isalpha() for character in cleaned):
        return None
    if len(re.findall(r"[A-Za-z0-9]+", cleaned)) < 3:
        return None
    if not _has_well_formed_double_quotes(cleaned):
        return None

    return cleaned


def _sanitize_retrieval_queries(queries: List[Any], limit: int = 5) -> List[str]:
    """Return deduplicated, MEMNON-safe retrieval queries."""
    valid_queries: List[str] = []
    seen: set[str] = set()

    for query in queries:
        cleaned = _clean_retrieval_query(query)
        if not cleaned:
            continue

        key = cleaned.casefold()
        if key in seen:
            continue

        valid_queries.append(cleaned)
        seen.add(key)

        if len(valid_queries) >= limit:
            break

    return valid_queries


def _has_complete_retrieval_query_set(queries: List[str]) -> bool:
    """Return whether a generated query set is complete enough for deep search."""
    return len(queries) >= _MIN_RETRIEVAL_QUERIES


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
        self.fallback_retrieval_query: str = (
            settings.get("lore", {})
            .get("retrieval", {})
            .get("fallback_query", "Recent narrative events")
        )

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

    def analyze_narrative_context(
        self, warm_slice: List[Dict], user_input: str
    ) -> Dict[str, Any]:
        """
        Analyze narrative context to identify entities and context type.

        Args:
            warm_slice: List of recent narrative chunks
            user_input: User's input

        Returns:
            Analysis results dictionary
        """
        # Combine warm slice text
        warm_text = "\n".join([chunk.get("text", "")[:200] for chunk in warm_slice[:3]])

        # REQUIRE the system prompt - fail hard if not loaded
        if not self.system_prompt:
            raise RuntimeError(
                "FATAL: LORE system prompt not loaded! Cannot perform narrative analysis without proper instructions."
            )
        system_prompt = self.system_prompt

        if LMS_SDK_AVAILABLE and self.model:
            # Use structured output for clean parsing
            try:
                chat = lms.Chat(system_prompt)
                chat.add_user_message(
                    f"""Analyze the following narrative context and user input.

Recent narrative:
{warm_text}

User input: {user_input}

Provide a structured analysis of characters, locations, context type, and entities needing retrieval."""
                )

                result = self.model.respond(
                    chat,
                    response_format=NarrativeAnalysis,
                    config={
                        "temperature": 0.3,
                        "maxTokens": 500,
                        "contextLength": self.llm_config.get("context_window", 65536),
                    },
                )

                # Convert structured output to dict safely
                try:
                    if hasattr(result, "parsed") and result.parsed is not None:
                        analysis = result.parsed
                        # result.parsed may already be a dict or a Pydantic model
                        if isinstance(analysis, dict):
                            return {
                                "characters": analysis.get("characters", []),
                                "locations": analysis.get("locations", []),
                                "context_type": analysis.get("context_type", "unknown"),
                                "entities_for_retrieval": analysis.get(
                                    "entities_for_retrieval", []
                                ),
                                "confidence_score": analysis.get(
                                    "confidence_score", 0.8
                                ),
                            }
                        else:
                            return {
                                "characters": getattr(analysis, "characters", []),
                                "locations": getattr(analysis, "locations", []),
                                "context_type": getattr(
                                    analysis, "context_type", "unknown"
                                ),
                                "entities_for_retrieval": getattr(
                                    analysis, "entities_for_retrieval", []
                                ),
                                "confidence_score": getattr(
                                    analysis, "confidence_score", 0.8
                                ),
                            }
                except Exception as e:
                    logger.error(f"Error processing structured analysis: {e}")
                    # Fall through to text parsing

            except Exception as e:
                logger.error(
                    f"SDK structured analysis failed: {e}, falling back to text parsing"
                )
                # Fall through to text parsing

        # Fallback to text parsing (for non-SDK or if structured output fails)
        prompt = f"""Analyze the following narrative context and user input.

Recent narrative:
{warm_text}

User input: {user_input}

Identify:
1. CHARACTER: [List character names, one per line]
2. LOCATION: [List locations, one per line]
3. CONTEXT_TYPE: [dialogue/action/exploration/transition]
4. KEY_ENTITIES: [Entities needing deeper context retrieval]

Response format - use exact headers:"""

        response = self.query(
            prompt, temperature=0.3, max_tokens=500, system_prompt=system_prompt
        )

        # Parse the response
        result = {
            "characters": [],
            "locations": [],
            "context_type": "unknown",
            "entities_for_retrieval": [],
        }

        try:
            lines = response.split("\n")
            current_section = None

            for line in lines:
                line = line.strip()
                if "CHARACTER:" in line:
                    current_section = "characters"
                elif "LOCATION:" in line:
                    current_section = "locations"
                elif "CONTEXT_TYPE:" in line:
                    context_type = line.split("CONTEXT_TYPE:")[-1].strip()
                    result["context_type"] = context_type.lower()
                    current_section = None
                elif "KEY_ENTITIES:" in line:
                    current_section = "entities_for_retrieval"
                elif line and current_section:
                    # Add to current section list
                    if line.startswith("-"):
                        line = line[1:].strip()
                    if line and not line.startswith("["):
                        result[current_section].append(line)
        except Exception as e:
            logger.error(f"Error parsing LLM analysis: {e}")

        return result

    def generate_retrieval_queries(
        self, context_analysis: Dict[str, Any], user_input: str
    ) -> List[str]:
        """
        Generate targeted retrieval queries based on context analysis.

        This method asks the LLM to generate 3-5 retrieval queries that would help
        retrieve relevant past narrative to inform the story continuation.

        Args:
            context_analysis: Results from analyze_narrative_context
            user_input: User's input

        Returns:
            List of retrieval queries (3-5 strings)
        """
        # Extract entities from context analysis
        characters = context_analysis.get("characters", [])
        locations = context_analysis.get("locations", [])
        entities_for_retrieval = context_analysis.get("entities_for_retrieval", [])
        context_type = context_analysis.get("context_type", "unknown")

        # Build a prompt for query generation
        # REQUIRE the system prompt - fail hard if not loaded
        if not self.system_prompt:
            raise RuntimeError(
                "FATAL: LORE system prompt not loaded! Cannot generate retrieval queries without proper instructions."
            )
        system_prompt = self.system_prompt

        if LMS_SDK_AVAILABLE and self.model:
            # Use structured output for clean, validated queries
            try:
                chat = lms.Chat(system_prompt)
                chat.add_user_message(
                    f"""Generate retrieval queries to search for relevant past events, character history, or world information.

User input: {user_input}

Context analysis:
- Characters present: {', '.join(characters) if characters else 'None'}
- Locations: {', '.join(locations) if locations else 'None'}
- Context type: {context_type}
- Key entities: {', '.join(entities_for_retrieval) if entities_for_retrieval else 'None'}

Generate 3-5 specific queries that would retrieve:
1. Relevant past events involving these characters
2. History of these locations
3. Character relationships and interactions
4. Background information on key entities

Each query should be a complete search phrase that captures what information you're looking for."""
                )

                result = self.model.respond(
                    chat,
                    response_format=RetrievalQueries,
                    config={
                        "temperature": 0.5,  # Moderate creativity for varied queries
                        "maxTokens": 300,
                        "topP": 0.9,
                        "contextLength": 65536,
                        "reasoning": {"effort": "high"},
                    },
                )

                # Access the parsed result correctly
                # LM Studio SDK can return parsed as either dict or Pydantic model
                if hasattr(result, "parsed") and result.parsed:
                    parsed = result.parsed
                    if isinstance(parsed, dict):
                        queries = parsed.get("queries", [])
                    else:
                        queries = parsed.queries
                elif isinstance(result, dict):
                    queries = result.get("queries", [])
                else:
                    # Try direct access as last resort
                    queries = result.queries

                # Debug: log what we got
                logger.debug(f"Structured output result type: {type(result)}")
                logger.debug(f"Parsed queries: {queries}")

                valid_queries = _sanitize_retrieval_queries(queries)

                # Sanitization can drop generic or malformed items even when the
                # Pydantic response had the requested list length.
                if _has_complete_retrieval_query_set(valid_queries):
                    logger.info(
                        f"Generated {len(valid_queries)} valid retrieval queries via structured output"
                    )
                    return valid_queries
                else:
                    logger.warning(
                        f"Structured output returned fewer than {_MIN_RETRIEVAL_QUERIES} valid queries, falling back to text parsing"
                    )
                    raise ValueError("Invalid structured output")

            except Exception as e:
                logger.warning(
                    f"SDK structured output failed: {e}, falling back to text parsing"
                )
                # Fall through to text parsing approach

        # Fallback: Use text parsing with the regular query method
        prompt = f"""Based on the current narrative context, generate 3-5 retrieval queries to search for relevant past events, character history, or world information.

User input: {user_input}

Context analysis:
- Characters present: {', '.join(characters) if characters else 'None'}
- Locations: {', '.join(locations) if locations else 'None'}
- Context type: {context_type}
- Key entities: {', '.join(entities_for_retrieval) if entities_for_retrieval else 'None'}

Generate queries that would retrieve:
1. Relevant past events involving these characters
2. History of these locations
3. Character relationships and interactions
4. Background information on key entities

Format: Output exactly 3-5 queries, one per line, no numbering or bullets.
Each query should be a complete question or search phrase."""

        try:
            response = self.query(
                prompt=prompt,
                temperature=0.5,  # Moderate creativity
                max_tokens=300,  # Keep it concise
                system_prompt=system_prompt,
            )

            response = _extract_final_channel_text(response)
            query_candidates = list(response.splitlines())
            queries = _sanitize_retrieval_queries(query_candidates)

            # Ensure we have between 3-5 queries
            if not _has_complete_retrieval_query_set(queries):
                # Fallback: add generic queries based on user input
                logger.warning(
                    f"Only generated {len(queries)} queries; need {_MIN_RETRIEVAL_QUERIES}, adding fallbacks"
                )
                fallback_candidates = []
                if user_input:
                    fallback_candidates.append(user_input)
                if characters:
                    fallback_candidates.append(f"What happened with {characters[0]}?")
                if locations:
                    fallback_candidates.append(f"Past events at {locations[0]}")
                query_candidates.extend(fallback_candidates)
                queries = _sanitize_retrieval_queries(query_candidates)

            logger.info(f"Generated {len(queries)} retrieval queries via text parsing")
            return queries or [self.fallback_retrieval_query]

        except Exception as e:
            logger.error(f"Failed to generate retrieval queries: {e}")
            # Fallback: return basic queries
            fallback_queries = []
            if user_input:
                fallback_queries.append(user_input)
            if characters:
                fallback_queries.append(f"Past events involving {characters[0]}")
            if locations:
                fallback_queries.append(f"History of {locations[0]}")
            fallback_queries = _sanitize_retrieval_queries(fallback_queries)

            # Ensure at least one query
            if not fallback_queries:
                fallback_queries = [self.fallback_retrieval_query]

            return fallback_queries

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

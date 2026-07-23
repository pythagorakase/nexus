"""
LOGON Utility - API Communication Handler for LORE

Manages communication with Apex AI providers (OpenAI, Anthropic, xAI).
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional, cast

import psycopg2

# Add scripts directory to path for API imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from scripts.api_openai import OpenAIProvider  # noqa: E402
from scripts.api_anthropic import AnthropicProvider  # noqa: E402
from nexus.agents.logon.apex_schema import (  # noqa: E402
    StoryTurnResponse,
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import (  # noqa: E402
    PresenceBaseline,
    PresenceRef,
    SkaldTurnWire,
    hydrate_skald_turn,
    skald_wire_lenient_schema,
    skald_wire_strict_text_format,
)
from nexus.agents.orrery.tag_library import (  # noqa: E402
    format_tag_library_for_prompt,
)
from nexus.config.loader import get_provider_for_model, resolve_model_ref  # noqa: E402
from nexus.memory.context_state import is_retrograde_summary  # noqa: E402
from nexus.memory.retrieval_coverage import coerce_chunk_id  # noqa: E402

logger = logging.getLogger("nexus.lore.logon")


def read_presence_baseline(
    dbname: str,
    parent_chunk_id: int,
) -> PresenceBaseline:
    """Read one parent chunk's character roster and setting place."""

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.name
                FROM chunk_character_references AS ccr
                JOIN characters AS c ON c.id = ccr.character_id
                WHERE ccr.chunk_id = %s
                  AND ccr.reference::text = 'present'
                ORDER BY c.id
                """,
                (parent_chunk_id,),
            )
            present = [
                PresenceRef(kind="character", id=row[0], name=row[1])
                for row in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT p.id, p.name
                FROM place_chunk_references AS pcr
                JOIN places AS p ON p.id = pcr.place_id
                WHERE pcr.chunk_id = %s
                  AND pcr.reference_type::text = 'setting'
                ORDER BY p.id
                """,
                (parent_chunk_id,),
            )
            setting_rows = cur.fetchall()
    finally:
        conn.close()

    if len(setting_rows) > 1:
        raise ValueError(f"Parent chunk {parent_chunk_id} has multiple setting places")
    setting = (
        PresenceRef(
            kind="place",
            id=setting_rows[0][0],
            name=setting_rows[0][1],
        )
        if setting_rows
        else None
    )
    return PresenceBaseline(present=present, setting=setting)


async def read_presence_baseline_async(
    dbname: str,
    parent_chunk_id: int,
) -> PresenceBaseline:
    """Read a presence baseline without blocking the async turn loop."""

    return await asyncio.to_thread(
        read_presence_baseline,
        dbname,
        parent_chunk_id,
    )


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    """Return a JSON-like mapping from DB or model payloads."""

    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Failed to parse mapping JSON for prompt context: %r", value)
            return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _string_value(value: Any) -> str:
    """Render a scalar prompt value, keeping empty values out of prompts."""

    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, set):
        return ", ".join(
            str(item) for item in sorted(value, key=str) if item not in (None, "")
        )
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item not in (None, ""))
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _labeled_lines(rows: list[tuple[str, Any]]) -> list[str]:
    """Render label/value rows, omitting absent values."""

    lines: list[str] = []
    for label, value in rows:
        rendered = _string_value(value)
        if rendered:
            lines.append(f"- {label}: {rendered}")
    return lines


def _retrieval_source_label(memory: Dict[str, Any]) -> str:
    """Render the retrieval corpus and identity without faking a chunk id."""

    if is_retrograde_summary(memory):
        summary_id = memory.get("summary_id")
        if summary_id is None:
            summary_id = (memory.get("metadata") or {}).get("summary_id")
        return f"Retrograde summary {summary_id}"

    chunk_id = coerce_chunk_id(memory)
    return f"Chunk {chunk_id}" if chunk_id is not None else "Retrieved passage"


class LogonUtility:
    """Wrapper for Apex AI API calls using existing providers"""

    def __init__(
        self,
        settings: Dict[str, Any],
        dbname: Optional[str] = None,
        model_override: Optional[str] = None,
        bootstrap_mode: bool = False,
    ):
        """
        Initialize LOGON utility with configured provider.

        Args:
            settings: Application settings dictionary
            dbname: Database name (save_01 through save_05).
                    If not provided, uses NEXUS_SLOT env var.
            model_override: Optional model to use instead of settings/slot config.
                           If None, will check slot's configured model first.
            bootstrap_mode: Whether this LOGON instance is generating chunk #1.
        """
        self.settings = settings
        self.dbname = dbname
        self.model_override = model_override
        self.bootstrap_mode = bootstrap_mode
        self.provider: Optional[OpenAIProvider | AnthropicProvider] = None
        self._system_prompt: Optional[str] = None
        self._provider_bootstrap_mode: Optional[bool] = None
        self._provider_wire_type: Optional[str] = None
        self._validation_dbname: Optional[str] = None
        self._schema_format_cache: Dict[type, Dict[str, Any]] = {}

    def _load_system_prompt(self, is_bootstrap: Optional[bool] = None) -> str:
        """Load and combine storyteller instructions with live slot context."""
        from nexus.api.slot_utils import require_slot_dbname

        is_bootstrap = self.bootstrap_mode if is_bootstrap is None else is_bootstrap

        # Load storyteller core prompt
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        core_prompt_path = prompts_dir / "storyteller_core.md"

        try:
            core_prompt = core_prompt_path.read_text()
            logger.info(f"Loaded storyteller core prompt ({len(core_prompt)} chars)")
        except FileNotFoundError:
            logger.warning(
                f"Core prompt not found at {core_prompt_path}, using minimal fallback"
            )
            core_prompt = (
                "You are a narrative intelligence system generating interactive "
                "fiction."
            )

        system_prompt = core_prompt
        if is_bootstrap:
            bootstrap_path = prompts_dir / "storyteller_bootstrap.md"
            try:
                bootstrap_content = bootstrap_path.read_text()
                system_prompt = f"{system_prompt}\n\n---\n\n{bootstrap_content}"
                logger.info(
                    "Appended storyteller bootstrap supplement (%s chars)",
                    len(bootstrap_content),
                )
            except FileNotFoundError:
                logger.warning(
                    "Bootstrap supplement not found at %s, using core prompt only",
                    bootstrap_path,
                )

        # Query setting from global_variables
        try:
            db = require_slot_dbname(dbname=self.dbname)
            try:
                tag_library_prompt = format_tag_library_for_prompt(db)
                if tag_library_prompt:
                    system_prompt = f"{system_prompt}\n\n---\n\n{tag_library_prompt}"
            except Exception as e:
                logger.warning(
                    "Failed to load Orrery tag library for storyteller prompt: %s",
                    e,
                )

            conn = psycopg2.connect(host="localhost", database=db, user="pythagor")
            with conn.cursor() as cur:
                cur.execute("SELECT setting FROM global_variables WHERE id = true")
                result = cur.fetchone()

                if result and result[0]:
                    setting_content = self._format_setting_context(result[0])
                    if not setting_content:
                        logger.warning(
                            "Setting data found in global_variables but no "
                            "promptable fields were present"
                        )
                        return system_prompt

                    # Combine core prompt with setting
                    combined_prompt = f"{system_prompt}\n\n{setting_content}"
                    logger.info(
                        "Combined prompt with setting context (%s chars)",
                        len(setting_content),
                    )
                    return combined_prompt
                else:
                    logger.warning(
                        "No setting data found in global_variables, using core "
                        "prompt only"
                    )
                    return system_prompt

        except Exception as e:
            logger.error(f"Failed to load setting from database: {e}")
            return system_prompt
        finally:
            if "conn" in locals():
                conn.close()

    @staticmethod
    def _format_setting_context(setting_data: Any) -> str:
        """Render persisted SettingCard JSON into system-prompt context."""

        setting = _coerce_mapping(setting_data)
        if not setting:
            return ""

        legacy_content = _string_value(setting.get("content"))
        if legacy_content:
            legacy_title = _string_value(setting.get("title")) or "Setting Context"
            return f"## {legacy_title}\n\n{legacy_content}"

        world_name = _string_value(setting.get("world_name")) or "Setting Context"
        lines = [f"## Setting Context: {world_name}"]

        diegetic_artifact = _string_value(setting.get("diegetic_artifact"))
        if diegetic_artifact:
            lines.extend(["", "### Diegetic Artifact", diegetic_artifact])

        field_rows = [
            ("Genre", setting.get("genre")),
            ("Secondary Genres", setting.get("secondary_genres")),
            ("Tone", setting.get("tone")),
            ("Time Period", setting.get("time_period")),
            ("Technology Level", setting.get("tech_level")),
            ("Geographic Scope", setting.get("geographic_scope")),
            ("Themes", setting.get("themes")),
            ("Magic Exists", setting.get("magic_exists")),
            ("Magic Description", setting.get("magic_description")),
            ("Political Structure", setting.get("political_structure")),
            ("Major Conflict", setting.get("major_conflict")),
            ("Cultural Notes", setting.get("cultural_notes")),
            ("Language Notes", setting.get("language_notes")),
        ]
        structured_lines = _labeled_lines(field_rows)
        if structured_lines:
            lines.extend(["", "### Structured Setting Card", *structured_lines])

        return "\n".join(lines)

    def _get_slot_model(self) -> Optional[str]:
        """Get the model configured for the current slot from global_variables."""
        from nexus.api.slot_utils import require_slot_dbname

        try:
            db = require_slot_dbname(dbname=self.dbname)
            conn = psycopg2.connect(host="localhost", database=db, user="pythagor")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
                    result = cur.fetchone()
                    return result[0] if result else None
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to get slot model: {e}")
            return None

    @staticmethod
    def _resolve_generation_model(model: str) -> str:
        """Resolve a runtime roster reference before constructing the provider."""
        return resolve_model_ref(model) if model.startswith("@") else model

    def _initialize_provider(self, is_bootstrap: Optional[bool] = None) -> None:
        """Initialize the appropriate API provider based on settings and slot config."""
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        provider_bootstrap_mode = (
            self.bootstrap_mode if is_bootstrap is None else is_bootstrap
        )

        # Model priority: override > slot config > settings
        model = self.model_override
        if not model:
            model = self._get_slot_model()
        if not model:
            model = apex_settings.get("model", "gpt-4o")
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError("LOGON could not resolve a storyteller model id")
        model = self._resolve_generation_model(model)

        provider_type = get_provider_for_model(model) or apex_settings.get(
            "provider", "openai"
        )

        # OpenAI-compatible base_url routing (mock TEST server, local servers):
        # the endpoint lives in the [global.model.api_models] registry (#401).
        from nexus.config import get_openai_compatible_endpoint

        endpoint = get_openai_compatible_endpoint(model)
        base_url = endpoint["base_url"] if endpoint else None
        api_key = endpoint["api_key"] if endpoint else None
        structured_transport = cast(
            Literal["responses", "chat_completions"],
            endpoint["structured_transport"] if endpoint else "responses",
        )
        request_timeout = endpoint["request_timeout_seconds"] if endpoint else None
        if base_url:
            logger.info(f"Model {model}: routing to base_url {base_url}")

        # Load system prompt
        system_prompt = self._load_system_prompt(provider_bootstrap_mode)
        self._system_prompt = system_prompt
        self._provider_bootstrap_mode = provider_bootstrap_mode

        structured_output_retries = apex_settings.get("structured_output_retries", 3)

        # Generation-time registry validation for Skald's orrery_tags: invalid
        # names become a ModelRetry while the model still owns the turn,
        # instead of a dead commit later (M9 gate finding).
        from nexus.agents.logon.orrery_tag_validation import (
            build_storyteller_tag_validator,
        )
        from nexus.api.slot_utils import require_slot_dbname

        # Slotless LOGON usage (model_override without dbname or NEXUS_SLOT)
        # has no registry to validate against; skip the validator rather
        # than failing provider initialization (Codex review on PR #383).
        try:
            validation_dbname: Optional[str] = require_slot_dbname(dbname=self.dbname)
        except Exception:
            validation_dbname = None
        output_validator = build_storyteller_tag_validator(validation_dbname)
        self._validation_dbname = validation_dbname
        self._schema_format_cache = {}

        if provider_type == "anthropic":
            self._provider_wire_type = "anthropic"
            self.provider = AnthropicProvider(
                model=model,
                max_tokens=apex_settings.get(
                    "max_output_tokens", apex_settings.get("max_tokens", 4000)
                ),
                system_prompt=system_prompt,
                structured_output_retries=structured_output_retries,
                output_validator=output_validator,
            )
        elif provider_type == "openai" or base_url:
            # Native OpenAI, or any OpenAI-compatible server registered with a
            # base_url in [global.model.api_models] (mock TEST, Ollama, vLLM).
            self._provider_wire_type = "local" if base_url else "openai"
            self.provider = OpenAIProvider(
                model=model,
                temperature=apex_settings.get("temperature", 0.7),
                max_output_tokens=apex_settings.get("max_output_tokens", 25000),
                reasoning_effort=apex_settings.get("reasoning_effort", "medium"),
                system_prompt=system_prompt,
                base_url=base_url,
                api_key=api_key,
                structured_transport=structured_transport,
                request_timeout=request_timeout,
                structured_output_retries=structured_output_retries,
                output_validator=output_validator,
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        logger.info(
            f"LOGON initialized with {provider_type} provider using model {model}"
        )
        logger.info(f"System prompt loaded: {len(system_prompt)} chars")

    def _ensure_provider(
        self, context_payload: Optional[Dict[str, Any]] = None
    ) -> None:
        """Ensure the provider is initialized before use."""
        desired_bootstrap_mode = (
            self._is_bootstrap_context(context_payload)
            if context_payload is not None
            else self.bootstrap_mode
        )

        if self.provider is None:
            self._initialize_provider(desired_bootstrap_mode)
            return

        resolved_model = self.model_override or self._get_slot_model()
        if resolved_model:
            resolved_model = self._resolve_generation_model(resolved_model)
        model_changed = bool(
            resolved_model and getattr(self.provider, "model", None) != resolved_model
        )
        bootstrap_changed = self._provider_bootstrap_mode != desired_bootstrap_mode
        if model_changed or bootstrap_changed:
            logger.info(
                "LOGON provider context changed. Reinitializing provider for model %s "
                "(bootstrap=%s)",
                resolved_model or getattr(self.provider, "model", None),
                desired_bootstrap_mode,
            )
            self._initialize_provider(desired_bootstrap_mode)

    def ensure_provider(self) -> None:
        """Public wrapper for provider initialization."""
        self._ensure_provider()

    def _stamp_generation_model(self, response: StoryTurnResponse) -> StoryTurnResponse:
        """Attach the concrete model used by the successful provider call."""
        generation_model = getattr(self.provider, "model", None)
        if not isinstance(generation_model, str) or not generation_model.strip():
            raise RuntimeError(
                "Successful LOGON generation did not expose the provider model id"
            )
        response.generation_model = generation_model
        return response

    def generate_narrative(self, context_payload: Dict[str, Any]) -> StoryTurnResponse:
        """Generate narrative from context payload with structured output."""
        self._ensure_provider(context_payload)
        assert self.provider is not None
        # Format the context into a prompt
        prompt = self._format_context_prompt(context_payload)
        schema_model = self._select_response_schema(context_payload)
        schema_kwargs = self._schema_format_kwargs(schema_model)

        # Get structured completion from provider
        # This returns a tuple of (parsed_object, llm_response)
        try:
            parsed_response, _llm_response = self.provider.get_structured_completion(
                prompt,
                schema_model,
                **schema_kwargs,
            )
            presence_baseline = self._read_presence_baseline_for_context(
                context_payload,
                schema_model,
            )
            response = self._hydrate_provider_response(
                parsed_response,
                schema_model,
                presence_baseline=presence_baseline,
            )
            logger.debug(
                "Received structured response with narrative length: %s",
                len(response.narrative),
            )
            return self._stamp_generation_model(response)
        except Exception:
            logger.exception("Failed to get structured response")
            raise

    async def generate_narrative_async(
        self, context_payload: Dict[str, Any]
    ) -> StoryTurnResponse:
        """Generate narrative from context payload without blocking the event loop."""
        self._ensure_provider(context_payload)
        assert self.provider is not None
        prompt = self._format_context_prompt(context_payload)
        schema_model = self._select_response_schema(context_payload)
        schema_kwargs = self._schema_format_kwargs(schema_model)

        try:
            parsed_response, _llm_response = (
                await self.provider.get_structured_completion_async(
                    prompt,
                    schema_model,
                    **schema_kwargs,
                )
            )
            presence_baseline = await self._read_presence_baseline_for_context_async(
                context_payload,
                schema_model,
            )
            response = self._hydrate_provider_response(
                parsed_response,
                schema_model,
                presence_baseline=presence_baseline,
            )
            logger.debug(
                "Received structured response with narrative length: %s",
                len(response.narrative),
            )
            return self._stamp_generation_model(response)
        except Exception:
            logger.exception("Failed to get structured response")
            raise

    def _select_response_schema(
        self, context_payload: Dict[str, Any]
    ) -> type[StorytellerResponseBootstrap] | type[SkaldTurnWire]:
        """Select the structured output schema for the current narrative context."""
        if self._is_bootstrap_context(context_payload):
            return StorytellerResponseBootstrap

        return SkaldTurnWire

    @staticmethod
    def _parent_chunk_id(context_payload: Mapping[str, Any]) -> Optional[int]:
        """Return the explicit parent chunk id carried by LORE context."""

        metadata = context_payload.get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        parent_chunk_id = metadata.get("target_chunk_id")
        if parent_chunk_id is None:
            return None
        if isinstance(parent_chunk_id, bool) or not isinstance(parent_chunk_id, int):
            raise TypeError("metadata.target_chunk_id must be an integer")
        if parent_chunk_id <= 0:
            raise ValueError("metadata.target_chunk_id must be positive")
        return parent_chunk_id

    def _read_presence_baseline_for_context(
        self,
        context_payload: Mapping[str, Any],
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
    ) -> Optional[PresenceBaseline]:
        """Read the parent baseline for a synchronous extended turn."""

        if schema_model is not SkaldTurnWire:
            return None
        parent_chunk_id = self._parent_chunk_id(context_payload)
        if parent_chunk_id is None:
            return None
        if self.dbname is None:
            raise RuntimeError("Presence hydration requires a slot database")
        return read_presence_baseline(self.dbname, parent_chunk_id)

    async def _read_presence_baseline_for_context_async(
        self,
        context_payload: Mapping[str, Any],
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
    ) -> Optional[PresenceBaseline]:
        """Read the parent baseline for an asynchronous extended turn."""

        if schema_model is not SkaldTurnWire:
            return None
        parent_chunk_id = self._parent_chunk_id(context_payload)
        if parent_chunk_id is None:
            return None
        if self.dbname is None:
            raise RuntimeError("Presence hydration requires a slot database")
        return await read_presence_baseline_async(self.dbname, parent_chunk_id)

    @staticmethod
    def _hydrate_provider_response(
        parsed_response: Any,
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
        *,
        presence_baseline: Optional[PresenceBaseline] = None,
    ) -> StoryTurnResponse:
        """Hydrate extended wire output while leaving bootstrap output unchanged."""

        if schema_model is SkaldTurnWire:
            if not isinstance(parsed_response, SkaldTurnWire):
                raise TypeError(
                    "Extended LOGON provider returned a non-SkaldTurnWire response"
                )
            return hydrate_skald_turn(
                parsed_response,
                presence_baseline=presence_baseline,
            )
        if not isinstance(parsed_response, StorytellerResponseBootstrap):
            raise TypeError(
                "Bootstrap LOGON provider returned a non-bootstrap response"
            )
        return parsed_response

    def _schema_format_kwargs(self, schema_model: type) -> Dict[str, Any]:
        """Return provider-specific native schema overrides for LOGON."""

        if not self._provider_wire_type:
            return {}
        if schema_model in self._schema_format_cache:
            return self._schema_format_cache[schema_model]

        from nexus.api.native_structured_output import (
            anthropic_output_config,
            openai_response_text_format,
        )

        kwargs: Dict[str, Any]
        if schema_model is SkaldTurnWire:
            if self._provider_wire_type == "openai":
                kwargs = {"text_format": skald_wire_strict_text_format()}
            elif self._provider_wire_type == "local":
                kwargs = {
                    "text_format": openai_response_text_format(
                        SkaldTurnWire,
                        schema=skald_wire_lenient_schema(),
                    )
                }
            elif self._provider_wire_type == "anthropic":
                kwargs = {
                    "output_config": anthropic_output_config(
                        SkaldTurnWire,
                        schema=skald_wire_lenient_schema(),
                    )
                }
            else:
                kwargs = {}
        elif self._provider_wire_type in {"openai", "local"}:
            kwargs = {"text_format": openai_response_text_format(schema_model)}
        elif self._provider_wire_type == "anthropic":
            kwargs = {"output_config": anthropic_output_config(schema_model)}
        else:
            kwargs = {}

        self._schema_format_cache[schema_model] = kwargs
        return kwargs

    @staticmethod
    def _is_bootstrap_context(context_payload: Optional[Mapping[str, Any]]) -> bool:
        """Return whether a context payload is for the opening bootstrap chunk."""

        if not isinstance(context_payload, Mapping):
            return False
        metadata = context_payload.get("metadata", {})
        metadata_bootstrap = (
            metadata.get("is_bootstrap", False) if isinstance(metadata, dict) else False
        )
        return bool(context_payload.get("is_bootstrap", False) or metadata_bootstrap)

    def _format_context_prompt(self, context: Dict) -> str:
        """Format context payload into a prompt for the Apex AI"""
        sections = []

        # The intertitle anchors Skald's declared time deltas and episode
        # transitions to visible state: without it the model reasons about
        # elapsed time and story position blind, and pacing drifts.
        # Deliberately unlabeled and gloss-free — position (first lines of
        # the prompt) and form carry it; a frontier model needs no
        # "In-world time:" caption on an ISO timestamp, and the WGS84
        # point is the spatial-reasoning offload, not decoration.
        intertitle = context.get("intertitle") or {}
        if intertitle:
            position_bits = []
            if intertitle.get("season") is not None:
                position_bits.append(
                    f"S{int(intertitle['season']):02d}"
                    f"E{int(intertitle.get('episode') or 0):02d}"
                )
            if intertitle.get("scene") is not None:
                position_bits.append(f"Scene {intertitle['scene']}")
            layer = intertitle.get("world_layer")
            if layer and layer != "primary":
                position_bits.append(f"{layer} layer")
            if position_bits:
                sections.append(" - ".join(position_bits))
            if intertitle.get("world_time"):
                sections.append(str(intertitle["world_time"]))
            if intertitle.get("location_name"):
                location_line = str(intertitle["location_name"])
                if intertitle.get("location_geom"):
                    location_line += f" — {intertitle['location_geom']}"
                sections.append(location_line)
            sections.append("")

        scene_conditions = context.get("scene_conditions") or {}
        if scene_conditions:
            sections.append("=== SCENE CONDITIONS ===")
            if "weather" in scene_conditions:
                sections.append(f"Weather: {scene_conditions['weather']}")
            if "time_of_day" in scene_conditions:
                sections.append(f"Time of day: {scene_conditions['time_of_day']}")
            moods = scene_conditions.get("moods") or []
            if moods:
                rendered_moods = ", ".join(
                    f"{entry['name']}: {entry['mood']}" for entry in moods
                )
                sections.append(f"Moods: {rendered_moods}")
            sections.append("")

        # Add warm slice
        if context.get("warm_slice"):
            sections.append("=== RECENT NARRATIVE ===")
            for chunk in context["warm_slice"]["chunks"]:
                chunk_text = chunk.get("text", "")
                if is_retrograde_summary(chunk):
                    sections.append(f"[{_retrieval_source_label(chunk)}] {chunk_text}")
                else:
                    sections.append(chunk_text)

        bootstrap_sections = self._format_bootstrap_context(
            context.get("bootstrap_data")
        )
        if bootstrap_sections:
            sections.extend(bootstrap_sections)

        # Add user input
        sections.append("\n=== USER INPUT ===")
        sections.append(context.get("user_input", ""))

        # Add entity data with hierarchical support
        entity_data = context.get("entity_data", {})
        if entity_data:
            sections.append("\n=== ENTITY DOSSIER ===")

            # Check if using hierarchical structure
            characters = entity_data.get("characters", [])
            is_hierarchical = isinstance(characters, dict) and (
                "baseline" in characters or "featured" in characters
            )

            if is_hierarchical:
                # New hierarchical format
                # Baseline characters (minimal 1-line summaries)
                baseline_chars = characters.get("baseline", [])
                if baseline_chars:
                    sections.append("\nAll Characters (brief status):")
                    for char in baseline_chars:
                        name = char.get("name", "Unknown")
                        location = char.get("current_location", "unknown location")
                        activity = char.get("current_activity", "status unknown")
                        sections.append(f"- {name}: at {location}, {activity}")

                # Featured characters (full details)
                featured_chars = characters.get("featured", [])
                if featured_chars:
                    sections.append("\nFeatured Characters (full details):")
                    for char in featured_chars:
                        name = char.get("name", "Unknown")
                        ref_type = char.get("reference_type", "")
                        summary = char.get("summary", "")
                        sections.append(f"- {name} [{ref_type}]: {summary}")

                        # Add detailed fields if present
                        if char.get("personality"):
                            sections.append(f"  Personality: {char['personality']}")
                        if char.get("emotional_state"):
                            sections.append(
                                f"  Emotional State: {char['emotional_state']}"
                            )

                # Locations (hierarchical)
                locations = entity_data.get("locations", {})
                baseline_locs = locations.get("baseline", [])
                featured_locs = locations.get("featured", [])

                if baseline_locs:
                    sections.append("\nAll Locations (brief):")
                    for loc in baseline_locs:
                        name = loc.get("name", "Unknown")
                        status = loc.get("current_status", "")
                        sections.append(f"- {name}: {status}")

                if featured_locs:
                    sections.append("\nFeatured Locations (full details):")
                    for loc in featured_locs:
                        name = loc.get("name", "Unknown")
                        ref_type = loc.get("reference_type", "")
                        summary = loc.get("summary", "")
                        sections.append(f"- {name} [{ref_type}]: {summary}")

                # Factions (hierarchical)
                factions = entity_data.get("factions", {})
                baseline_factions = factions.get("baseline", [])
                featured_factions = factions.get("featured", [])

                if baseline_factions:
                    sections.append("\nAll Factions (brief):")
                    for faction in baseline_factions:
                        name = faction.get("name", "Unknown")
                        tags = faction.get("orrery_tag_summary") or ""
                        summary = faction.get("summary") or ""
                        detail = tags or summary
                        sections.append(f"- {name}: {detail}")

                if featured_factions:
                    sections.append("\nFeatured Factions (full details):")
                    for faction in featured_factions:
                        name = faction.get("name", "Unknown")
                        summary = faction.get("summary", "")
                        tags = faction.get("orrery_tag_summary") or ""
                        tag_detail = f"Tags: {tags}" if tags else ""
                        detail = " ".join(
                            part for part in (summary, tag_detail) if part
                        )
                        sections.append(f"- {name}: {detail}")
            else:
                # Flat format (backward compatibility)
                if characters:
                    sections.append("\nCharacters:")
                    for char in characters:
                        name = char.get("name", "Unknown")
                        summary = char.get("summary", "")
                        sections.append(f"- {name}: {summary}")

                locations = entity_data.get("locations", [])
                if locations:
                    sections.append("\nLocations:")
                    for loc in locations:
                        name = loc.get("name", "Unknown")
                        summary = loc.get("description", "") or loc.get("summary", "")
                        sections.append(f"- {name}: {summary}")

            # Relationships, events, threats (same for both formats)
            relationships = entity_data.get("relationships", [])
            if relationships:
                sections.append("\nRelationships:")
                for rel in relationships[:5]:  # Limit to top 5
                    char1 = rel.get("character1_name", "Unknown")
                    char2 = rel.get("character2_name", "Unknown")
                    rel_type = rel.get("relationship_type", "unknown")
                    sections.append(f"- {char1} → {char2}: {rel_type}")

            events = entity_data.get("events", [])
            if events:
                sections.append("\nActive Events:")
                for event in events[:5]:  # Limit to top 5
                    name = event.get("name", "Unknown")
                    summary = event.get("summary", "")
                    sections.append(f"- {name}: {summary}")

            threats = entity_data.get("threats", [])
            if threats:
                sections.append("\nActive Threats:")
                for threat in threats[:5]:  # Limit to top 5
                    name = threat.get("name", "Unknown")
                    description = threat.get("description", "")
                    sections.append(f"- {name}: {description}")

        # Add retrieved passages
        if context.get("retrieved_passages"):
            sections.append("\n=== HISTORICAL CONTEXT ===")
            for passage in context["retrieved_passages"]["results"][
                :5
            ]:  # Limit to top 5
                sections.append(
                    f"[{_retrieval_source_label(passage)} | "
                    f"Score: {passage.get('score', 0):.2f}] "
                    f"{passage.get('text', '')}"
                )

        world_knowledge = context.get("world_knowledge") or []
        if world_knowledge:
            sections.append("\n=== WORLD KNOWLEDGE ===")
            for item in world_knowledge:
                if not isinstance(item, dict):
                    continue
                acquisition = item.get("acquisition") or {}
                acquisition_kind = acquisition.get("kind") or "granted"
                if acquisition_kind == "told" and acquisition.get("source_name"):
                    acquisition_kind = f"told by {acquisition['source_name']}"
                qualifiers = [str(acquisition_kind)]
                if item.get("freshly_revealed"):
                    qualifiers.append("freshly revealed")
                character_name = item.get("character_name") or (
                    f"entity {item.get('character_entity_id')}"
                )
                sections.append(
                    f"- {character_name} [{'; '.join(qualifiers)}]: "
                    f"{item.get('summary', '')}"
                )
            if context.get("world_knowledge_truncated"):
                sections.append("(older knowledge omitted)")

        # Render caps shared with the commit-time prompt-exposure log
        # (orrery_prompt_exposures): both sides must slice identically or the
        # recorded "shown set" lies. Model defaults keep a single source when
        # the orrery section is absent.
        from nexus.config.settings_models import OrreryPromptSettings

        _prompt_defaults = OrreryPromptSettings()
        _prompt_cfg = (self.settings.get("orrery") or {}).get("prompt") or {}
        max_rendered_proposals = int(
            _prompt_cfg.get(
                "max_rendered_proposals", _prompt_defaults.max_rendered_proposals
            )
        )
        max_rendered_pressures = int(
            _prompt_cfg.get(
                "max_rendered_pressures", _prompt_defaults.max_rendered_pressures
            )
        )

        imminent_activity = context.get("orrery_imminent_activity") or []
        if imminent_activity:
            sections.append("\n=== ORRERY IMMINENT ACTIVITY ===")
            sections.append(
                "These are current-tick Orrery proposals. If you omit a proposal "
                "from orrery_adjudications, commit will ratify it. You remain "
                "sovereign: use defer to leave pressure unresolved, void when a "
                "proposal is definitively false, and replace when your structured "
                "updates or replacement_state_delta supersede it. A replacement "
                "only emits a world_event if you provide replacement_event_type. "
                "Refer only to proposal_id; do not rely on prose parsing."
            )
            for proposal in imminent_activity[:max_rendered_proposals]:
                if not isinstance(proposal, dict):
                    continue
                proposal_id = proposal.get("proposal_id")
                label = proposal.get("branch_label") or proposal.get("template_id")
                state_delta = proposal.get("state_delta") or {}
                sections.append(f"- {proposal_id} [{label}]: state_delta={state_delta}")

        scene_pressures = context.get("orrery_scene_pressures") or []
        if scene_pressures:
            sections.append("\n=== ORRERY SCENE PRESSURE ===")
            sections.append(
                "These are Storyteller-mediated pressures involving current "
                "on-screen characters. Some may originate from off-screen "
                "actors; some may be present-character need pressure. You may "
                "adapt, delay, ignore, or incorporate them. Do not let Orrery "
                "decide what present characters do."
            )
            for pressure in scene_pressures[:max_rendered_pressures]:
                if not isinstance(pressure, dict):
                    continue
                label = pressure.get("branch_label") or pressure.get("template_id")
                prompt_text = pressure.get("prompt_text") or pressure.get(
                    "pressure_stub", ""
                )
                if prompt_text:
                    sections.append(f"- {label}: {prompt_text}")

        joint_beats = context.get("orrery_joint_beats") or []
        if joint_beats:
            sections.append("\n=== ORRERY JOINT BEATS ===")
            sections.append(
                "These proposal pairs have the same two characters acting "
                "toward each other in this tick. Treat each pair as one "
                "scene if you wish: 'reciprocal' means both chose the same "
                "behavior (a meeting of intent); 'crossed' means their "
                "behaviors differ (tension you may spring). Adjudicate the "
                "underlying proposals by proposal_id as usual."
            )
            for beat in joint_beats[:max_rendered_proposals]:
                if not isinstance(beat, dict):
                    continue
                names = beat.get("entity_names") or {}
                pair = " & ".join(str(name) for name in names.values()) or (
                    f"{beat.get('entity_a')} & {beat.get('entity_b')}"
                )
                sections.append(
                    f"- [{beat.get('kind')}] {pair}: "
                    f"{beat.get('forward_template_id')} <-> "
                    f"{beat.get('reverse_template_id')} "
                    f"({beat.get('forward_proposal_id')} / "
                    f"{beat.get('reverse_proposal_id')})"
                )

        bleed_menu = context.get("orrery_bleed_menu") or []
        if bleed_menu:
            sections.append("\n=== ORRERY AMBIENT PERIPHERALS ===")
            sections.append(
                "These are optional ambient peripherals from off-screen events. "
                "Ignore freely, render subtly, or use them at any density that "
                "fits the current scene. If you use one with an actor name, "
                "include that exact name at least once in the prose. Do not "
                "explain Orrery."
            )
            for item in bleed_menu[:5]:
                channel = item.get("channel") or "ambient"
                summary = item.get("summary") or item.get("template_id")
                actor = item.get("actor_name")
                prefix = f"[{channel}]"
                if actor:
                    prefix = f"{prefix} {actor}:"
                sections.append(f"- {prefix} {summary}")

        # Add author's note (soft out-of-character suggestion, used by regenerate).
        # Placed immediately before INSTRUCTIONS so recency bias gives it the influence
        # a soft nudge needs — entity/historical context above would otherwise bury it.
        note = context.get("note")
        if note:
            sections.append("\n=== AUTHOR'S NOTE ===")
            sections.append(
                "The player is also leaving a soft, out-of-character suggestion "
                "for this generation — treat it as authorial intent, not a hard "
                "constraint. It may "
                "be a tonal nudge, a continuity correction, or an outcome preference:"
            )
            sections.append(note)

        # Add instructions
        sections.append("\n=== INSTRUCTIONS ===")
        sections.append(
            "Continue the narrative based on the provided context and user input."
        )
        sections.append(
            "Maintain consistency with established characters, locations, and plot."
        )

        return "\n".join(sections)

    @staticmethod
    def _format_bootstrap_context(bootstrap_data: Any) -> list[str]:
        """Render new-story wizard output into chunk #1 user prompt context."""

        data = _coerce_mapping(bootstrap_data)
        if not data:
            return []

        sections = [
            "\n=== BOOTSTRAP CONTEXT ===",
            "Use this new-story context to write chunk #1. It is authoritative "
            "for the opening scene.",
        ]

        setting = _coerce_mapping(data.get("setting"))
        setting_lines = _labeled_lines(
            [
                ("World", setting.get("world_name")),
                ("Genre", setting.get("genre")),
                ("Tone", setting.get("tone")),
                ("Themes", setting.get("themes")),
                ("Time Period", setting.get("time_period")),
                ("Technology Level", setting.get("tech_level")),
                ("Magic Exists", setting.get("magic_exists")),
                ("Magic Description", setting.get("magic_description")),
                ("Political Structure", setting.get("political_structure")),
                ("Major Conflict", setting.get("major_conflict")),
                ("Cultural Notes", setting.get("cultural_notes")),
                ("Language Notes", setting.get("language_notes")),
                ("Geographic Scope", setting.get("geographic_scope")),
                ("Diegetic Artifact", setting.get("diegetic_artifact")),
            ]
        )
        if setting_lines:
            sections.extend(["\n## Setting Snapshot", *setting_lines])

        protagonist = _coerce_mapping(data.get("protagonist"))
        protagonist_lines = _labeled_lines(
            [
                ("Name", protagonist.get("name")),
                ("Summary", protagonist.get("summary")),
                ("Appearance", protagonist.get("appearance")),
                ("Background", protagonist.get("background")),
                ("Personality", protagonist.get("personality")),
                ("Emotional State", protagonist.get("emotional_state")),
                ("Current Activity", protagonist.get("current_activity")),
                ("Traits", protagonist.get("traits") or protagonist.get("extra_data")),
            ]
        )
        if protagonist_lines:
            sections.extend(["\n## Protagonist", *protagonist_lines])

        location = _coerce_mapping(data.get("location"))
        location_lines = _labeled_lines(
            [
                ("Name", location.get("name")),
                ("Summary", location.get("summary")),
                ("Current Status", location.get("current_status")),
                ("Atmosphere", location.get("atmosphere")),
                ("History", location.get("history")),
                ("Inhabitants", location.get("inhabitants")),
                ("Resources", location.get("resources")),
                ("Dangers", location.get("dangers")),
                ("Secrets", location.get("secrets")),
            ]
        )
        if location_lines:
            sections.extend(["\n## Starting Location", *location_lines])

        seed = _coerce_mapping(data.get("story_seed"))
        seed_title = _string_value(seed.get("title")) or "Story Seed"
        seed_lines = _labeled_lines(
            [
                ("Seed Type", seed.get("seed_type")),
                ("Situation", seed.get("situation")),
                ("Hook", seed.get("hook")),
                ("Immediate Goal", seed.get("immediate_goal")),
                ("Stakes", seed.get("stakes")),
                ("Tension Source", seed.get("tension_source")),
                ("Weather", seed.get("weather")),
                ("Key NPCs", seed.get("key_npcs")),
            ]
        )
        if seed_lines:
            sections.extend([f"\n## Story Seed: {seed_title}", *seed_lines])
        seed_secrets = _string_value(seed.get("secrets"))
        if seed_secrets:
            sections.extend(
                [
                    "\n### LLM-Internal Secrets",
                    "Use these for dramatic irony and continuity. Do not reveal "
                    "them directly to the player unless the story earns it.",
                    seed_secrets,
                ]
            )

        return sections

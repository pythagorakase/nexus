"""
LOGON Utility - API Communication Handler for LORE

Manages communication with Apex AI providers (OpenAI, Anthropic, xAI).
"""

import asyncio
import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional, Union, cast

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
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
    combine_two_pass,
    hydrate_skald_turn,
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
    skald_wire_lenient_schema,
    skald_wire_prompt_guide,
    skald_wire_strict_text_format,
    skald_writer_lenient_schema,
    skald_writer_strict_text_format,
)
from nexus.agents.lore.utils.chunk_operations import (  # noqa: E402
    calculate_chunk_tokens,
)
from nexus.agents.orrery.tag_library import (  # noqa: E402
    EntityRowReference,
    TagLibraryContext,
    format_contextual_tag_library,
    format_tag_library_for_prompt,
)
from nexus.config.loader import get_provider_for_model, resolve_model_ref  # noqa: E402
from nexus.memory.context_state import is_retrograde_summary  # noqa: E402
from nexus.memory.correspondence import (  # noqa: E402
    CorrespondenceDigestWire,
    GeneratedCorrespondence,
    build_digest_length_validator,
    build_letter_length_validator,
    correspondence_settings,
)
from nexus.memory.manager import (  # noqa: E402
    resolve_storyteller_context_window,
)
from nexus.memory.retrieval_coverage import coerce_chunk_id  # noqa: E402

logger = logging.getLogger("nexus.lore.logon")

# One resolved storyteller/gaia seat: (model id, registry provider name,
# OpenAI-compatible endpoint or None, wire class). Shared by the slot-model
# route and the pinned gaia route so the tuple shape cannot drift.
StorytellerRoute = tuple[
    str,
    str,
    Optional[Dict[str, Any]],
    Literal["openai", "anthropic", "local"],
]

_PROPOSAL_TAG_DELTA_KEYS = frozenset(
    {
        "entity_tags.add",
        "entity_tags.remove",
        "entity_tags_target.add",
        "entity_tags_target.remove",
    }
)
# The remaining closed-vocabulary carriers in SUPPORTED_STATE_DELTA_KEYS are
# pair-tag operations: entity_pair_tags.{add_inbound,add_outbound,
# clear_outbound}, entity_pair_tags_target.clear_inbound, and status.bestow
# (which writes status:<level>). Pair tags have their own name index and no
# single-entity Tier-2 descriptions, so they are intentionally not extracted
# here.


def proposal_tag_names_from_payload(context_payload: Mapping[str, Any]) -> set[str]:
    """Extract single-entity tags referenced by pending Orrery proposals."""

    tag_names: set[str] = set()
    for proposal in context_payload.get("orrery_imminent_activity") or []:
        if not isinstance(proposal, Mapping):
            continue
        state_delta = proposal.get("state_delta") or {}
        if not isinstance(state_delta, Mapping):
            continue
        for key in _PROPOSAL_TAG_DELTA_KEYS:
            values = state_delta.get(key) or []
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, (list, tuple, set)):
                continue
            tag_names.update(
                str(value).strip()
                for value in values
                if value is not None and str(value).strip()
            )
        mood_set = state_delta.get("mood.set")
        if isinstance(mood_set, Mapping):
            mood = mood_set.get("mood")
            if mood is not None and str(mood).strip():
                tag_names.add(str(mood).strip())
    return tag_names


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


def read_user_character_id(dbname: str) -> Optional[int]:
    """Read the configured user character for contextual tag exposure."""

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
                SELECT user_character
                FROM global_variables
                WHERE id = TRUE
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return int(row[0]) if row and row[0] is not None else None


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
        settings_path: Optional[Union[str, Path]] = None,
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
            settings_path: Effective configuration path that owns this LOGON
                stack. Registry lookups remain bound to it when provided.
        """
        self.settings = settings
        self.dbname = dbname
        self.model_override = model_override
        self.bootstrap_mode = bootstrap_mode
        self.settings_path = (
            Path(settings_path).resolve() if settings_path is not None else None
        )
        self.provider: Optional[OpenAIProvider | AnthropicProvider] = None
        self._system_prompt: Optional[str] = None
        self._provider_bootstrap_mode: Optional[bool] = None
        self._provider_wire_type: Optional[Literal["openai", "anthropic", "local"]] = (
            None
        )
        self._provider_type_name: Optional[str] = None
        self._validation_dbname: Optional[str] = None
        # Keyed by schema type for single-pass entries and by
        # (schema type, wire class) tuples for two-pass entries, because the
        # pinned gaia seat can run a different wire class than the writer.
        self._schema_format_cache: Dict[Any, Dict[str, Any]] = {}
        # One setting snapshot per utility instance: both seats of a
        # two-pass turn must compose against the same SettingCard.
        self._setting_context: Optional[str] = None
        self._setting_context_loaded = False
        self._generated_correspondence: Optional[GeneratedCorrespondence] = None

    def _turn_pipeline(self) -> Literal["single_pass", "two_pass"]:
        """Return the validated non-bootstrap storyteller pipeline lever."""

        apex_settings = self.settings.get("API Settings", {}).get("apex")
        if not isinstance(apex_settings, Mapping):
            apex_settings = self.settings.get("apex") or {}
        turn_pipeline = apex_settings.get("turn_pipeline", "single_pass")
        if turn_pipeline not in {"single_pass", "two_pass"}:
            raise ValueError(
                "API Settings.apex.turn_pipeline must be 'single_pass' or 'two_pass'"
            )
        return cast(Literal["single_pass", "two_pass"], turn_pipeline)

    def _load_system_prompt(self, is_bootstrap: Optional[bool] = None) -> str:
        """Load and combine storyteller instructions with live slot context."""

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
        # Core is the writer-scoped Skald document. When one mind holds both
        # chairs on an ongoing turn — single-pass mode — append the
        # state-authorship supplement carrying Gaia's portfolio. Bootstrap
        # never gets it: the bootstrap schema is prose and choices only.
        if not is_bootstrap and self._turn_pipeline() == "single_pass":
            supplement = (prompts_dir / "storyteller_single_pass.md").read_text()
            system_prompt = f"{system_prompt}\n\n---\n\n{supplement}"
            logger.info(
                "Appended single-pass state supplement (%s chars)", len(supplement)
            )
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

        setting_content = self._load_setting_context()
        if setting_content:
            return f"{system_prompt}\n\n{setting_content}"
        return system_prompt

    def _load_setting_context(self) -> Optional[str]:
        """Fetch and render the persisted SettingCard from global_variables.

        The first call performs the read; the snapshot is then cached for
        the instance's lifetime so the writer and gaia seats of a two-pass
        turn always compose against the same setting.
        """

        if self._setting_context_loaded:
            return self._setting_context
        self._setting_context = self._fetch_setting_context()
        self._setting_context_loaded = True
        return self._setting_context

    def _fetch_setting_context(self) -> Optional[str]:
        """Perform the actual SettingCard read behind the snapshot cache."""
        from nexus.api.slot_utils import require_slot_dbname

        try:
            db = require_slot_dbname(dbname=self.dbname)
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
                        return None
                    logger.info(
                        "Loaded setting context (%s chars)", len(setting_content)
                    )
                    return setting_content
                logger.warning(
                    "No setting data found in global_variables, using core "
                    "prompt only"
                )
                return None

        except Exception as e:
            logger.error(f"Failed to load setting from database: {e}")
            return None
        finally:
            if "conn" in locals():
                conn.close()

    @staticmethod
    def _load_gaia_system_prompt() -> str:
        """Load the dedicated gaia instructions without per-turn material."""

        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        gaia_prompt_path = prompts_dir / "storyteller_gaia.md"
        gaia_prompt = gaia_prompt_path.read_text()
        if not gaia_prompt.strip():
            raise ValueError(f"Gaia prompt is empty: {gaia_prompt_path}")
        logger.info("Loaded storyteller Gaia prompt (%s chars)", len(gaia_prompt))
        return gaia_prompt

    @staticmethod
    def _load_writer_pass_note() -> str:
        """Load the writer-pass scope note appended in two-pass mode."""

        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        note_path = prompts_dir / "storyteller_writer_pass.md"
        note = note_path.read_text()
        if not note.strip():
            raise ValueError(f"Writer pass note is empty: {note_path}")
        return note

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
    def _resolve_generation_model(
        model: str, settings_path: Optional[Path] = None
    ) -> str:
        """Resolve a runtime roster reference before constructing the provider."""
        return (
            resolve_model_ref(model, settings_path) if model.startswith("@") else model
        )

    def _resolve_storyteller_route(self) -> StorytellerRoute:
        """Resolve the active model, endpoint, and storyteller wire class."""
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})

        # Model priority: override > slot config > settings
        model = self.model_override
        if not model:
            model = self._get_slot_model()
        if not model:
            model = apex_settings.get("model", "gpt-4o")
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError("LOGON could not resolve a storyteller model id")
        model = self._resolve_generation_model(model, self.settings_path)

        provider_type = get_provider_for_model(
            model, self.settings_path
        ) or apex_settings.get("provider", "openai")

        # OpenAI-compatible base_url routing (mock TEST server, local servers):
        # the endpoint lives in [global.model.api_models] (#401).
        from nexus.config import get_openai_compatible_endpoint

        endpoint = get_openai_compatible_endpoint(model, self.settings_path)
        base_url = endpoint["base_url"] if endpoint else None

        provider_wire_type: Literal["openai", "anthropic", "local"]
        if provider_type == "anthropic":
            provider_wire_type = "anthropic"
        elif provider_type == "openai" or base_url:
            provider_wire_type = "local" if base_url else "openai"
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        return model, provider_type, endpoint, provider_wire_type

    def resolve_provider_wire_type(
        self,
    ) -> Literal["openai", "anthropic", "local"]:
        """Return LOGON's wire classification without constructing a provider."""
        return self._resolve_storyteller_route()[3]

    def resolve_storyteller_route(
        self,
    ) -> tuple[str, Literal["openai", "anthropic", "local"], str]:
        """Return the storyteller model, wire class, and provider name."""
        model, provider_type, _endpoint, provider_wire_type = (
            self._resolve_storyteller_route()
        )
        return model, provider_wire_type, provider_type

    def _initialize_provider(
        self,
        is_bootstrap: Optional[bool] = None,
        *,
        resolved_route: Optional[StorytellerRoute] = None,
    ) -> None:
        """Initialize the appropriate API provider based on settings and slot config."""
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        provider_bootstrap_mode = (
            self.bootstrap_mode if is_bootstrap is None else is_bootstrap
        )

        model, provider_type, endpoint, provider_wire_type = resolved_route or (
            self._resolve_storyteller_route()
        )
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
        use_two_pass = (
            not provider_bootstrap_mode and self._turn_pipeline() == "two_pass"
        )
        anthropic_transport: Literal["native", "prompted", "tool_envelope"] = "native"
        if provider_type == "anthropic":
            configured_transport = apex_settings.get("anthropic_storyteller_transport")
            if configured_transport not in {
                "native",
                "prompted",
                "tool_envelope",
            }:
                raise ValueError(
                    "API Settings.apex.anthropic_storyteller_transport must be "
                    "'native', 'prompted', or 'tool_envelope'"
                )
            anthropic_transport = (
                "native"
                if provider_bootstrap_mode
                else cast(
                    Literal["native", "prompted", "tool_envelope"],
                    configured_transport,
                )
            )
            if anthropic_transport == "prompted" and not use_two_pass:
                system_prompt = f"{system_prompt}\n\n{skald_wire_prompt_guide()}"
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
        tag_library_settings = apex_settings.get("tag_library") or {}
        tag_output_validator = build_storyteller_tag_validator(
            validation_dbname,
            suggestion_limit=int(tag_library_settings.get("suggestion_limit", 3)),
        )
        output_validator = tag_output_validator
        if not provider_bootstrap_mode:
            output_validator = self._build_letter_output_validator(
                delegate=tag_output_validator
            )
        self._validation_dbname = validation_dbname
        self._schema_format_cache = {}

        self._provider_wire_type = provider_wire_type
        self._provider_type_name = provider_type
        if provider_wire_type == "anthropic":
            self.provider = AnthropicProvider(
                model=model,
                max_tokens=apex_settings.get(
                    "max_output_tokens", apex_settings.get("max_tokens", 4000)
                ),
                reasoning_effort=apex_settings.get("reasoning_effort"),
                system_prompt=system_prompt,
                structured_transport=anthropic_transport,
                structured_output_retries=structured_output_retries,
                output_validator=output_validator,
            )
        else:
            # Native OpenAI, or any OpenAI-compatible server registered with a
            # base_url in [global.model.api_models] (mock TEST, Ollama, vLLM).
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
                request_params=endpoint.get("request_params") if endpoint else None,
            )

        logger.info(
            f"LOGON initialized with {provider_type} provider using model {model}"
        )
        logger.info(f"System prompt loaded: {len(system_prompt)} chars")

    def _ensure_provider(
        self,
        context_payload: Optional[Dict[str, Any]] = None,
        *,
        expected_model: Optional[str] = None,
        expected_wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
    ) -> None:
        """Ensure the provider is initialized before use."""
        desired_bootstrap_mode = (
            self._is_bootstrap_context(context_payload)
            if context_payload is not None
            else self.bootstrap_mode
        )

        resolved_route = None
        if (expected_model is None) != (expected_wire_type is None):
            raise RuntimeError(
                "Expected storyteller model and wire class must be supplied together"
            )
        if expected_model is not None and expected_wire_type is not None:
            resolved_route = self._resolve_storyteller_route()
            resolved_model = resolved_route[0]
            resolved_wire_type = resolved_route[3]
            if (
                resolved_model != expected_model
                or resolved_wire_type != expected_wire_type
            ):
                raise RuntimeError(
                    "slot model changed mid-turn; aborting the turn: "
                    f"expected model={expected_model!r}, "
                    f"wire_class={expected_wire_type!r}; "
                    f"found model={resolved_model!r}, "
                    f"wire_class={resolved_wire_type!r}"
                )

        if self.provider is None:
            if resolved_route is None:
                self._initialize_provider(desired_bootstrap_mode)
            else:
                self._initialize_provider(
                    desired_bootstrap_mode,
                    resolved_route=resolved_route,
                )
            return

        if resolved_route is not None:
            active_model: Optional[str] = resolved_route[0]
            active_wire_type: Optional[Literal["openai", "anthropic", "local"]] = (
                resolved_route[3]
            )
        else:
            active_model = self.model_override or self._get_slot_model()
            if active_model:
                active_model = self._resolve_generation_model(active_model)
            active_wire_type = self._provider_wire_type
        model_changed = bool(
            active_model and getattr(self.provider, "model", None) != active_model
        )
        wire_type_changed = self._provider_wire_type != active_wire_type
        bootstrap_changed = self._provider_bootstrap_mode != desired_bootstrap_mode
        if model_changed or wire_type_changed or bootstrap_changed:
            logger.info(
                "LOGON provider context changed. Reinitializing provider for model %s "
                "(bootstrap=%s)",
                active_model or getattr(self.provider, "model", None),
                desired_bootstrap_mode,
            )
            if resolved_route is None:
                self._initialize_provider(desired_bootstrap_mode)
            else:
                self._initialize_provider(
                    desired_bootstrap_mode,
                    resolved_route=resolved_route,
                )

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

    def generate_narrative(
        self,
        context_payload: Dict[str, Any],
        *,
        expected_model: Optional[str] = None,
        expected_wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
        effective_context_window: Optional[int] = None,
    ) -> StoryTurnResponse:
        """Generate narrative from context payload with structured output."""
        self._generated_correspondence = None
        self._ensure_provider(
            context_payload,
            expected_model=expected_model,
            expected_wire_type=expected_wire_type,
        )
        assert self.provider is not None
        schema_model = self._select_response_schema(context_payload)
        presence_baseline = self._read_presence_baseline_for_context(
            context_payload,
            schema_model,
        )
        # Format the context into a prompt
        prompt = self._format_context_prompt(
            context_payload,
            presence_baseline=presence_baseline,
        )
        self._enforce_final_prompt_window(
            prompt,
            effective_context_window=effective_context_window,
        )

        # Get structured completion from provider
        # This returns a tuple of (parsed_object, llm_response)
        try:
            if self._is_two_pass_turn(schema_model):
                response = self._generate_narrative_two_pass(
                    prompt,
                    presence_baseline=presence_baseline,
                    effective_context_window=effective_context_window,
                )
            else:
                schema_kwargs = self._schema_format_kwargs(schema_model)
                parsed_response, _llm_response = (
                    self.provider.get_structured_completion(
                        prompt,
                        schema_model,
                        **schema_kwargs,
                    )
                )
                self._capture_single_pass_correspondence(
                    parsed_response,
                    schema_model=schema_model,
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
            self._generated_correspondence = None
            logger.exception("Failed to get structured response")
            raise

    async def generate_narrative_async(
        self,
        context_payload: Dict[str, Any],
        *,
        expected_model: Optional[str] = None,
        expected_wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
        effective_context_window: Optional[int] = None,
    ) -> StoryTurnResponse:
        """Generate narrative from context payload without blocking the event loop."""
        self._generated_correspondence = None
        self._ensure_provider(
            context_payload,
            expected_model=expected_model,
            expected_wire_type=expected_wire_type,
        )
        assert self.provider is not None
        schema_model = self._select_response_schema(context_payload)
        presence_baseline = await self._read_presence_baseline_for_context_async(
            context_payload,
            schema_model,
        )
        prompt = self._format_context_prompt(
            context_payload,
            presence_baseline=presence_baseline,
        )
        self._enforce_final_prompt_window(
            prompt,
            effective_context_window=effective_context_window,
        )

        try:
            if self._is_two_pass_turn(schema_model):
                response = await self._generate_narrative_two_pass_async(
                    prompt,
                    presence_baseline=presence_baseline,
                    effective_context_window=effective_context_window,
                )
            else:
                schema_kwargs = self._schema_format_kwargs(schema_model)
                parsed_response, _llm_response = (
                    await self.provider.get_structured_completion_async(
                        prompt,
                        schema_model,
                        **schema_kwargs,
                    )
                )
                self._capture_single_pass_correspondence(
                    parsed_response,
                    schema_model=schema_model,
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
            self._generated_correspondence = None
            logger.exception("Failed to get structured response")
            raise

    def take_generated_correspondence(self) -> Optional[GeneratedCorrespondence]:
        """Move the current private output to the turn context exactly once."""

        generated = self._generated_correspondence
        self._generated_correspondence = None
        return generated

    def _capture_single_pass_correspondence(
        self,
        parsed_response: Any,
        *,
        schema_model: type,
    ) -> None:
        """Capture a combined-seat letter without touching the public response."""

        if schema_model is not SkaldTurnWire:
            return
        if not isinstance(parsed_response, SkaldTurnWire):
            raise TypeError("Single-pass correspondence requires SkaldTurnWire")
        if parsed_response.letter is None:
            raise ValueError("Single-pass storyteller response omitted its letter")
        self._generated_correspondence = GeneratedCorrespondence(
            writer_letter=parsed_response.letter,
            gaia_letter=None,
        )

    def _build_letter_output_validator(self, *, delegate: Any = None) -> Any:
        """Bind the configured repairable letter limit to one provider pass."""

        config = correspondence_settings(self.settings)
        return build_letter_length_validator(
            max_letter_tokens=int(config["max_letter_tokens"]),
            delegate=delegate,
        )

    def compact_correspondence(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_digest_tokens: int,
    ) -> str:
        """Run one isolated structured completion with bounded digest repair."""

        self._ensure_provider()
        if self.provider is None:
            raise RuntimeError("Correspondence compaction requires a provider")
        compaction_provider = copy.copy(self.provider)
        compaction_provider.system_prompt = system_prompt
        compaction_provider.output_validator = build_digest_length_validator(
            max_digest_tokens=max_digest_tokens
        )
        if isinstance(compaction_provider, AnthropicProvider):
            # The compact digest schema is intentionally small enough for
            # Anthropic native enforcement even when storyteller turns use
            # prompted/tool-envelope transport.
            compaction_provider.structured_transport = "native"
        parsed, _response = compaction_provider.get_structured_completion(
            user_prompt,
            CorrespondenceDigestWire,
            **self._schema_format_kwargs(CorrespondenceDigestWire),
        )
        if not isinstance(parsed, CorrespondenceDigestWire):
            raise TypeError(
                "Correspondence compaction returned a non-digest wire response"
            )
        return parsed.digest.strip()

    def _is_two_pass_turn(self, schema_model: type) -> bool:
        """Return whether this non-bootstrap turn uses the bakeoff pipeline."""

        return schema_model is SkaldTurnWire and self._turn_pipeline() == "two_pass"

    def _clone_provider_for_two_pass(
        self,
        *,
        system_prompt: Optional[str],
        output_validator: Any,
        anthropic_transport: Optional[
            Literal["native", "prompted", "tool_envelope"]
        ] = None,
    ) -> OpenAIProvider | AnthropicProvider:
        """Create an isolated provider view for one pass."""

        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")
        pass_provider = copy.copy(self.provider)
        pass_provider.system_prompt = system_prompt
        pass_provider.output_validator = output_validator
        if self._provider_wire_type == "anthropic":
            if anthropic_transport is None:
                raise ValueError(
                    "Anthropic two-pass calls require an explicit transport"
                )
            cast(AnthropicProvider, pass_provider).structured_transport = (
                anthropic_transport
            )
        elif anthropic_transport is not None:
            raise ValueError(
                "Anthropic transport cannot be set for a non-Anthropic provider"
            )
        return pass_provider

    def _writer_system_prompt(self) -> str:
        """Return the storyteller system prompt scoped to the writer pass.

        The single-pass core doctrine instructs authoring updates,
        adjudications, and declarations — gaia work. Grammar-enforced
        writers physically cannot overflow into those fields, but schema-free
        writers (OpenRouter passthrough) obey the doctrine over the repair
        loop, so the writer pass must be told its own scope explicitly (live
        failure: Kimi K2.5 at a proposal-bearing beat, #578).
        """

        if self.provider is None:
            raise RuntimeError("Writer prompt requires an initialized provider")
        system_prompt = self._system_prompt
        if system_prompt is None:
            system_prompt = getattr(self.provider, "system_prompt", None)
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise TypeError("Writer system prompt must be a string")
        note = self._load_writer_pass_note()
        if system_prompt is None:
            return note
        return f"{system_prompt}\n\n{note}"

    def _resolve_gaia_route(self) -> Optional[StorytellerRoute]:
        """Resolve the pinned gaia seat, or None to follow the slot model.

        Returns None whenever the gaia should ride the proven clone path:
        no gaia_model configured; the active writer is the TEST mock (TEST
        slots stay self-contained and offline); or the pinned model IS the
        slot model (a fresh provider would be an identical twin).
        """
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        gaia_model = apex_settings.get("gaia_model")
        if not gaia_model:
            return None
        if self._provider_type_name is None:
            raise RuntimeError("Gaia route resolution requires an initialized provider")
        if self._provider_type_name == "test":
            return None
        turn_model = getattr(self.provider, "model", None)
        if turn_model is None:
            raise RuntimeError(
                "Gaia route resolution requires the active provider's model"
            )
        if gaia_model == turn_model:
            return None

        provider_type = get_provider_for_model(gaia_model, self.settings_path)
        if provider_type is None:
            raise ValueError(f"gaia_model {gaia_model!r} is not in the model registry")
        from nexus.config import get_openai_compatible_endpoint

        endpoint = get_openai_compatible_endpoint(gaia_model, self.settings_path)
        base_url = endpoint["base_url"] if endpoint else None
        gaia_wire: Literal["openai", "anthropic", "local"]
        if provider_type == "anthropic":
            gaia_wire = "anthropic"
        elif provider_type == "openai" or base_url:
            gaia_wire = "local" if base_url else "openai"
        else:
            raise ValueError(f"Unsupported gaia provider type: {provider_type}")
        return gaia_model, provider_type, endpoint, gaia_wire

    def _build_gaia_provider(
        self,
        gaia_route: StorytellerRoute,
        *,
        system_prompt: Optional[str],
        output_validator: Any,
        anthropic_transport: Optional[Literal["prompted", "tool_envelope"]],
    ) -> "OpenAIProvider | AnthropicProvider":
        """Construct a fresh provider for the pinned gaia seat.

        Mirrors _initialize_provider's constructor arguments so the gaia
        inherits the same apex generation settings as the writer, differing
        only in model, endpoint, and transport.
        """
        gaia_model, _provider_type, endpoint, gaia_wire = gaia_route
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})
        structured_output_retries = apex_settings.get("structured_output_retries", 3)
        if gaia_wire == "anthropic":
            if anthropic_transport is None:
                raise ValueError("Anthropic gaia seat requires an explicit transport")
            return AnthropicProvider(
                model=gaia_model,
                max_tokens=apex_settings.get(
                    "max_output_tokens", apex_settings.get("max_tokens", 4000)
                ),
                reasoning_effort=apex_settings.get("reasoning_effort"),
                system_prompt=system_prompt,
                structured_transport=anthropic_transport,
                structured_output_retries=structured_output_retries,
                output_validator=output_validator,
            )
        base_url = endpoint["base_url"] if endpoint else None
        api_key = endpoint["api_key"] if endpoint else None
        structured_transport = cast(
            Literal["responses", "chat_completions"],
            endpoint["structured_transport"] if endpoint else "responses",
        )
        request_timeout = endpoint["request_timeout_seconds"] if endpoint else None
        return OpenAIProvider(
            model=gaia_model,
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
            request_params=endpoint.get("request_params") if endpoint else None,
        )

    def _gaia_effective_window(self, gaia_route: StorytellerRoute) -> int:
        """Resolve the pinned gaia provider's own context ceiling.

        The gaia prompt (turn context + finished writer output) must be
        enforced against the GAIA provider's window, not the writer's — a
        32K local writer with a 75K frontier gaia must not false-raise.
        """
        _model, provider_type, _endpoint, gaia_wire = gaia_route
        return resolve_storyteller_context_window(
            self.settings, gaia_wire, provider_type
        )

    def _resolve_anthropic_two_pass_gaia_transport(
        self,
        wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
    ) -> Optional[Literal["prompted", "tool_envelope"]]:
        """Resolve the schema-free Anthropic gaia arm or reject native.

        ``wire_type`` is the GAIA seat's wire class (defaults to the active
        provider's). A non-Anthropic gaia needs no Anthropic transport even
        under an Anthropic writer, and vice versa.
        """

        effective_wire = (
            wire_type if wire_type is not None else self._provider_wire_type
        )
        if effective_wire != "anthropic":
            return None
        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")

        if self._provider_wire_type == "anthropic":
            transport = self.provider.structured_transport
        else:
            # Pinned Anthropic gaia under a non-Anthropic writer: the active
            # provider carries no Anthropic transport, so read the setting.
            apex_settings = self.settings.get("API Settings", {}).get("apex", {})
            transport = apex_settings.get("anthropic_storyteller_transport", "prompted")
        if transport == "native":
            raise ValueError(
                "Anthropic two-pass execution cannot use "
                "anthropic_storyteller_transport='native': the gaia wire cannot "
                "compile under Anthropic native enforcement (probe G2b, issue #566). "
                "Choose 'prompted' or 'tool_envelope' for the gaia."
            )
        if transport not in {"prompted", "tool_envelope"}:
            raise ValueError(
                "Anthropic two-pass gaia transport must be 'prompted' or "
                f"'tool_envelope', got {transport!r}"
            )
        return cast(Literal["prompted", "tool_envelope"], transport)

    def _gaia_system_prompt(
        self,
        *,
        wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
        anthropic_transport: Optional[Literal["prompted", "tool_envelope"]] = None,
    ) -> str:
        """Build the pass-two system content for the gaia seat's wire class."""

        effective_wire = (
            wire_type if wire_type is not None else self._provider_wire_type
        )
        system_prompt = self._load_gaia_system_prompt()
        # Gaia authors canon-adjacent text (update notes, entity summaries)
        # and needs the same setting idiom the writer works in.
        setting_content = self._load_setting_context()
        if setting_content:
            system_prompt = f"{system_prompt}\n\n{setting_content}"
        if effective_wire == "anthropic":
            if anthropic_transport is None:
                raise ValueError(
                    "Anthropic gaia system prompt requires an explicit transport"
                )
            if anthropic_transport == "prompted":
                system_prompt = f"{system_prompt}\n\n{skald_gaia_prompt_guide()}"
        return system_prompt

    @staticmethod
    def _format_gaia_user_prompt(
        turn_prompt: str,
        writer: SkaldWriterWire,
    ) -> str:
        """Append the finished writer output to the stable turn context."""

        scene = (
            writer.scene.model_dump_json(exclude_none=True)
            if writer.scene is not None
            else "null"
        )
        presence = (
            writer.presence.model_dump_json(exclude_none=True)
            if writer.presence is not None
            else "null"
        )
        operations = (
            writer.operations.model_dump_json(exclude_none=True)
            if writer.operations is not None
            else "null"
        )
        choices = "\n\n".join(writer.choices)
        if writer.letter is None:
            raise ValueError("Writer pass omitted its private letter to Gaia")
        return "\n\n".join(
            [
                turn_prompt,
                "=== FINISHED WRITER NARRATIVE (VERBATIM) ===",
                writer.narrative,
                "=== FINISHED WRITER CHOICES (VERBATIM) ===",
                choices,
                "=== FINISHED WRITER SCENE (COMPACT JSON) ===",
                scene,
                "=== FINISHED WRITER PRESENCE (COMPACT JSON) ===",
                presence,
                "=== FINISHED WRITER OPERATIONS (COMPACT JSON) ===",
                operations,
                "=== FINISHED WRITER LETTER (VERBATIM, PRIVATE) ===",
                writer.letter,
            ]
        )

    def _generate_narrative_two_pass(
        self,
        turn_prompt: str,
        *,
        presence_baseline: Optional[PresenceBaseline],
        effective_context_window: Optional[int],
    ) -> StoryTurnResponse:
        """Run synchronous writer and gaia calls, then hydrate once."""

        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")
        gaia_route = self._resolve_gaia_route()
        gaia_wire = (
            gaia_route[3] if gaia_route is not None else self._provider_wire_type
        )
        anthropic_gaia_transport = self._resolve_anthropic_two_pass_gaia_transport(
            gaia_wire
        )
        writer_provider = self._clone_provider_for_two_pass(
            system_prompt=self._writer_system_prompt(),
            output_validator=self._build_letter_output_validator(),
            anthropic_transport=(
                "native" if self._provider_wire_type == "anthropic" else None
            ),
        )
        writer, _writer_response = writer_provider.get_structured_completion(
            turn_prompt,
            SkaldWriterWire,
            **self._two_pass_schema_format_kwargs(SkaldWriterWire),
        )
        if not isinstance(writer, SkaldWriterWire):
            raise TypeError("LOGON writer pass returned a non-SkaldWriterWire response")

        gaia_prompt = self._format_gaia_user_prompt(turn_prompt, writer)
        gaia_window = (
            self._gaia_effective_window(gaia_route)
            if gaia_route is not None
            else effective_context_window
        )
        self._enforce_final_prompt_window(
            gaia_prompt,
            effective_context_window=gaia_window,
        )
        gaia_system_prompt = self._gaia_system_prompt(
            wire_type=gaia_wire,
            anthropic_transport=anthropic_gaia_transport,
        )
        gaia_validator = getattr(self.provider, "output_validator", None)
        if gaia_route is not None:
            gaia_provider: Any = self._build_gaia_provider(
                gaia_route,
                system_prompt=gaia_system_prompt,
                output_validator=gaia_validator,
                anthropic_transport=anthropic_gaia_transport,
            )
        else:
            gaia_provider = self._clone_provider_for_two_pass(
                system_prompt=gaia_system_prompt,
                output_validator=gaia_validator,
                anthropic_transport=anthropic_gaia_transport,
            )
        gaia, _gaia_response = gaia_provider.get_structured_completion(
            gaia_prompt,
            SkaldGaiaWire,
            **self._two_pass_schema_format_kwargs(SkaldGaiaWire, wire_type=gaia_wire),
        )
        if not isinstance(gaia, SkaldGaiaWire):
            raise TypeError("LOGON gaia pass returned a non-SkaldGaiaWire response")
        if writer.letter is None or gaia.letter is None:
            raise ValueError("Two-pass storyteller exchange omitted a private letter")
        self._generated_correspondence = GeneratedCorrespondence(
            writer_letter=writer.letter,
            gaia_letter=gaia.letter,
        )

        return self._hydrate_provider_response(
            combine_two_pass(writer, gaia),
            SkaldTurnWire,
            presence_baseline=presence_baseline,
        )

    async def _generate_narrative_two_pass_async(
        self,
        turn_prompt: str,
        *,
        presence_baseline: Optional[PresenceBaseline],
        effective_context_window: Optional[int],
    ) -> StoryTurnResponse:
        """Run asynchronous writer and gaia calls, then hydrate once."""

        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")
        gaia_route = self._resolve_gaia_route()
        gaia_wire = (
            gaia_route[3] if gaia_route is not None else self._provider_wire_type
        )
        anthropic_gaia_transport = self._resolve_anthropic_two_pass_gaia_transport(
            gaia_wire
        )
        writer_provider = self._clone_provider_for_two_pass(
            system_prompt=self._writer_system_prompt(),
            output_validator=self._build_letter_output_validator(),
            anthropic_transport=(
                "native" if self._provider_wire_type == "anthropic" else None
            ),
        )
        writer, _writer_response = (
            await writer_provider.get_structured_completion_async(
                turn_prompt,
                SkaldWriterWire,
                **self._two_pass_schema_format_kwargs(SkaldWriterWire),
            )
        )
        if not isinstance(writer, SkaldWriterWire):
            raise TypeError("LOGON writer pass returned a non-SkaldWriterWire response")

        gaia_prompt = self._format_gaia_user_prompt(turn_prompt, writer)
        gaia_window = (
            self._gaia_effective_window(gaia_route)
            if gaia_route is not None
            else effective_context_window
        )
        self._enforce_final_prompt_window(
            gaia_prompt,
            effective_context_window=gaia_window,
        )
        gaia_system_prompt = self._gaia_system_prompt(
            wire_type=gaia_wire,
            anthropic_transport=anthropic_gaia_transport,
        )
        gaia_validator = getattr(self.provider, "output_validator", None)
        if gaia_route is not None:
            gaia_provider: Any = self._build_gaia_provider(
                gaia_route,
                system_prompt=gaia_system_prompt,
                output_validator=gaia_validator,
                anthropic_transport=anthropic_gaia_transport,
            )
        else:
            gaia_provider = self._clone_provider_for_two_pass(
                system_prompt=gaia_system_prompt,
                output_validator=gaia_validator,
                anthropic_transport=anthropic_gaia_transport,
            )
        gaia, _gaia_response = await gaia_provider.get_structured_completion_async(
            gaia_prompt,
            SkaldGaiaWire,
            **self._two_pass_schema_format_kwargs(SkaldGaiaWire, wire_type=gaia_wire),
        )
        if not isinstance(gaia, SkaldGaiaWire):
            raise TypeError("LOGON gaia pass returned a non-SkaldGaiaWire response")
        if writer.letter is None or gaia.letter is None:
            raise ValueError("Two-pass storyteller exchange omitted a private letter")
        self._generated_correspondence = GeneratedCorrespondence(
            writer_letter=writer.letter,
            gaia_letter=gaia.letter,
        )

        return self._hydrate_provider_response(
            combine_two_pass(writer, gaia),
            SkaldTurnWire,
            presence_baseline=presence_baseline,
        )

    def _enforce_final_prompt_window(
        self,
        prompt: str,
        *,
        effective_context_window: Optional[int],
    ) -> int:
        """Fail before generation when LOGON formatting exceeds the turn window."""
        provider_wire_type = self._provider_wire_type
        provider_name = self._provider_type_name
        if provider_wire_type is None or provider_name is None:
            raise RuntimeError(
                "Final storyteller prompt sizing requires an active provider "
                "wire class and provider name"
            )
        if effective_context_window is None:
            effective_context_window = resolve_storyteller_context_window(
                self.settings,
                provider_wire_type,
                provider_name,
            )
        if isinstance(effective_context_window, bool) or not isinstance(
            effective_context_window, int
        ):
            raise TypeError("Effective storyteller context window must be an integer")
        if effective_context_window < 1000:
            raise ValueError(
                "Effective storyteller context window must be at least 1000 tokens"
            )

        prompt_tokens = calculate_chunk_tokens(prompt)
        logger.debug(
            "Final storyteller prompt size: wire_class=%s tokens=%s "
            "effective_window=%s",
            provider_wire_type,
            prompt_tokens,
            effective_context_window,
        )
        if prompt_tokens > effective_context_window:
            raise ValueError(
                "Final storyteller prompt exceeds the effective context window: "
                f"wire_class={provider_wire_type!r}, "
                f"prompt_tokens={prompt_tokens}, "
                f"effective_window={effective_context_window}"
            )
        return prompt_tokens

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
        if self.dbname is None:
            # No slot database means a baseline is structurally unavailable
            # (DB-less utilities in tests). Hydration still raises loudly if
            # the response actually carries a presence block.
            return None
        parent_chunk_id = self._parent_chunk_id(context_payload)
        if parent_chunk_id is None:
            raise ValueError(
                "Non-bootstrap narrative context requires metadata.target_chunk_id"
            )
        return read_presence_baseline(self.dbname, parent_chunk_id)

    async def _read_presence_baseline_for_context_async(
        self,
        context_payload: Mapping[str, Any],
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
    ) -> Optional[PresenceBaseline]:
        """Read the parent baseline for an asynchronous extended turn."""

        if schema_model is not SkaldTurnWire:
            return None
        if self.dbname is None:
            # No slot database means a baseline is structurally unavailable
            # (DB-less utilities in tests). Hydration still raises loudly if
            # the response actually carries a presence block.
            return None
        parent_chunk_id = self._parent_chunk_id(context_payload)
        if parent_chunk_id is None:
            raise ValueError(
                "Non-bootstrap narrative context requires metadata.target_chunk_id"
            )
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
                if self.provider is None:
                    raise RuntimeError(
                        "Anthropic schema formatting requires an initialized provider"
                    )
                anthropic_transport = self.provider.structured_transport
                if anthropic_transport == "prompted":
                    kwargs = {}
                elif anthropic_transport == "tool_envelope":
                    kwargs = {"input_schema": skald_wire_lenient_schema()}
                elif anthropic_transport == "native":
                    kwargs = {
                        "output_config": anthropic_output_config(
                            SkaldTurnWire,
                            schema=skald_wire_lenient_schema(),
                        )
                    }
                else:
                    raise ValueError(
                        "Anthropic provider has an invalid structured transport: "
                        f"{anthropic_transport!r}"
                    )
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

    def _two_pass_schema_format_kwargs(
        self,
        schema_model: type,
        *,
        wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
    ) -> Dict[str, Any]:
        """Return the frozen transport schema arguments for one pass.

        ``wire_type`` is the wire class of the provider EXECUTING the pass —
        the pinned gaia seat may run a different class than the writer.
        """

        if schema_model not in {SkaldWriterWire, SkaldGaiaWire}:
            raise TypeError("Two-pass schema formatting requires writer or gaia wire")
        effective_wire = (
            wire_type if wire_type is not None else self._provider_wire_type
        )
        if effective_wire is None:
            raise RuntimeError(
                "Two-pass schema formatting requires an active provider wire class"
            )
        cache_key = (schema_model, effective_wire)
        if cache_key in self._schema_format_cache:
            return self._schema_format_cache[cache_key]

        from nexus.api.native_structured_output import (
            anthropic_output_config,
            openai_response_text_format,
        )

        kwargs: Dict[str, Any]
        if effective_wire == "openai":
            kwargs = {
                "text_format": (
                    skald_writer_strict_text_format()
                    if schema_model is SkaldWriterWire
                    else skald_gaia_strict_text_format()
                )
            }
        elif effective_wire == "local":
            lenient_schema = (
                skald_writer_lenient_schema()
                if schema_model is SkaldWriterWire
                else skald_gaia_lenient_schema()
            )
            kwargs = {
                "text_format": openai_response_text_format(
                    schema_model,
                    schema=lenient_schema,
                )
            }
        elif effective_wire == "anthropic":
            if schema_model is SkaldWriterWire:
                kwargs = {
                    "output_config": anthropic_output_config(
                        SkaldWriterWire,
                        schema=skald_writer_lenient_schema(),
                    )
                }
            else:
                gaia_transport = self._resolve_anthropic_two_pass_gaia_transport(
                    effective_wire
                )
                if gaia_transport == "prompted":
                    kwargs = {}
                elif gaia_transport == "tool_envelope":
                    kwargs = {"input_schema": skald_gaia_lenient_schema()}
                else:
                    raise AssertionError(
                        "Anthropic gaia transport resolution returned no transport"
                    )
        else:
            raise ValueError(
                "Unsupported two-pass provider wire class: " f"{effective_wire!r}"
            )

        self._schema_format_cache[cache_key] = kwargs
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

    def _format_context_prompt(
        self,
        context: Dict,
        *,
        presence_baseline: Optional[PresenceBaseline] = None,
    ) -> str:
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

        correspondence = context.get("storyteller_correspondence")
        if correspondence is not None:
            if not isinstance(correspondence, str) or not correspondence.strip():
                raise ValueError(
                    "storyteller_correspondence must be a nonempty rendered block"
                )
            sections.extend([correspondence, ""])

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

        tag_library = self._format_turn_tag_library(
            context,
            presence_baseline=presence_baseline,
        )
        if tag_library:
            sections.extend(["\n=== ORRERY TAG LIBRARY ===", tag_library])

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

    def _format_turn_tag_library(
        self,
        context: Mapping[str, Any],
        *,
        presence_baseline: Optional[PresenceBaseline],
    ) -> str:
        """Render the bootstrap or scene-contextual tag library for one turn."""

        if self.dbname is None:
            return ""
        if self._is_bootstrap_context(context):
            return format_tag_library_for_prompt(self.dbname)

        from nexus.config.settings_models import APEXTagLibrarySettings

        defaults = APEXTagLibrarySettings()
        apex_settings = self.settings.get("API Settings", {}).get("apex")
        if not isinstance(apex_settings, Mapping):
            apex_settings = self.settings.get("apex") or {}
        raw_settings = apex_settings.get("tag_library") or {}
        contextual = bool(raw_settings.get("contextual", defaults.contextual))
        if not contextual:
            return format_tag_library_for_prompt(self.dbname)

        baseline = presence_baseline
        if baseline is None:
            baseline = self._read_presence_baseline_for_context(
                context,
                SkaldTurnWire,
            )
        if baseline is None:
            raise RuntimeError(
                "Contextual Orrery tag library requires a presence baseline"
            )

        entity_refs = [
            EntityRowReference(kind=reference.kind, row_id=reference.id)
            for reference in baseline.present
            if reference.id is not None
        ]
        if baseline.setting is not None and baseline.setting.id is not None:
            entity_refs.append(
                EntityRowReference(
                    kind=baseline.setting.kind,
                    row_id=baseline.setting.id,
                )
            )
        user_character_id = read_user_character_id(self.dbname)
        if user_character_id is not None:
            entity_refs.append(
                EntityRowReference(
                    kind="character",
                    row_id=user_character_id,
                )
            )

        imminent_activity = context.get("orrery_imminent_activity") or []
        return format_contextual_tag_library(
            self.dbname,
            context=TagLibraryContext(
                present_entity_refs=list(dict.fromkeys(entity_refs)),
                proposal_tag_names=proposal_tag_names_from_payload(context),
                has_pending_proposals=bool(imminent_activity),
                anchor_chunk_id=self._parent_chunk_id(context),
            ),
        )

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

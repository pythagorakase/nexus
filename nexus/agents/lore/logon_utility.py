"""
LOGON Utility - API Communication Handler for LORE

Manages communication with Apex AI providers (OpenAI, Anthropic, xAI).
"""

from nexus.database import connection_kwargs

import asyncio
import copy
from datetime import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Literal, Mapping, Optional, Union, cast

import psycopg2

if TYPE_CHECKING:
    from nexus.config.seat_window import SeatWindow
    from nexus.config.settings_models import APIModelEntry
    from nexus.telemetry.prompt_window import AssemblyRequest, LocalRequestCounter

from nexus.agents.logon.apex_schema import (  # noqa: E402
    StoryTurnResponse,
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.gaia_registry_schema import (  # noqa: E402
    GaiaRegistryReadError,
    coerce_gaia_registry_wire,
    gaia_wire_registry_digest,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (  # noqa: E402
    CharacterRef,
    PlaceRef,
    PresenceBaseline,
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
from nexus.agents.orrery.player_identity import (  # noqa: E402
    canonical_player_character_id,
)
from nexus.agents.orrery.tag_library import (  # noqa: E402
    EntityRowReference,
    TagLibraryContext,
    format_contextual_tag_library,
    format_tag_library_for_prompt,
)
from nexus.api.native_structured_output import (  # noqa: E402
    structured_output_error_text,
)
from nexus.api.presence_reconciliation import (  # noqa: E402
    CharacterRosterRows,
    read_character_roster,
    read_character_roster_async,
    reconcile_prose_mentions,
)
from nexus.config.loader import get_provider_for_model  # noqa: E402
from nexus.config.settings_models import (  # noqa: E402
    APEXTagLibrarySettings,
    OrreryRetrogradeMaturationSettings,
    RenderLimits,
)
from nexus.config.story_model import StorySettings, read_story_settings
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
from nexus.agents.orrery.cards import (
    card_key,
    proposal_handles,
    rendered_selection,
    snapshot_from_context,
)
from nexus.util.clock_face import clock_face
from nexus.prompts.registry import PromptId, load

# Add scripts directory to path for API imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from scripts.api_openai import OpenAIProvider  # noqa: E402
from scripts.api_anthropic import AnthropicProvider  # noqa: E402

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


def _prompt_one_line(value: Any) -> str:
    """Collapse a prompt data value to one whitespace-normalized line."""

    return " ".join(str(value).split())


def _orrery_card_identity(card: Mapping[str, Any]) -> str:
    """Render the actor and counterpart with only known, distinct places."""
    names = card.get("binding_names") or {}
    actor = _prompt_one_line(names.get("actor", ""))
    place = names.get("place")
    if place and place != "unknown":
        actor += f" at {_prompt_one_line(place)}"
    target = names.get("target") or names.get("counterpart") or names.get("faction")
    if target:
        actor += f" → {_prompt_one_line(target)}"
        target_place = names.get("target_place")
        if target_place and target_place != "unknown" and target_place != place:
            actor += f" at {_prompt_one_line(target_place)}"
    return actor


def _orrery_card_line(
    card: Mapping[str, Any],
    handle: str,
    *,
    position: int,
    description: str,
    earlier_turn: bool = False,
) -> str:
    """Render one compact named card; durable identity stays in the snapshot."""
    line = f"- [{position}] {handle} {_orrery_card_identity(card)}: {_prompt_one_line(description)}"
    if earlier_turn and card.get("evaluated_at"):
        line += f" · evaluated {clock_face(card['evaluated_at'])}"
    return line


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


def _proposal_bindings_from_payload(
    context_payload: Mapping[str, Any],
) -> Dict[str, Mapping[str, Any]]:
    """Index current Orrery bindings by the proposal id exposed to Gaia."""

    indexed: Dict[str, Mapping[str, Any]] = {}
    for proposal in context_payload.get("orrery_imminent_activity") or []:
        if not isinstance(proposal, Mapping):
            continue
        proposal_id = proposal.get("proposal_id")
        bindings = proposal.get("bindings")
        if not isinstance(proposal_id, str) or not proposal_id:
            continue
        if not isinstance(bindings, Mapping):
            bindings = {}
        normalized = {
            str(getattr(key, "value", key)): value for key, value in bindings.items()
        }
        if proposal_id in indexed:
            raise ValueError(
                f"Duplicate Orrery proposal_id in generation context: {proposal_id!r}"
            )
        indexed[proposal_id] = normalized
    selection = rendered_selection(snapshot_from_context(context_payload))
    for key, handle in proposal_handles(selection).items():
        if key in indexed:
            indexed[handle] = indexed[key]
    return indexed


def read_presence_baseline(
    dbname: str,
    parent_chunk_id: int,
) -> PresenceBaseline:
    """Read one parent chunk's character roster and setting place."""

    conn = psycopg2.connect(**connection_kwargs(dbname))
    try:
        conn.set_session(readonly=True, autocommit=True)
        from nexus.presence.roster import continuation_setting, read_roster

        roster = read_roster(conn, parent_chunk_id)
        setting = continuation_setting(roster, parent_chunk_id)
        from nexus.agents.orrery.player_identity import canonical_player_character_id

        with conn.cursor() as cur:
            player_id = canonical_player_character_id(cur)
        return PresenceBaseline(
            player_character_id=player_id,
            present=[
                CharacterRef(kind="character", id=entry.id, name=entry.name)
                for entry in roster.present.values()
            ],
            setting=PlaceRef(kind="place", id=setting.id, name=setting.name),
        )
    finally:
        conn.close()


def read_user_character_id(dbname: str) -> int:
    """Read the configured user character for contextual tag exposure."""

    conn = psycopg2.connect(**connection_kwargs(dbname))
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            return canonical_player_character_id(cur)
    finally:
        conn.close()


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
        story_settings: StorySettings | None = None,
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
            story_settings: Optional explicit story snapshot for already-resolved callers.
                When omitted, model resolution reads the live slot.
            settings_path: Effective configuration path that owns this LOGON
                stack. Registry lookups remain bound to it when provided.
        """
        self.settings = settings
        self.story_settings = story_settings
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
        # Keyed by schema type for single-pass entries and by schema, wire, and
        # slot-qualified cache affinity for two-pass entries, because gaia can
        # run a different wire and cache affinity must never cross save slots.
        self._schema_format_cache: Dict[Any, Dict[str, Any]] = {}
        # Current prompt proposal bindings are read by the generation-time
        # replacement-delta validator. They are replaced atomically per turn.
        self._active_orrery_proposal_bindings: Dict[str, Mapping[str, Any]] = {}
        # Dynamic parent anchor consumed by the reusable provider validator.
        # This must change per generation; capturing it at provider construction
        # would use a stale clock on the next turn.
        self._active_anchor_chunk_id: Optional[int] = None
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

    def _tag_library_settings(self) -> APEXTagLibrarySettings:
        """Return validated prompt and strict-schema vocabulary controls."""

        apex_settings = self.settings.get("API Settings", {}).get("apex")
        if not isinstance(apex_settings, Mapping):
            apex_settings = self.settings.get("apex") or {}
        raw_settings = apex_settings.get("tag_library") or {}
        return APEXTagLibrarySettings.model_validate(raw_settings)

    def _load_system_prompt(self, is_bootstrap: Optional[bool] = None) -> str:
        """Load storyteller instructions in their original composition order."""
        is_bootstrap = self.bootstrap_mode if is_bootstrap is None else is_bootstrap
        system_prompt = load(PromptId.STORYTELLER_CORE)
        if not is_bootstrap and self._turn_pipeline() == "single_pass":
            supplement = load(PromptId.STORYTELLER_SINGLE_PASS)
            system_prompt = f"{system_prompt}\n\n---\n\n{supplement}"
        if is_bootstrap:
            bootstrap_content = load(PromptId.STORYTELLER_BOOTSTRAP)
            system_prompt = f"{system_prompt}\n\n---\n\n{bootstrap_content}"
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
        from nexus.api.db_pool import get_connection

        with get_connection(dbname=self.dbname) as conn, conn.cursor() as cur:
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
            logger.info("Loaded setting context (%s chars)", len(setting_content))
            return setting_content
        logger.warning(
            "No setting data found in global_variables, using core prompt only"
        )
        return None

    @staticmethod
    def _load_gaia_system_prompt(max_letter_tokens: int) -> str:
        """Load the seat document with its configured letter budget."""
        return load(PromptId.STORYTELLER_GAIA, MAX_LETTER_TOKENS=int(max_letter_tokens))

    @staticmethod
    def _load_writer_pass_note(max_letter_tokens: int) -> str:
        """Load the seat document with its configured letter budget."""
        return load(
            PromptId.STORYTELLER_WRITER_PASS, MAX_LETTER_TOKENS=int(max_letter_tokens)
        )

    @staticmethod
    def _load_ambient_scene_instruction() -> str:
        """Load the ambient-scene instruction."""
        return load(PromptId.AMBIENT_SCENE_SEEDS).strip()

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

    def _read_story_settings(self) -> StorySettings:
        """Use an explicit snapshot, or read the live slot through the shared pool."""
        from nexus.api.slot_utils import require_slot_dbname

        if self.story_settings is not None:
            return self.story_settings
        return read_story_settings(require_slot_dbname(dbname=self.dbname))

    def _get_slot_model(self) -> Optional[str]:
        """Return the current story's Skald pin without swallowing read errors."""
        return self._read_story_settings().skald_model

    @staticmethod
    def _resolve_generation_model(
        model: str, settings_path: Optional[Path] = None
    ) -> str:
        """Require concrete model IDs for runtime selections and overrides."""
        if model.startswith("@"):
            raise ValueError("Model aliases are no longer supported; select a model ID")
        return model

    def _resolve_storyteller_route(self) -> StorytellerRoute:
        """Resolve the active model, endpoint, and storyteller wire class."""
        apex_settings = self.settings.get("API Settings", {}).get("apex", {})

        from nexus.config import load_settings
        from nexus.config.story_model import StorySettings, resolve_story_model

        model = resolve_story_model(
            "skald",
            settings=load_settings(self.settings_path),
            story=(
                StorySettings(skald_model=self._get_slot_model())
                if self.model_override is None
                else None
            ),
            override=self.model_override,
        )
        provider_type = get_provider_for_model(model, self.settings_path)
        if provider_type is None:
            raise ValueError(f"Model {model!r} is absent from the registry")

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

        # Generation-time registry validation for Skald's durable fields:
        # invalid Orrery vocabulary and unresolved faction update identities
        # become a ModelRetry while the model still owns the turn, instead of
        # a dead commit later (M9 gate finding and issue #634).
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
        maturation_settings = OrreryRetrogradeMaturationSettings.model_validate(
            (
                ((self.settings.get("orrery") or {}).get("retrograde") or {}).get(
                    "maturation"
                )
            )
            or {}
        )
        tag_output_validator = build_storyteller_tag_validator(
            validation_dbname,
            suggestion_limit=int(tag_library_settings.get("suggestion_limit", 3)),
            allow_same_turn_faction_declarations=maturation_settings.enabled,
            proposal_bindings_provider=(lambda: self._active_orrery_proposal_bindings),
            anchor_chunk_id_provider=lambda: self._active_anchor_chunk_id,
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
                usage_provider_name=provider_type,
                usage_seat="skald_single_pass",
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
                usage_provider_name=provider_type,
                usage_seat="skald_single_pass",
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
        self._active_orrery_proposal_bindings = _proposal_bindings_from_payload(
            context_payload
        )
        self._active_anchor_chunk_id = self._parent_chunk_id(context_payload)
        self._window_payload = context_payload
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
        character_roster = self._read_character_roster_for_schema(schema_model)
        # Format the context into a prompt
        prompt = self._format_context_prompt(
            context_payload,
            presence_baseline=presence_baseline,
        )
        self._writer_window_blocks = list(self._last_rendered_blocks)

        # Get structured completion from provider
        # This returns a tuple of (parsed_object, llm_response)
        try:
            if self._is_two_pass_turn(schema_model):
                gaia_turn_prompt = self._format_context_prompt(
                    context_payload,
                    presence_baseline=presence_baseline,
                    include_ambient_scene_seeds=False,
                    seat="gaia",
                )
                self._gaia_window_blocks = list(self._last_rendered_blocks)
                response = self._generate_narrative_two_pass(
                    prompt,
                    gaia_turn_prompt=gaia_turn_prompt,
                    presence_baseline=presence_baseline,
                    character_roster=character_roster,
                    effective_context_window=effective_context_window,
                )
            else:
                self._attach_prompt_window_guard(
                    self.provider,
                    prompt,
                    seat="skald_single_pass",
                    window=effective_context_window,
                )
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
                    character_roster=character_roster,
                )
            logger.debug(
                "Received structured response with narrative length: %s",
                len(response.narrative),
            )
            return self._stamp_generation_model(response)
        except Exception as exc:
            self._generated_correspondence = None
            logger.error(
                "Failed to get structured response: exception=%s error=%s",
                type(exc).__name__,
                structured_output_error_text(exc),
            )
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
        self._active_orrery_proposal_bindings = _proposal_bindings_from_payload(
            context_payload
        )
        self._active_anchor_chunk_id = self._parent_chunk_id(context_payload)
        self._window_payload = context_payload
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
        character_roster = await self._read_character_roster_for_schema_async(
            schema_model
        )
        prompt = self._format_context_prompt(
            context_payload,
            presence_baseline=presence_baseline,
        )
        self._writer_window_blocks = list(self._last_rendered_blocks)

        try:
            if self._is_two_pass_turn(schema_model):
                gaia_turn_prompt = self._format_context_prompt(
                    context_payload,
                    presence_baseline=presence_baseline,
                    include_ambient_scene_seeds=False,
                    seat="gaia",
                )
                self._gaia_window_blocks = list(self._last_rendered_blocks)
                response = await self._generate_narrative_two_pass_async(
                    prompt,
                    gaia_turn_prompt=gaia_turn_prompt,
                    presence_baseline=presence_baseline,
                    character_roster=character_roster,
                    effective_context_window=effective_context_window,
                )
            else:
                self._attach_prompt_window_guard(
                    self.provider,
                    prompt,
                    seat="skald_single_pass",
                    window=effective_context_window,
                )
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
                    character_roster=character_roster,
                )
            logger.debug(
                "Received structured response with narrative length: %s",
                len(response.narrative),
            )
            return self._stamp_generation_model(response)
        except Exception as exc:
            self._generated_correspondence = None
            logger.error(
                "Failed to get structured response: exception=%s error=%s",
                type(exc).__name__,
                structured_output_error_text(exc),
            )
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
        digest_hard_cap_multiplier: float,
    ) -> str:
        """Run one isolated structured completion with bounded digest repair."""

        self._ensure_provider()
        if self.provider is None:
            raise RuntimeError("Correspondence compaction requires a provider")
        compaction_provider = copy.copy(self.provider)
        compaction_provider.system_prompt = system_prompt
        compaction_provider.usage_seat = "correspondence_compaction"
        compaction_provider.output_validator = build_digest_length_validator(
            max_digest_tokens=max_digest_tokens,
            digest_hard_cap_multiplier=digest_hard_cap_multiplier,
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
        usage_seat: str,
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
        pass_provider.usage_seat = usage_seat
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
        config = correspondence_settings(self.settings)
        note = self._load_writer_pass_note(
            max_letter_tokens=int(config["max_letter_tokens"])
        )
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
        from nexus.api.slot_utils import require_slot_dbname
        from nexus.config import load_settings
        from nexus.config.story_model import read_story_settings, resolve_story_model

        story = self._read_story_settings()
        # A null pin follows the actual writer, including a request override.
        gaia_model = resolve_story_model(
            "gaia",
            settings=load_settings(self.settings_path),
            story=story,
            override=(
                getattr(self.provider, "model", None)
                if story.gaia_model is None
                else None
            ),
        )
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
        gaia_model, provider_type, endpoint, gaia_wire = gaia_route
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
                usage_provider_name=provider_type,
                usage_seat="gaia",
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
            usage_provider_name=provider_type,
            usage_seat="gaia",
        )

    def _gaia_effective_window(self, gaia_route: StorytellerRoute) -> int:
        """Resolve the pinned gaia provider's own context ceiling.

        The gaia prompt (turn context + finished writer output) must be
        enforced against the GAIA provider's window, not the writer's — a
        32K local writer with a 75K frontier gaia must not false-raise.
        """
        from nexus.config.story_model import story_context_settings

        _model, provider_type, _endpoint, gaia_wire = gaia_route
        settings = story_context_settings(self.settings, self._read_story_settings())
        return resolve_storyteller_context_window(settings, gaia_wire, provider_type)

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
        config = correspondence_settings(self.settings)
        system_prompt = self._load_gaia_system_prompt(
            max_letter_tokens=int(config["max_letter_tokens"])
        )
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
        gaia_turn_prompt: str,
        presence_baseline: Optional[PresenceBaseline],
        character_roster: Optional[CharacterRosterRows],
        effective_context_window: Optional[int],
    ) -> StoryTurnResponse:
        """Run synchronous writer and gaia calls, then hydrate once."""

        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")
        gaia_route = self._resolve_gaia_route()
        gaia_wire = (
            gaia_route[3] if gaia_route is not None else self._provider_wire_type
        )
        if gaia_wire is None:
            raise RuntimeError("Two-pass Gaia generation requires a provider wire")
        anthropic_gaia_transport = self._resolve_anthropic_two_pass_gaia_transport(
            gaia_wire
        )
        writer_provider = self._clone_provider_for_two_pass(
            system_prompt=self._writer_system_prompt(),
            output_validator=self._build_letter_output_validator(),
            usage_seat="skald_writer",
            anthropic_transport=(
                "native" if self._provider_wire_type == "anthropic" else None
            ),
        )
        self._attach_prompt_window_guard(
            writer_provider,
            turn_prompt,
            seat="skald_writer",
            window=effective_context_window,
        )
        writer, _writer_response = writer_provider.get_structured_completion(
            turn_prompt,
            SkaldWriterWire,
            **self._two_pass_schema_format_kwargs(SkaldWriterWire),
        )
        if not isinstance(writer, SkaldWriterWire):
            raise TypeError("LOGON writer pass returned a non-SkaldWriterWire response")

        gaia_prompt = self._format_gaia_user_prompt(gaia_turn_prompt, writer)
        gaia_window = (
            self._gaia_effective_window(gaia_route)
            if gaia_route is not None
            else effective_context_window
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
                usage_seat="gaia",
                anthropic_transport=anthropic_gaia_transport,
            )
        self._attach_prompt_window_guard(
            gaia_provider, gaia_prompt, seat="gaia", window=gaia_window
        )
        gaia_schema_model = self._gaia_schema_model(gaia_wire)
        gaia, _gaia_response = gaia_provider.get_structured_completion(
            gaia_prompt,
            gaia_schema_model,
            **self._two_pass_schema_format_kwargs(
                gaia_schema_model,
                wire_type=gaia_wire,
            ),
        )
        if not isinstance(gaia, SkaldGaiaWire):
            raise TypeError("LOGON gaia pass returned a non-SkaldGaiaWire response")
        gaia = coerce_gaia_registry_wire(gaia)
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
            character_roster=character_roster,
        )

    async def _generate_narrative_two_pass_async(
        self,
        turn_prompt: str,
        *,
        gaia_turn_prompt: str,
        presence_baseline: Optional[PresenceBaseline],
        character_roster: Optional[CharacterRosterRows],
        effective_context_window: Optional[int],
    ) -> StoryTurnResponse:
        """Run asynchronous writer and gaia calls, then hydrate once."""

        if self.provider is None:
            raise RuntimeError("Two-pass generation requires an initialized provider")
        gaia_route = self._resolve_gaia_route()
        gaia_wire = (
            gaia_route[3] if gaia_route is not None else self._provider_wire_type
        )
        if gaia_wire is None:
            raise RuntimeError("Two-pass Gaia generation requires a provider wire")
        anthropic_gaia_transport = self._resolve_anthropic_two_pass_gaia_transport(
            gaia_wire
        )
        writer_provider = self._clone_provider_for_two_pass(
            system_prompt=self._writer_system_prompt(),
            output_validator=self._build_letter_output_validator(),
            usage_seat="skald_writer",
            anthropic_transport=(
                "native" if self._provider_wire_type == "anthropic" else None
            ),
        )
        self._attach_prompt_window_guard(
            writer_provider,
            turn_prompt,
            seat="skald_writer",
            window=effective_context_window,
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

        gaia_prompt = self._format_gaia_user_prompt(gaia_turn_prompt, writer)
        gaia_window = (
            self._gaia_effective_window(gaia_route)
            if gaia_route is not None
            else effective_context_window
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
                usage_seat="gaia",
                anthropic_transport=anthropic_gaia_transport,
            )
        self._attach_prompt_window_guard(
            gaia_provider, gaia_prompt, seat="gaia", window=gaia_window
        )
        gaia_schema_model = self._gaia_schema_model(gaia_wire)
        gaia, _gaia_response = await gaia_provider.get_structured_completion_async(
            gaia_prompt,
            gaia_schema_model,
            **self._two_pass_schema_format_kwargs(
                gaia_schema_model,
                wire_type=gaia_wire,
            ),
        )
        if not isinstance(gaia, SkaldGaiaWire):
            raise TypeError("LOGON gaia pass returned a non-SkaldGaiaWire response")
        gaia = coerce_gaia_registry_wire(gaia)
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
            character_roster=character_roster,
        )

    def _local_window_counter(
        self, provider: Any, **kwargs: Any
    ) -> tuple["LocalRequestCounter", "APIModelEntry"]:
        """Reuse one declared local tokenizer cache for all blocks in this turn."""
        from nexus.config.settings_models import APIModelEntry
        from nexus.telemetry.prompt_window import (
            local_text_counter,
            local_request_counter,
        )

        entry = next(
            APIModelEntry.model_validate(entry)
            for provider_settings in self.settings["global"]["model"][
                "api_models"
            ].values()
            for entry in provider_settings["models"]
            if entry["id"] == provider.model
        )
        if not hasattr(self, "_window_text_counters"):
            self._window_text_counters = {}
        key = (entry.tokenizer_encoding, entry.tokenizer_repository)
        if key not in self._window_text_counters:
            self._window_text_counters[key] = local_text_counter(entry)
        return (
            local_request_counter(
                provider, entry, self._window_text_counters[key], **kwargs
            ),
            entry,
        )

    def _measure_assembly_request(
        self,
        provider: Any,
        prompt: str,
        blocks: list[tuple[str, str]],
        sources: dict[int, int],
        schema: type,
        format_kwargs: Dict[str, Any],
        *,
        seat: str,
        window: int,
    ) -> "AssemblyRequest":
        """Count each block locally, including the seat's system and schema."""
        from nexus.config.seat_window import resolve_seat_window
        from nexus.telemetry.prompt_window import AssemblyRequest

        anthropic_request = None
        if provider.usage_provider_name == "anthropic":
            if provider.structured_transport == "native":
                anthropic_request = provider._build_native_structured_request_params(
                    prompt, schema, **format_kwargs
                )
            elif provider.structured_transport == "tool_envelope":
                anthropic_request = (
                    provider._build_tool_envelope_structured_request_params(
                        prompt, schema, **format_kwargs
                    )
                )
            else:
                anthropic_request = provider._build_prompted_structured_request_params(
                    prompt
                )
        count, entry = self._local_window_counter(
            provider,
            text_format=format_kwargs.get("text_format"),
            anthropic_request=anthropic_request,
        )
        budget = resolve_seat_window(
            self.settings, provider.model, seat=seat, window=window
        )
        return AssemblyRequest(
            budget, blocks, sources, count, entry.token_count_safety_margin
        )

    def measure_turn_requests(
        self, payload: Dict[str, Any], window: int
    ) -> list["AssemblyRequest"]:
        """Render both seats once, reserving the full writer allowance for Gaia."""
        self._window_text_counters = {}
        self._active_orrery_proposal_bindings = _proposal_bindings_from_payload(payload)
        self._active_anchor_chunk_id = self._parent_chunk_id(payload)
        self._ensure_provider(payload)
        schema = self._select_response_schema(payload)
        presence = self._read_presence_baseline_for_context(payload, schema)
        prompt = self._format_context_prompt(payload, presence_baseline=presence)
        blocks = self._last_rendered_blocks
        sources = self._last_rendered_block_sources
        provider = copy.copy(self.provider)
        two_pass = self._is_two_pass_turn(schema)
        if two_pass:
            provider.system_prompt = self._writer_system_prompt()
            if provider.usage_provider_name == "anthropic":
                provider.structured_transport = "native"
        writer = self._measure_assembly_request(
            provider,
            prompt,
            blocks,
            sources,
            SkaldWriterWire if two_pass else schema,
            (
                self._two_pass_schema_format_kwargs(SkaldWriterWire)
                if two_pass
                else self._schema_format_kwargs(schema)
            ),
            seat="skald_writer",
            window=window,
        )
        if not two_pass:
            return [writer]
        gaia_route = self._resolve_gaia_route()
        gaia_wire = (
            gaia_route[3] if gaia_route is not None else self._provider_wire_type
        )
        transport = self._resolve_anthropic_two_pass_gaia_transport(gaia_wire)
        system = self._gaia_system_prompt(
            wire_type=gaia_wire, anthropic_transport=transport
        )
        if gaia_route is not None:
            gaia_provider = self._build_gaia_provider(
                gaia_route,
                system_prompt=system,
                output_validator=None,
                anthropic_transport=transport,
            )
        else:
            gaia_provider = copy.copy(self.provider)
            gaia_provider.system_prompt = system
            if transport is not None:
                gaia_provider.structured_transport = transport
        gaia_prompt = self._format_context_prompt(
            payload,
            presence_baseline=presence,
            include_ambient_scene_seeds=False,
            seat="gaia",
        )
        gaia_blocks = list(self._last_rendered_blocks)
        gaia_sources = self._last_rendered_block_sources
        # Rendering adds fixed headings beyond the writer's response tokens.
        empty_writer = SkaldWriterWire.model_construct(
            narrative="",
            choices=[],
            letter="",
            scene=None,
            presence=None,
            operations=None,
        )
        suffix = self._format_gaia_user_prompt("", empty_writer)
        gaia_blocks.append(("finished writer framing", suffix))
        gaia_schema = self._gaia_schema_model(gaia_wire)
        gaia = self._measure_assembly_request(
            gaia_provider,
            gaia_prompt + suffix,
            gaia_blocks,
            gaia_sources,
            gaia_schema,
            self._two_pass_schema_format_kwargs(gaia_schema, wire_type=gaia_wire),
            seat="gaia",
            window=self._gaia_effective_window(gaia_route) if gaia_route else window,
        )
        gaia.reserved_output = writer.budget.max_output_tokens
        return [writer, gaia]

    def measure_writer_request(
        self, payload: Dict[str, Any], window: int
    ) -> tuple[int, "SeatWindow", list[tuple[str, str]], "LocalRequestCounter"]:
        """Expose the writer's locally counted assembly for diagnostics."""
        writer = self.measure_turn_requests(payload, window)[0]
        return writer.tokens, writer.budget, writer.blocks, writer.counter

    def _attach_prompt_window_guard(
        self, provider: Any, prompt: str, *, seat: str, window: Optional[int]
    ) -> None:
        """Bind exact rendered accounting to every provider attempt, including repair."""
        from nexus.telemetry.generation import report_generation_phase

        report_generation_phase("gaia" if seat == "gaia" else "writer")
        from nexus.config.seat_window import resolve_seat_window
        from nexus.telemetry.prompt_window import (
            PromptWindowRecord,
            measure_blocks,
            rendered_request_counter,
        )
        from nexus.telemetry.usage import record_prompt_window, current_usage_context
        from uuid import uuid4

        generation_session = (
            current_usage_context()[2]
            or self._window_payload.get("metadata", {}).get("turn_id")
            or str(uuid4())
        )

        attempt_record = None
        delegate = getattr(provider, "output_validator", None)
        delegate = getattr(delegate, "_wire_validation_delegate", delegate)

        async def validate_attempt(ctx: Any, output: Any) -> Any:
            from nexus.agents.logon.skald_wire import finalize_scene_reset_repair
            from nexus.api.db_pool import get_connection
            from nexus.api.presence_reconciliation import (
                read_character_roster_from_connection,
            )
            from nexus.presence.roster import character_identity_index
            from nexus.telemetry.usage import validation_attempt

            with validation_attempt(attempt_record):
                presence = getattr(output, "presence", None)
                if presence is not None and presence._reset_repair is not None:
                    index = None
                    if self._validation_dbname is not None:
                        with get_connection(self._validation_dbname) as conn:
                            rows = read_character_roster_from_connection(conn)
                        index = character_identity_index(rows.characters, rows.aliases)
                    finalize_scene_reset_repair(output, index)
                return await delegate(ctx, output) if delegate is not None else output

        validate_attempt._wire_validation_delegate = delegate
        provider.output_validator = validate_attempt

        def guard(
            active_prompt: str,
            attempt: int,
            *,
            text_format: Optional[Dict[str, Any]] = None,
            anthropic_request: Optional[Dict[str, Any]] = None,
        ) -> None:
            nonlocal attempt_record
            if window is None:
                resolved_window = resolve_storyteller_context_window(
                    self.settings, self._provider_wire_type, self._provider_type_name
                )
            else:
                resolved_window = window
            budget = resolve_seat_window(
                self.settings, provider.model, seat=seat, window=resolved_window
            )
            from nexus.config import load_settings

            entry = load_settings(self.settings_path).model_entry(provider.model)
            provider.supports_temperature = (
                "temperature" not in entry.unsupported_params
            )
            provider.max_output_tokens = budget.max_output_tokens
            if hasattr(provider, "max_tokens"):
                provider.max_tokens = budget.max_output_tokens
            count = rendered_request_counter(
                provider,
                text_format=text_format,
                anthropic_request=anthropic_request,
                settings_path=self.settings_path,
            )
            blocks = list(
                self._writer_window_blocks
                if seat != "gaia"
                else self._gaia_window_blocks
            )
            base = "".join(text for _, text in blocks)
            if not prompt.startswith(base):
                raise ValueError(
                    "Rendered block set does not match the generation request"
                )
            if prompt != base:
                blocks.append(("finished writer output", prompt[len(base) :]))
            payload = self._window_payload
            active_blocks = list(blocks)
            if not active_prompt.startswith(prompt):
                raise ValueError("Retry rewrote the rendered request prefix")
            if active_prompt != prompt:
                active_blocks.append(
                    ("structured output retry", active_prompt[len(prompt) :])
                )
            if provider.usage_provider_name == "local":
                from nexus.config.local_window import verify_local_context

                verify_local_context(provider, self.settings)
            local_count, _ = self._local_window_counter(
                provider, text_format=text_format, anthropic_request=anthropic_request
            )
            tokens = count(active_prompt)
            counts, _ = measure_blocks(active_blocks, local_count, exact_total=tokens)
            attempt_record = PromptWindowRecord(
                generation_session=generation_session,
                seat=seat,
                attempt=attempt,
                model=provider.model,
                block_tokens=counts,
                input_tokens=tokens,
                effective_ceiling=budget.input_ceiling,
                policy_headroom=budget.policy_headroom,
                headroom=budget.input_ceiling - tokens,
                trimming=payload.get("window_trimming", {}),
            )
            record_prompt_window(attempt_record)
            self._enforce_final_prompt_window(
                active_prompt,
                effective_context_window=budget.input_ceiling,
                rendered_tokens=tokens,
            )
            if seat != "gaia":
                # An untrimmable Gaia core must fail before paying for the writer.
                for request in getattr(self, "_assembly_window_requests", []):
                    if (
                        request.budget.seat == "gaia"
                        and request.tokens > request.target
                    ):
                        raise ValueError(
                            f"Gaia shared request {request.tokens} plus reserved writer output "
                            f"{request.reserved_output} and tokenizer margin {request.safety_margin} "
                            f"exceeds the effective input window {request.budget.input_ceiling}"
                        )
                record_coverage = getattr(self, "record_rendered_coverage", None)
                if record_coverage is not None:
                    record_coverage()
                    self.record_rendered_coverage = None

        provider.prompt_window_guard = guard

    def _enforce_final_prompt_window(
        self,
        prompt: str,
        *,
        effective_context_window: Optional[int],
        rendered_tokens: int,
    ) -> int:
        """Sole hard stop: reject the exactly counted rendered generation request."""
        if effective_context_window is None:
            raise ValueError("Final request requires a resolved seat input ceiling")
        if rendered_tokens > effective_context_window:
            raise ValueError(
                "Final storyteller prompt exceeds the effective context window: "
                f"prompt_tokens={rendered_tokens}, effective_window={effective_context_window}"
            )
        return rendered_tokens

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

    def _read_character_roster_for_schema(
        self,
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
    ) -> Optional[CharacterRosterRows]:
        """Read known characters for a synchronous extended turn."""

        if schema_model is not SkaldTurnWire or self.dbname is None:
            return None
        return read_character_roster(self.dbname)

    async def _read_character_roster_for_schema_async(
        self,
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
    ) -> Optional[CharacterRosterRows]:
        """Read known characters for an asynchronous extended turn."""

        if schema_model is not SkaldTurnWire or self.dbname is None:
            return None
        return await read_character_roster_async(self.dbname)

    @staticmethod
    def _hydrate_provider_response(
        parsed_response: Any,
        schema_model: type[StorytellerResponseBootstrap] | type[SkaldTurnWire],
        *,
        presence_baseline: Optional[PresenceBaseline] = None,
        character_roster: Optional[CharacterRosterRows] = None,
    ) -> StoryTurnResponse:
        """Hydrate extended wire output while leaving bootstrap output unchanged."""

        if schema_model is SkaldTurnWire:
            if not isinstance(parsed_response, SkaldTurnWire):
                raise TypeError(
                    "Extended LOGON provider returned a non-SkaldTurnWire response"
                )
            if character_roster is not None:
                reconcile_prose_mentions(
                    parsed_response,
                    presence_baseline=presence_baseline,
                    roster_rows=character_roster,
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

    def _gaia_schema_model(
        self,
        wire_type: Literal["openai", "anthropic", "local"],
    ) -> type[SkaldGaiaWire]:
        """Return the static or registry-specialized model for one Gaia call."""

        if wire_type != "openai" or not self._tag_library_settings().schema_enums:
            return SkaldGaiaWire
        if self._validation_dbname is None:
            raise GaiaRegistryReadError(
                "OpenAI Gaia registry enum schema requires an initialized "
                "slot validation database"
            )
        return load_gaia_registry_wire_spec(self._validation_dbname).model

    def _two_pass_schema_format_kwargs(
        self,
        schema_model: type,
        *,
        wire_type: Optional[Literal["openai", "anthropic", "local"]] = None,
    ) -> Dict[str, Any]:
        """Return the frozen transport request arguments for one pass.

        ``wire_type`` is the wire class of the provider EXECUTING the pass —
        the pinned gaia seat may run a different class than the writer.
        """

        if not isinstance(schema_model, type):
            raise TypeError("Two-pass schema formatting requires writer or gaia wire")
        is_writer = schema_model is SkaldWriterWire
        is_gaia = issubclass(schema_model, SkaldGaiaWire)
        if not is_writer and not is_gaia:
            raise TypeError("Two-pass schema formatting requires writer or gaia wire")
        gaia_schema_model = cast(type[SkaldGaiaWire], schema_model)
        effective_wire = (
            wire_type if wire_type is not None else self._provider_wire_type
        )
        if effective_wire is None:
            raise RuntimeError(
                "Two-pass schema formatting requires an active provider wire class"
            )
        prompt_cache_key: Optional[str] = None
        if effective_wire == "openai":
            from nexus.api.slot_utils import require_slot_dbname

            slot_dbname = require_slot_dbname(dbname=self.dbname)
            usage_seat = "skald_writer" if is_writer else "gaia"
            prompt_cache_key = f"nexus:{slot_dbname}:{usage_seat}"
        cache_key: tuple[Any, ...]
        if is_gaia:
            cache_key = (
                SkaldGaiaWire,
                effective_wire,
                prompt_cache_key,
                gaia_wire_registry_digest(gaia_schema_model),
                schema_model,
            )
        else:
            cache_key = (SkaldWriterWire, effective_wire, prompt_cache_key)
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
                    if is_writer
                    else skald_gaia_strict_text_format(gaia_schema_model)
                ),
                "prompt_cache_key": prompt_cache_key,
            }
        elif effective_wire == "local":
            lenient_schema = (
                skald_writer_lenient_schema()
                if is_writer
                else skald_gaia_lenient_schema()
            )
            kwargs = {
                "text_format": openai_response_text_format(
                    SkaldWriterWire if is_writer else SkaldGaiaWire,
                    schema=lenient_schema,
                )
            }
        elif effective_wire == "anthropic":
            if is_writer:
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

    @staticmethod
    def build_recent_orrery_rulings_section(
        session: Any,
        *,
        anchor_chunk_id: int,
        limit: int,
    ) -> list[str]:
        """Build recent adjudication lines for the shared storyteller context."""

        from nexus.agents.orrery.history import adjudication_history

        if anchor_chunk_id <= 0:
            raise ValueError("anchor_chunk_id must be positive")
        if limit <= 0:
            raise ValueError("limit must be positive")

        history = adjudication_history(
            session,
            through_tick=anchor_chunk_id,
            recent_rulings_limit=limit,
        )
        rulings = history["recent_rulings"]
        if not rulings:
            return []

        lines = ["=== RECENT ORRERY RULINGS ==="]
        for ruling in rulings:
            turn_offset = ruling.get("turn_offset")
            if (
                isinstance(turn_offset, bool)
                or not isinstance(turn_offset, int)
                or turn_offset <= 0
            ):
                raise ValueError(
                    "Recent Orrery ruling requires a positive accepted-turn offset"
                )

            outcome = ruling["outcome"]
            if outcome == "ratified":
                summary = ruling.get("summary")
                if not isinstance(summary, str) or not summary.strip():
                    raise ValueError(
                        "Ratified Orrery ruling requires its committed brief"
                    )
                summary = " ".join(summary.split())
            elif outcome in {"deferred", "voided"}:
                state_delta = ruling.get("state_delta")
                if not isinstance(state_delta, Mapping):
                    raise TypeError(
                        f"{outcome.title()} Orrery ruling requires its state_delta"
                    )
                rendered_delta = json.dumps(
                    state_delta,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                summary = f"{ruling['template_id']}: state_delta={rendered_delta}"
            else:
                raise ValueError(f"Unsupported recent Orrery outcome: {outcome!r}")

            turn_label = f"(turn N-{turn_offset})"
            if outcome == "ratified":
                lines.append(f"[RATIFIED] {summary} {turn_label}")
            elif outcome == "deferred":
                count = ruling["consecutive_deferrals"]
                if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                    raise ValueError(
                        "Deferred Orrery ruling requires a positive consecutive count"
                    )
                suffix = (
                    "th"
                    if 10 < count % 100 < 14
                    else {1: "st", 2: "nd", 3: "rd"}.get(count % 10, "th")
                )
                lines.append(
                    f"[DEFERRED] {summary} {turn_label} — "
                    f"{count}{suffix} consecutive deferral"
                )
            elif outcome == "voided":
                note = ruling.get("note")
                rendered_note = " ".join(note.split()) if isinstance(note, str) else ""
                lines.append(
                    f"[VOIDED — {rendered_note or 'no note'}] "
                    f"{summary} {turn_label}"
                )
        return lines

    def _format_context_prompt(
        self,
        context: Dict,
        *,
        presence_baseline: Optional[PresenceBaseline] = None,
        include_ambient_scene_seeds: bool = True,
        rendered_blocks: Optional[list[tuple[str, str]]] = None,
        seat: Literal["writer", "gaia"] = "writer",
    ) -> str:
        """Format context payload into a prompt for the Apex AI"""
        from nexus.config import load_settings
        from nexus.telemetry.prompt_window import RenderedSections

        raw_limits = (self.settings.get("lore") or {}).get("render_limits")
        render_limits = (
            RenderLimits.model_validate(raw_limits)
            if raw_limits is not None
            else load_settings(self.settings_path).lore.render_limits
        )
        sections = RenderedSections()

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
                sections.append(clock_face(intertitle["world_time"]))
            if intertitle.get("location_name"):
                location_line = str(intertitle["location_name"])
                if intertitle.get("location_geom"):
                    location_line += f" — {intertitle['location_geom']}"
                sections.append(location_line)
            sections.append("")

        sections.kind = "scene conditions"
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

        sections.kind = "private storyteller correspondence"
        correspondence = context.get("storyteller_correspondence")
        if correspondence is not None:
            if not isinstance(correspondence, str) or not correspondence.strip():
                raise ValueError(
                    "storyteller_correspondence must be a nonempty rendered block"
                )
            sections.extend([correspondence, ""])

        sections.kind = "recent narrative"
        # Add warm slice
        if context.get("warm_slice"):
            sections.append("=== RECENT NARRATIVE ===")
            for chunk in context["warm_slice"]["chunks"]:
                chunk_text = chunk.get("text", "")
                if is_retrograde_summary(chunk):
                    sections.append_chunk(
                        f"[{_retrieval_source_label(chunk)}] {chunk_text}", chunk
                    )
                else:
                    sections.append_chunk(chunk_text, chunk)

        sections.kind = "bootstrap context"
        bootstrap_sections = self._format_bootstrap_context(
            context.get("bootstrap_data")
        )
        if bootstrap_sections:
            sections.extend(bootstrap_sections)

        sections.kind = "scene roster"
        # The writer authors sparse changes against this exact parent roster.
        if seat == "writer" and presence_baseline is not None:
            from nexus.presence.roster import render_roster, roster_from_baseline

            sections.append(
                render_roster(
                    roster_from_baseline(presence_baseline),
                    player_character_id=presence_baseline.player_character_id,
                )
            )

        sections.kind = "user input"
        # Add user input
        sections.append("\n=== USER INPUT ===")
        sections.append(context.get("user_input", ""))

        sections.kind = "entity dossier"
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
                        tags = ", ".join(
                            (char.get("orrery_tag_summary") or "").split(", ")[
                                : render_limits.character_tags
                            ]
                        )
                        tag_detail = f" Tags: {tags}" if tags else ""
                        sections.append(
                            f"- {name}: at {location}, {activity}{tag_detail}"
                        )

                # Featured characters (full details)
                featured_chars = characters.get("featured", [])
                if featured_chars:
                    sections.append("\nFeatured Characters (full details):")
                    for char in featured_chars:
                        name = char.get("name", "Unknown")
                        ref_type = char.get("reference_type", "")
                        summary = char.get("summary", "")
                        tags = ", ".join(
                            (char.get("orrery_tag_summary") or "").split(", ")[
                                : render_limits.character_tags
                            ]
                        )
                        tag_detail = f"Tags: {tags}" if tags else ""
                        detail = " ".join(
                            part for part in (summary, tag_detail) if part
                        )
                        sections.append(f"- {name} [{ref_type}]: {detail}")

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
                for rel in relationships[: render_limits.relationships]:
                    char1 = rel.get("character1_name", "Unknown")
                    char2 = rel.get("character2_name", "Unknown")
                    rel_type = rel.get("relationship_type", "unknown")
                    valence = rel["valence_current"]
                    sections.append(
                        f"- {char1} → {char2}: {rel_type} (valence {valence:+g})"
                    )

            events = entity_data.get("events", [])
            if events:
                sections.append("\nActive Events:")
                for event in events[: render_limits.events]:
                    name = event.get("name", "Unknown")
                    summary = event.get("summary", "")
                    sections.append(f"- {name}: {summary}")

            threats = entity_data.get("threats", [])
            if threats:
                sections.append("\nActive Threats:")
                for threat in threats[: render_limits.threats]:
                    name = threat.get("name", "Unknown")
                    description = threat.get("description", "")
                    sections.append(f"- {name}: {description}")

        # Add retrieved passages
        sections.kind = "historical context"
        if context.get("retrieved_passages"):
            sections.append("\n=== HISTORICAL CONTEXT ===")
            for passage in context["retrieved_passages"]["results"][
                :5
            ]:  # Limit to top 5
                sections.append_chunk(
                    f"[{_retrieval_source_label(passage)} | "
                    f"Score: {passage.get('score', 0):.2f}] "
                    f"{passage.get('text', '')}",
                    passage,
                )

        sections.kind = "world knowledge"
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
                source = item.get("source") or {}
                if source.get("kind") == "experience":
                    qualifiers.append(f"Character experience {source.get('id')}")
                character_name = item.get("character_name") or (
                    f"entity {item.get('character_entity_id')}"
                )
                sections.append(
                    f"- {character_name} [{'; '.join(qualifiers)}]: "
                    f"{item.get('summary', '')}"
                )
            if context.get("world_knowledge_truncated"):
                sections.append("(older knowledge omitted)")

        sections.kind = "orrery tag library"
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

        _prompt_cfg = (self.settings.get("orrery") or {}).get("prompt") or {}
        prompt_settings = OrreryPromptSettings.model_validate(_prompt_cfg)

        sections.kind = "recent orrery rulings"
        recent_rulings_section = context.get("orrery_recent_rulings_section")
        if recent_rulings_section is None:
            recent_rulings_section = []
        elif not isinstance(recent_rulings_section, list):
            raise TypeError(
                "orrery_recent_rulings_section must be None or a list, got "
                f"{recent_rulings_section!r}"
            )
        if not isinstance(recent_rulings_section, list) or not all(
            isinstance(line, str) and line for line in recent_rulings_section
        ):
            raise TypeError(
                "orrery_recent_rulings_section must be a list of nonempty strings"
            )
        if recent_rulings_section:
            sections.append("")
            sections.extend(recent_rulings_section)

        card_snapshot = snapshot_from_context(context)
        card_selection = rendered_selection(card_snapshot, prompt_settings)
        handles = proposal_handles(card_selection)
        proposal_cards = {card_key(card): card for card in card_snapshot["resolutions"]}
        pressure_cards = {
            card_key(card): card for card in card_snapshot["scene_pressures"]
        }
        proposal_positions = {key: index for index, key in enumerate(proposal_cards)}
        pressure_positions = {key: index for index, key in enumerate(pressure_cards)}
        ranked_anchor = context.get("orrery_anchor_chunk_id")
        current_anchor = self._parent_chunk_id(context)

        def card_line(card: Mapping[str, Any], *, pressure: bool = False) -> str:
            key = card_key(card)
            position = card.get("position")
            if position is None:
                position = (pressure_positions if pressure else proposal_positions)[key]
            earlier = (
                ranked_anchor is not None
                and current_anchor is not None
                and ranked_anchor < current_anchor
            )
            if (
                ranked_anchor is None
                and card.get("evaluated_at")
                and intertitle.get("world_time")
            ):
                earlier = datetime.fromisoformat(
                    card["evaluated_at"]
                ) < datetime.fromisoformat(intertitle["world_time"])
            description = (
                card.get("prompt_text") or card.get("pressure_stub", "")
                if pressure
                else card.get("branch_label") or card["template_id"]
            )
            return _orrery_card_line(
                card,
                handles[key],
                position=position,
                description=description,
                earlier_turn=earlier,
            )

        sections.kind = "orrery imminent activity"
        imminent_activity = context.get("orrery_imminent_activity") or []
        if imminent_activity:
            sections.append("\n=== ORRERY IMMINENT ACTIVITY ===")
            sections.append(load(PromptId.TURN_BLOCKS_IMMINENT_ACTIVITY))
            for item in card_selection:
                if item["kind"] == "resolution":
                    sections.append(card_line(proposal_cards[item["proposal_id"]]))

        sections.kind = "orrery scene pressure"
        scene_pressures = context.get("orrery_scene_pressures") or []
        if scene_pressures:
            sections.append("\n=== ORRERY SCENE PRESSURE ===")
            sections.append(load(PromptId.TURN_BLOCKS_SCENE_PRESSURE))
            for item in card_selection:
                if (
                    item["kind"] == "scene_pressure"
                    and item["proposal_id"] in pressure_cards
                ):
                    sections.append(
                        card_line(pressure_cards[item["proposal_id"]], pressure=True)
                    )

        sections.kind = "orrery ambient scene seeds"
        ambient_scene_seeds = context.get("orrery_ambient_scene_seeds") or []
        if ambient_scene_seeds and include_ambient_scene_seeds:
            sections.append("\n=== ORRERY AMBIENT SCENE SEEDS ===")
            sections.append(self._load_ambient_scene_instruction())
            for seed in ambient_scene_seeds:
                if not isinstance(seed, dict):
                    continue
                participants = seed.get("participants") or []
                participant_bits = []
                for item in participants:
                    if not isinstance(item, dict):
                        continue
                    fallback_name = f"entity {item.get('entity_id')}"
                    name = _prompt_one_line(item.get("name") or fallback_name)
                    speaking = str(bool(item.get("speaking_eligible"))).lower()
                    participant_bits.append(
                        f"{name}#{item.get('entity_id')}[speak={speaking}]"
                    )
                participant_summary = ", ".join(participant_bits)
                entitlement_summary = "; ".join(
                    f"{item.get('participant_entity_id')}:"
                    f"claims={item.get('claim_ids') or []},"
                    f"experiences={item.get('character_experience_ids') or []}"
                    for item in seed.get("entitlements") or []
                    if isinstance(item, dict)
                )
                location = seed.get("location_constraint") or {}
                sections.append(
                    f"- {seed.get('seed_id')} participants={participant_summary}; "
                    f"topic={_prompt_one_line(seed.get('topic'))}; "
                    f"tension={_prompt_one_line(seed.get('tension'))}; "
                    f"why_now={_prompt_one_line(seed.get('why_now'))}; "
                    f"entitlements={entitlement_summary}; "
                    f"location={location.get('kind')}:{location.get('place_id')}; "
                    f"budget={seed.get('turn_budget')} turns/"
                    f"{seed.get('line_budget')} lines; silence_ok=true"
                )

        sections.kind = "orrery joint beats"
        joint_beats = context.get("orrery_joint_beats") or []
        if joint_beats:
            sections.append("\n=== ORRERY JOINT BEATS ===")
            sections.append(load(PromptId.TURN_BLOCKS_JOINT_BEATS))
            for item in card_selection:
                if item["kind"] == "joint_beat":
                    sections.append(card_line(proposal_cards[item["proposal_id"]]))

        sections.kind = "orrery ambient peripherals"
        bleed_menu = context.get("orrery_bleed_menu") or []
        if bleed_menu:
            sections.append("\n=== ORRERY AMBIENT PERIPHERALS ===")
            sections.append(load(PromptId.TURN_BLOCKS_AMBIENT_PERIPHERALS))
            for item in bleed_menu[: render_limits.bleed_menu]:
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
        sections.kind = "author's note"
        note = context.get("note")
        if note:
            sections.append("\n=== AUTHOR'S NOTE ===")
            sections.append(load(PromptId.TURN_BLOCKS_AUTHORS_NOTE))
            sections.append(note)

        sections.kind = "instructions"
        # Add instructions
        sections.append("\n=== INSTRUCTIONS ===")
        sections.append(load(PromptId.TURN_BLOCKS_CONTINUE_NARRATIVE))
        sections.append(load(PromptId.TURN_BLOCKS_MAINTAIN_CONSISTENCY))

        self._last_rendered_blocks = sections.blocks()
        self._last_rendered_block_sources = sections.sources
        if rendered_blocks is not None:
            rendered_blocks.extend(self._last_rendered_blocks)
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

        if not self._tag_library_settings().contextual:
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
            load(PromptId.TURN_BLOCKS_BOOTSTRAP_INTRO),
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
                    load(PromptId.TURN_BLOCKS_BOOTSTRAP_SECRETS),
                    seed_secrets,
                ]
            )

        return sections

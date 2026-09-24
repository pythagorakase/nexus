"""Single catalog and byte-preserving loader for model prompt documents.

Templates use {{UPPER_CASE}} markers so JSON examples and Markdown braces stay
literal. Only source templates are cached; substitutions are local to each load.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
import re
from threading import Lock
from types import MappingProxyType
from typing import Literal, Mapping


PromptSeat = Literal[
    "all",
    "correspondence_compaction",
    "experience_renderer",
    "gaia",
    "geo_authoring",
    "legacy_generator",
    "legacy_operator",
    "player",
    "retrieval_query_bakeoff",
    "retrograde_expansion",
    "retrograde_seed_candidates",
    "retrograde_seed_selection",
    "set_designer",
    "skald_single_pass",
    "skald_writer",
    "summaries",
    "trait_input_derivation",
    "wizard",
    "wizard_debug",
    "wizard_wildcard",
]


class PromptId(str, Enum):
    """Stable identities for every live prompt document."""

    AMBIENT_SCENE_SEEDS = "ambient_scene_seeds"
    CORRESPONDENCE_COMPACTION = "correspondence_compaction"
    CORRESPONDENCE_DIGEST_RETRY = "correspondence/digest_retry"
    CORRESPONDENCE_HEADER = "correspondence/header"
    CORRESPONDENCE_LETTER_RETRY = "correspondence/letter_retry"
    EXPERIENCE_RENDERER = "experience_renderer"
    GEO_AUTHORING = "orrery/geo_authoring"
    OPERATORS_ESTIMATE_TIME_DELTA_SYSTEM = "operators/estimate_time_delta_system"
    OPERATORS_ESTIMATE_TIME_DELTA_USER = "operators/estimate_time_delta_user"
    OPERATORS_FREESTYLE_SYSTEM = "operators/freestyle_system"
    OPERATORS_FREESTYLE_USER = "operators/freestyle_user"
    OPERATORS_MAP_BUILDER = "operators/map_builder"
    OPERATORS_MAP_BUILDER_SCHEMA = "operators/map_builder_schema"
    OPERATORS_PROCESS_CHARACTERS = "operators/process_characters"
    OPERATORS_PROCESS_FACTIONS = "operators/process_factions"
    OPERATORS_RETRIEVAL_QUERY_BAKEOFF = "operators/retrieval_query_bakeoff"
    RETROGRADE_EXPANSION = "retrograde/expansion"
    RETROGRADE_EXPANSION_CONSTRAINTS = "retrograde/expansion_constraints"
    RETROGRADE_EXPANSION_RETRY = "retrograde/expansion_retry"
    RETROGRADE_EXPANSION_SYSTEM = "retrograde/expansion_system"
    RETROGRADE_EXPANSION_TASK = "retrograde/expansion_task"
    RETROGRADE_GENERATION_CONSTRAINTS = "retrograde/generation_constraints"
    RETROGRADE_GENERATION_RETRY = "retrograde/generation_retry"
    RETROGRADE_GENERATION_SYSTEM = "retrograde/generation_system"
    RETROGRADE_GENERATION_TASK = "retrograde/generation_task"
    RETROGRADE_MECHANICAL_TAG_RULES = "retrograde/mechanical_tag_rules"
    RETROGRADE_PAIR_TAG_RULE = "retrograde/pair_tag_rule"
    RETROGRADE_REVIEW_CONTRACT = "retrograde/review_contract"
    RETROGRADE_SEED_GENERATION = "retrograde/seed_generation"
    RETROGRADE_SEED_SELECTION = "retrograde/seed_selection"
    RETROGRADE_SELECTION_PRIORITIES = "retrograde/selection_priorities"
    RETROGRADE_SELECTION_SYSTEM = "retrograde/selection_system"
    RETROGRADE_SELECTION_TASK = "retrograde/selection_task"
    RETROGRADE_WEAVER_INSTRUCTIONS = "retrograde/weaver_instructions"
    RETRY_CLOSED_REGISTRY = "retry/closed_registry"
    RETRY_STRUCTURED_OUTPUT = "retry/structured_output"
    STORYTELLER_BOOTSTRAP = "storyteller_bootstrap"
    STORYTELLER_CORE = "storyteller_core"
    STORYTELLER_GAIA = "storyteller_gaia"
    STORYTELLER_NEW = "storyteller_new"
    STORYTELLER_SET_DESIGNER = "storyteller_set_designer"
    STORYTELLER_SINGLE_PASS = "storyteller_single_pass"
    STORYTELLER_WRITER_PASS = "storyteller_writer_pass"
    SUMMARIES_DEFAULT_SYSTEM = "summaries/default_system"
    SUMMARIES_EPISODE_RANGE_USER = "summaries/episode_range_user"
    SUMMARIES_EPISODE_SYSTEM = "summaries/episode_system"
    SUMMARIES_EPISODE_USER = "summaries/episode_user"
    SUMMARIES_SEASON_RANGE_USER = "summaries/season_range_user"
    SUMMARIES_SEASON_SYSTEM = "summaries/season_system"
    SUMMARIES_SEASON_USER = "summaries/season_user"
    TAG_LIBRARY_ACTIVE_TAG = "tag_library/active_tag"
    TAG_LIBRARY_CONTEXTUAL_INDEX = "tag_library/contextual_index"
    TAG_LIBRARY_EMPTY = "tag_library/empty"
    TAG_LIBRARY_HEADER = "tag_library/header"
    TRAIT_INPUT_DERIVER = "trait_input_deriver"
    TURN_BLOCKS_AMBIENT_PERIPHERALS = "turn_blocks/ambient_peripherals"
    TURN_BLOCKS_AUTHORS_NOTE = "turn_blocks/authors_note"
    TURN_BLOCKS_BOOTSTRAP_INTRO = "turn_blocks/bootstrap_intro"
    TURN_BLOCKS_BOOTSTRAP_SECRETS = "turn_blocks/bootstrap_secrets"
    TURN_BLOCKS_CONTINUE_NARRATIVE = "turn_blocks/continue_narrative"
    TURN_BLOCKS_IMMINENT_ACTIVITY = "turn_blocks/imminent_activity"
    TURN_BLOCKS_JOINT_BEATS = "turn_blocks/joint_beats"
    TURN_BLOCKS_MAINTAIN_CONSISTENCY = "turn_blocks/maintain_consistency"
    TURN_BLOCKS_SCENE_PRESSURE = "turn_blocks/scene_pressure"
    WIZARD_ACCEPT_FATE = "wizard/accept_fate"
    WIZARD_ACCEPT_FATE_RETRY = "wizard/accept_fate_retry"
    WIZARD_CHARACTER_PHASE = "wizard/character_phase"
    WIZARD_CHOICES_INSTRUCTION = "wizard/choices_instruction"
    WIZARD_DEV_PREAMBLE = "wizard/dev_preamble"
    WIZARD_LEGACY_CHARACTER_SYSTEM = "wizard/legacy_character_system"
    WIZARD_LEGACY_CHARACTER_USER = "wizard/legacy_character_user"
    WIZARD_LEGACY_LOCATION_SYSTEM = "wizard/legacy_location_system"
    WIZARD_LEGACY_LOCATION_USER = "wizard/legacy_location_user"
    WIZARD_LEGACY_SEED_SYSTEM = "wizard/legacy_seed_system"
    WIZARD_LEGACY_SEED_USER = "wizard/legacy_seed_user"
    WIZARD_LEGACY_SETTING_SYSTEM = "wizard/legacy_setting_system"
    WIZARD_LEGACY_SETTING_USER = "wizard/legacy_setting_user"
    WIZARD_SEED_PHASE = "wizard/seed_phase"
    WIZARD_SET_DESIGNER_USER = "wizard/set_designer_user"
    WIZARD_SUBMIT_INSTRUCTION = "wizard/submit_instruction"
    WIZARD_SUGGESTED_TRAITS_INSTRUCTION = "wizard/suggested_traits_instruction"
    WIZARD_SUGGESTED_TRAITS_INTRO = "wizard/suggested_traits_intro"
    WIZARD_TOOL_SUBMIT_CHARACTER_CONCEPT = "wizard/tools/submit_character_concept"
    WIZARD_TOOL_SUBMIT_STARTING_SCENARIO = "wizard/tools/submit_starting_scenario"
    WIZARD_TOOL_SUBMIT_TRAIT_SELECTION = "wizard/tools/submit_trait_selection"
    WIZARD_TOOL_SUBMIT_WILDCARD_TRAIT = "wizard/tools/submit_wildcard_trait"
    WIZARD_TOOL_SUBMIT_WORLD_DOCUMENT = "wizard/tools/submit_world_document"
    WIZARD_TRAIT_DERIVER_SYSTEM = "wizard/trait_deriver_system"


@dataclass(frozen=True)
class PromptSpec:
    """Repository-relative document, consumer seats, and exact marker contract."""

    path: str
    seats: tuple[PromptSeat, ...]
    placeholders: frozenset[str] = frozenset()


PROMPTS: Mapping[PromptId, PromptSpec] = MappingProxyType(
    {
        PromptId.AMBIENT_SCENE_SEEDS: PromptSpec(
            "ambient_scene_seeds.md", ("skald_writer",)
        ),
        PromptId.CORRESPONDENCE_COMPACTION: PromptSpec(
            "correspondence_compaction.md",
            ("correspondence_compaction",),
            frozenset(("MAX_DIGEST_TOKENS",)),
        ),
        PromptId.CORRESPONDENCE_DIGEST_RETRY: PromptSpec(
            "correspondence/digest_retry.md",
            ("skald_writer", "gaia", "correspondence_compaction"),
            frozenset(("TOKEN_COUNT", "HARD_CAP_TOKENS", "MAX_DIGEST_TOKENS")),
        ),
        PromptId.CORRESPONDENCE_HEADER: PromptSpec(
            "correspondence/header.md",
            ("skald_writer", "gaia", "correspondence_compaction"),
        ),
        PromptId.CORRESPONDENCE_LETTER_RETRY: PromptSpec(
            "correspondence/letter_retry.md",
            ("skald_writer", "gaia", "correspondence_compaction"),
            frozenset(("TOKEN_COUNT", "MAX_LETTER_TOKENS")),
        ),
        PromptId.EXPERIENCE_RENDERER: PromptSpec(
            "experience_renderer.md", ("experience_renderer",)
        ),
        PromptId.GEO_AUTHORING: PromptSpec(
            "orrery/geo_authoring.md",
            ("geo_authoring",),
            frozenset(("PLACE_NAME", "PLACE_SUMMARY", "ZONE_NAME", "ZONE_SUMMARY")),
        ),
        PromptId.OPERATORS_ESTIMATE_TIME_DELTA_SYSTEM: PromptSpec(
            "operators/estimate_time_delta_system.md",
            ("legacy_operator",),
            frozenset(("CHUNK_ID", "CHUNK_RAW_TEXT")),
        ),
        PromptId.OPERATORS_ESTIMATE_TIME_DELTA_USER: PromptSpec(
            "operators/estimate_time_delta_user.md", ("legacy_operator",)
        ),
        PromptId.OPERATORS_FREESTYLE_SYSTEM: PromptSpec(
            "operators/freestyle_system.md", ("legacy_operator",)
        ),
        PromptId.OPERATORS_FREESTYLE_USER: PromptSpec(
            "operators/freestyle_user.md",
            ("legacy_operator",),
            frozenset(("ARGS_PROMPT",)),
        ),
        PromptId.OPERATORS_MAP_BUILDER: PromptSpec(
            "operators/map_builder.md", ("legacy_operator",)
        ),
        PromptId.OPERATORS_MAP_BUILDER_SCHEMA: PromptSpec(
            "operators/map_builder_schema.md",
            ("legacy_operator",),
            frozenset(("CHUNK_ID",)),
        ),
        PromptId.OPERATORS_PROCESS_CHARACTERS: PromptSpec(
            "operators/process_characters.md",
            ("legacy_operator",),
            frozenset(
                (
                    "KNOWN_CHARACTERS_FORMATTED",
                    "CHUNK_ID",
                    "CHUNK_RAW_TEXT",
                    "CHUNK_ID_4",
                )
            ),
        ),
        PromptId.OPERATORS_PROCESS_FACTIONS: PromptSpec(
            "operators/process_factions.md",
            ("legacy_operator",),
            frozenset(("ROSTER_TEXT",)),
        ),
        PromptId.OPERATORS_RETRIEVAL_QUERY_BAKEOFF: PromptSpec(
            "operators/retrieval_query_bakeoff.md",
            ("retrieval_query_bakeoff",),
            frozenset(
                (
                    "SAMPLE_SOURCE_TEXT_8000",
                    "SAMPLE_CHOICE_TEXT",
                    "JOIN_SAMPLE_SOURCE_REFS_CHARACTERS_OR_NONE",
                    "JOIN_SAMPLE_SOURCE_REFS_PLACES_OR_NONE",
                    "JOIN_SAMPLE_SOURCE_REFS_FACTIONS_OR_NONE",
                )
            ),
        ),
        PromptId.RETROGRADE_EXPANSION: PromptSpec(
            "retrograde/expansion.md",
            ("retrograde_expansion",),
            frozenset(("REQUEST_JSON",)),
        ),
        PromptId.RETROGRADE_EXPANSION_CONSTRAINTS: PromptSpec(
            "retrograde/expansion_constraints.md",
            ("retrograde_expansion",),
            frozenset(("ENTITY_REF_MAX_LENGTH",)),
        ),
        PromptId.RETROGRADE_EXPANSION_RETRY: PromptSpec(
            "retrograde/expansion_retry.md",
            ("retrograde_expansion",),
            frozenset(("EXC",)),
        ),
        PromptId.RETROGRADE_EXPANSION_SYSTEM: PromptSpec(
            "retrograde/expansion_system.md", ("retrograde_expansion",)
        ),
        PromptId.RETROGRADE_EXPANSION_TASK: PromptSpec(
            "retrograde/expansion_task.md", ("retrograde_expansion",)
        ),
        PromptId.RETROGRADE_GENERATION_CONSTRAINTS: PromptSpec(
            "retrograde/generation_constraints.md",
            ("retrograde_seed_candidates",),
            frozenset(("ENTITY_REF_MAX_LENGTH",)),
        ),
        PromptId.RETROGRADE_GENERATION_RETRY: PromptSpec(
            "retrograde/generation_retry.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(("EXC",)),
        ),
        PromptId.RETROGRADE_GENERATION_SYSTEM: PromptSpec(
            "retrograde/generation_system.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_GENERATION_TASK: PromptSpec(
            "retrograde/generation_task.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_MECHANICAL_TAG_RULES: PromptSpec(
            "retrograde/mechanical_tag_rules.md",
            ("retrograde_seed_candidates",),
        ),
        PromptId.RETROGRADE_PAIR_TAG_RULE: PromptSpec(
            "retrograde/pair_tag_rule.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_REVIEW_CONTRACT: PromptSpec(
            "retrograde/review_contract.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_SEED_GENERATION: PromptSpec(
            "retrograde/seed_generation.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(("REQUEST_JSON",)),
        ),
        PromptId.RETROGRADE_SEED_SELECTION: PromptSpec(
            "retrograde/seed_selection.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(("REQUEST_JSON",)),
        ),
        PromptId.RETROGRADE_SELECTION_PRIORITIES: PromptSpec(
            "retrograde/selection_priorities.md",
            ("retrograde_seed_selection",),
        ),
        PromptId.RETROGRADE_SELECTION_SYSTEM: PromptSpec(
            "retrograde/selection_system.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_SELECTION_TASK: PromptSpec(
            "retrograde/selection_task.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_WEAVER_INSTRUCTIONS: PromptSpec(
            "retrograde/weaver_instructions.md",
            ("retrograde_seed_candidates",),
        ),
        PromptId.RETRY_CLOSED_REGISTRY: PromptSpec(
            "retry/closed_registry.md",
            ("gaia", "skald_single_pass"),
            frozenset(("DECLARATION_GUIDANCE", "FORMATTED")),
        ),
        PromptId.RETRY_STRUCTURED_OUTPUT: PromptSpec(
            "retry/structured_output.md", ("all",), frozenset(("PROMPT", "MESSAGE"))
        ),
        PromptId.STORYTELLER_BOOTSTRAP: PromptSpec(
            "storyteller_bootstrap.md", ("skald_writer",)
        ),
        PromptId.STORYTELLER_CORE: PromptSpec(
            "storyteller_core.md", ("skald_writer", "skald_single_pass")
        ),
        PromptId.STORYTELLER_GAIA: PromptSpec(
            "storyteller_gaia.md", ("gaia",), frozenset(("MAX_LETTER_TOKENS",))
        ),
        PromptId.STORYTELLER_NEW: PromptSpec(
            "storyteller_new.md",
            ("wizard", "wizard_wildcard", "wizard_debug", "player"),
        ),
        PromptId.STORYTELLER_SET_DESIGNER: PromptSpec(
            "storyteller_set_designer.md", ("set_designer",)
        ),
        PromptId.STORYTELLER_SINGLE_PASS: PromptSpec(
            "storyteller_single_pass.md", ("skald_single_pass",)
        ),
        PromptId.STORYTELLER_WRITER_PASS: PromptSpec(
            "storyteller_writer_pass.md",
            ("skald_writer",),
            frozenset(("MAX_LETTER_TOKENS",)),
        ),
        PromptId.SUMMARIES_DEFAULT_SYSTEM: PromptSpec(
            "summaries/default_system.md", ("summaries",)
        ),
        PromptId.SUMMARIES_EPISODE_RANGE_USER: PromptSpec(
            "summaries/episode_range_user.md",
            ("summaries",),
            frozenset(("START_ID", "END_ID", "CHUNKS_TEXT")),
        ),
        PromptId.SUMMARIES_EPISODE_SYSTEM: PromptSpec(
            "summaries/episode_system.md", ("summaries",)
        ),
        PromptId.SUMMARIES_EPISODE_USER: PromptSpec(
            "summaries/episode_user.md",
            ("summaries",),
            frozenset(("SEASON", "EPISODE", "CONTEXT_TEXT", "CHUNKS_TEXT")),
        ),
        PromptId.SUMMARIES_SEASON_RANGE_USER: PromptSpec(
            "summaries/season_range_user.md",
            ("summaries",),
            frozenset(("START_ID", "END_ID", "CHUNKS_TEXT")),
        ),
        PromptId.SUMMARIES_SEASON_SYSTEM: PromptSpec(
            "summaries/season_system.md", ("summaries",)
        ),
        PromptId.SUMMARIES_SEASON_USER: PromptSpec(
            "summaries/season_user.md",
            ("summaries",),
            frozenset(("SEASON", "PREV_SUMMARIES_TEXT", "CHUNKS_TEXT")),
        ),
        PromptId.TAG_LIBRARY_ACTIVE_TAG: PromptSpec(
            "tag_library/active_tag.md",
            ("skald_writer", "gaia", "skald_single_pass", "wizard"),
            frozenset(("STATUS",)),
        ),
        PromptId.TAG_LIBRARY_CONTEXTUAL_INDEX: PromptSpec(
            "tag_library/contextual_index.md",
            ("skald_writer", "gaia", "skald_single_pass", "wizard"),
        ),
        PromptId.TAG_LIBRARY_EMPTY: PromptSpec(
            "tag_library/empty.md",
            ("skald_writer", "gaia", "skald_single_pass", "wizard"),
        ),
        PromptId.TAG_LIBRARY_HEADER: PromptSpec(
            "tag_library/header.md",
            ("skald_writer", "gaia", "skald_single_pass", "wizard"),
        ),
        PromptId.TRAIT_INPUT_DERIVER: PromptSpec(
            "trait_input_deriver.md", ("trait_input_derivation",)
        ),
        PromptId.TURN_BLOCKS_AMBIENT_PERIPHERALS: PromptSpec(
            "turn_blocks/ambient_peripherals.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_AUTHORS_NOTE: PromptSpec(
            "turn_blocks/authors_note.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_BOOTSTRAP_INTRO: PromptSpec(
            "turn_blocks/bootstrap_intro.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_BOOTSTRAP_SECRETS: PromptSpec(
            "turn_blocks/bootstrap_secrets.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_CONTINUE_NARRATIVE: PromptSpec(
            "turn_blocks/continue_narrative.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_IMMINENT_ACTIVITY: PromptSpec(
            "turn_blocks/imminent_activity.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_JOINT_BEATS: PromptSpec(
            "turn_blocks/joint_beats.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_MAINTAIN_CONSISTENCY: PromptSpec(
            "turn_blocks/maintain_consistency.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.TURN_BLOCKS_SCENE_PRESSURE: PromptSpec(
            "turn_blocks/scene_pressure.md",
            ("skald_writer", "gaia", "skald_single_pass"),
        ),
        PromptId.WIZARD_ACCEPT_FATE: PromptSpec(
            "wizard/accept_fate.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_ACCEPT_FATE_RETRY: PromptSpec(
            "wizard/accept_fate_retry.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
            frozenset(("TOOL_NAME",)),
        ),
        PromptId.WIZARD_CHARACTER_PHASE: PromptSpec(
            "wizard/character_phase.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_CHOICES_INSTRUCTION: PromptSpec(
            "wizard/choices_instruction.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_DEV_PREAMBLE: PromptSpec(
            "wizard/dev_preamble.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
            frozenset(
                (
                    "CONTEXT_SLOT",
                    "CONTEXT_THREAD_ID",
                    "CONTEXT_MODEL",
                    "CONTEXT_PHASE",
                    "CHARACTER_SUBPHASE_CONTEXT",
                    "CONTEXT_USER_TURNS",
                    "CONTEXT_ASSISTANT_TURNS",
                    "CONTEXT_HISTORY_LEN",
                    "PRIMARY_TOOL",
                )
            ),
        ),
        PromptId.WIZARD_LEGACY_CHARACTER_SYSTEM: PromptSpec(
            "wizard/legacy_character_system.md",
            ("legacy_generator", "set_designer"),
        ),
        PromptId.WIZARD_LEGACY_CHARACTER_USER: PromptSpec(
            "wizard/legacy_character_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(("SETTING_CONTEXT", "CHARACTER_CONCEPT")),
        ),
        PromptId.WIZARD_LEGACY_LOCATION_SYSTEM: PromptSpec(
            "wizard/legacy_location_system.md",
            ("legacy_generator", "set_designer"),
        ),
        PromptId.WIZARD_LEGACY_LOCATION_USER: PromptSpec(
            "wizard/legacy_location_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(
                (
                    "SETTING_WORLD_NAME",
                    "SETTING_TIME_PERIOD",
                    "SEED_TITLE",
                    "SEED_SITUATION",
                    "CHARACTER_NAME",
                )
            ),
        ),
        PromptId.WIZARD_LEGACY_SEED_SYSTEM: PromptSpec(
            "wizard/legacy_seed_system.md",
            ("legacy_generator", "set_designer"),
        ),
        PromptId.WIZARD_LEGACY_SEED_USER: PromptSpec(
            "wizard/legacy_seed_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(
                (
                    "SETTING_WORLD_NAME",
                    "SETTING_GENRE",
                    "CHARACTER_NAME",
                    "CHARACTER_SUMMARY",
                    "CHARACTER_BACKGROUND",
                    "CHARACTER_PERSONALITY",
                    "TRAITS_TEXT",
                    "WILDCARD_TEXT",
                    "SETTING_TONE",
                )
            ),
        ),
        PromptId.WIZARD_LEGACY_SETTING_SYSTEM: PromptSpec(
            "wizard/legacy_setting_system.md",
            ("legacy_generator", "set_designer"),
        ),
        PromptId.WIZARD_LEGACY_SETTING_USER: PromptSpec(
            "wizard/legacy_setting_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(("USER_PREFERENCES",)),
        ),
        PromptId.WIZARD_SEED_PHASE: PromptSpec(
            "wizard/seed_phase.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_SET_DESIGNER_USER: PromptSpec(
            "wizard/set_designer_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(
                (
                    "SETTING_WORLD_NAME",
                    "SETTING_GENRE_VALUE",
                    "SETTING_TIME_PERIOD",
                    "SETTING_TECH_LEVEL_VALUE",
                    "SETTING_GEOGRAPHIC_SCOPE",
                    "SETTING_TONE",
                    "SEED_TITLE",
                    "SEED_SEED_TYPE_VALUE",
                    "SEED_SITUATION",
                    "SEED_WEATHER_OR_NOT_SPECIFIED",
                    "LOCATION_SKETCH",
                )
            ),
        ),
        PromptId.WIZARD_SUBMIT_INSTRUCTION: PromptSpec(
            "wizard/submit_instruction.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_SUGGESTED_TRAITS_INSTRUCTION: PromptSpec(
            "wizard/suggested_traits_instruction.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_SUGGESTED_TRAITS_INTRO: PromptSpec(
            "wizard/suggested_traits_intro.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TOOL_SUBMIT_CHARACTER_CONCEPT: PromptSpec(
            "wizard/tools/submit_character_concept.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TOOL_SUBMIT_STARTING_SCENARIO: PromptSpec(
            "wizard/tools/submit_starting_scenario.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TOOL_SUBMIT_TRAIT_SELECTION: PromptSpec(
            "wizard/tools/submit_trait_selection.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TOOL_SUBMIT_WILDCARD_TRAIT: PromptSpec(
            "wizard/tools/submit_wildcard_trait.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TOOL_SUBMIT_WORLD_DOCUMENT: PromptSpec(
            "wizard/tools/submit_world_document.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
        ),
        PromptId.WIZARD_TRAIT_DERIVER_SYSTEM: PromptSpec(
            "wizard/trait_deriver_system.md", ("trait_input_derivation",)
        ),
    }
)

_PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
_TEMPLATE_LOCK = Lock()
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


@lru_cache(maxsize=None)
def _template(prompt_id: PromptId) -> str:
    spec = PROMPTS[prompt_id]
    path = _PROMPTS_ROOT / spec.path
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Prompt {prompt_id.value} is empty: {path}")
    found = frozenset(PLACEHOLDER.findall(text))
    if found != spec.placeholders:
        raise ValueError(
            f"Prompt {prompt_id.value} placeholder contract differs: "
            f"declared={sorted(spec.placeholders)}, found={sorted(found)}"
        )
    return text


def load(prompt_id: PromptId, **placeholders: object) -> str:
    """Render one cached document, rejecting missing and unknown substitutions.

    No stripping, dedenting, or trailing newline is added. Replacements happen
    in one pass so substituted user data is never interpreted as template text.
    File-not-found and contract errors deliberately propagate to the caller.
    """
    spec = PROMPTS[prompt_id]
    supplied = frozenset(placeholders)
    missing = spec.placeholders - supplied
    unknown = supplied - spec.placeholders
    if missing or unknown:
        raise ValueError(
            f"Prompt {prompt_id.value}: missing placeholders {sorted(missing)}; "
            f"unknown placeholders {sorted(unknown)}"
        )
    # Serialize cache misses as well as hits: simultaneous first readers must
    # not each open the same file (lru_cache alone permits duplicate misses).
    with _TEMPLATE_LOCK:
        template = _template(prompt_id)
    return PLACEHOLDER.sub(lambda match: str(placeholders[match.group(1)]), template)

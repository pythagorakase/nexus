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
    CORRESPONDENCE_PRIVACY = "correspondence/privacy"
    EXPERIENCE_RENDERER = "experience_renderer"
    GEO_AUTHORING = "orrery/geo_authoring"
    OPERATORS_ESTIMATE_TIME_DELTA_SYSTEM = "operators/estimate_time_delta_system"
    OPERATORS_ESTIMATE_TIME_DELTA_USER = "operators/estimate_time_delta_user"
    OPERATORS_FACTION_CHARACTER_SYSTEM = "operators/faction_character_system"
    OPERATORS_FACTION_CHARACTER_USER = "operators/faction_character_user"
    OPERATORS_FACTION_RELATIONSHIP_SYSTEM = "operators/faction_relationship_system"
    OPERATORS_FACTION_RELATIONSHIP_USER = "operators/faction_relationship_user"
    OPERATORS_FREESTYLE_SYSTEM = "operators/freestyle_system"
    OPERATORS_FREESTYLE_USER = "operators/freestyle_user"
    OPERATORS_MAP_BUILDER = "operators/map_builder"
    OPERATORS_MAP_BUILDER_JSON_REMINDER = "operators/map_builder_json_reminder"
    OPERATORS_MAP_BUILDER_SCHEMA = "operators/map_builder_schema"
    OPERATORS_PROCESS_CHARACTERS = "operators/process_characters"
    OPERATORS_PROCESS_FACTIONS = "operators/process_factions"
    OPERATORS_RETRIEVAL_QUERY_BAKEOFF = "operators/retrieval_query_bakeoff"
    OPERATORS_RETRIEVAL_QUERY_SYSTEM = "operators/retrieval_query_system"
    ORRERY_PRESSURE_HUNGER = "orrery/pressure_hunger"
    ORRERY_PRESSURE_INTIMACY = "orrery/pressure_intimacy"
    ORRERY_PRESSURE_SLEEP = "orrery/pressure_sleep"
    ORRERY_PRESSURE_SOCIALIZE = "orrery/pressure_socialize"
    ORRERY_PRESSURE_THIRST = "orrery/pressure_thirst"
    ORRERY_SCENE_PRESSURE_ACCOMPANIMENT = "orrery/scene_pressure/accompaniment"
    ORRERY_SCENE_PRESSURE_AFFECTION = "orrery/scene_pressure/affection"
    ORRERY_SCENE_PRESSURE_ARRIVAL = "orrery/scene_pressure/arrival"
    ORRERY_SCENE_PRESSURE_CONFRONTATION = "orrery/scene_pressure/confrontation"
    ORRERY_SCENE_PRESSURE_CONTEMPLATION = "orrery/scene_pressure/contemplation"
    ORRERY_SCENE_PRESSURE_CONVERSATION = "orrery/scene_pressure/conversation"
    ORRERY_SCENE_PRESSURE_FIRST_AID = "orrery/scene_pressure/first_aid"
    ORRERY_SCENE_PRESSURE_GRUDGE = "orrery/scene_pressure/grudge"
    ORRERY_SCENE_PRESSURE_HELD_CONTACT = "orrery/scene_pressure/held_contact"
    ORRERY_SCENE_PRESSURE_INTEL = "orrery/scene_pressure/intel"
    ORRERY_SCENE_PRESSURE_INTERMEDIARY = "orrery/scene_pressure/intermediary"
    ORRERY_SCENE_PRESSURE_INTERVENE = "orrery/scene_pressure/intervene"
    ORRERY_SCENE_PRESSURE_NO_CONTACT = "orrery/scene_pressure/no_contact"
    ORRERY_SCENE_PRESSURE_OVERTURE = "orrery/scene_pressure/overture"
    ORRERY_SCENE_PRESSURE_PASSIVE_OVERTURE = "orrery/scene_pressure/passive_overture"
    ORRERY_SCENE_PRESSURE_PUBLIC_PATTERN = "orrery/scene_pressure/public_pattern"
    ORRERY_SCENE_PRESSURE_RESTORATION = "orrery/scene_pressure/restoration"
    ORRERY_SCENE_PRESSURE_RIVAL_MEETING = "orrery/scene_pressure/rival_meeting"
    ORRERY_SCENE_PRESSURE_SIGNALS = "orrery/scene_pressure/signals"
    ORRERY_SCENE_PRESSURE_SILENT_VIGIL = "orrery/scene_pressure/silent_vigil"
    ORRERY_SCENE_PRESSURE_SPEAKING_VIGIL = "orrery/scene_pressure/speaking_vigil"
    ORRERY_SCENE_PRESSURE_SURVEILLANCE = "orrery/scene_pressure/surveillance"
    ORRERY_SCENE_PRESSURE_WELFARE = "orrery/scene_pressure/welfare"
    OUTPUT_FORMAT_GUIDE = "output/format_guide"
    OUTPUT_STRUCTURED_TOOL = "output/structured_tool"
    RETROGRADE_ABSENT_SUPPORTING_FIELDS = "retrograde/absent_supporting_fields"
    RETROGRADE_EVENT_TYPE_HINT = "retrograde/event_type_hint"
    RETROGRADE_EXPANSION = "retrograde/expansion"
    RETROGRADE_EXPANSION_CONSTRAINTS = "retrograde/expansion_constraints"
    RETROGRADE_EXPANSION_RETRY = "retrograde/expansion_retry"
    RETROGRADE_EXPANSION_SYSTEM = "retrograde/expansion_system"
    RETROGRADE_EXPANSION_TASK = "retrograde/expansion_task"
    RETROGRADE_GENERATION_CONSTRAINTS = "retrograde/generation_constraints"
    RETROGRADE_GENERATION_RETRY = "retrograde/generation_retry"
    RETROGRADE_GENERATION_SYSTEM = "retrograde/generation_system"
    RETROGRADE_GENERATION_TASK = "retrograde/generation_task"
    RETROGRADE_INTENT_TARGET_REFS = "retrograde/intent_target_refs"
    RETROGRADE_MATURATION_BUDGET = "retrograde/maturation_budget"
    RETROGRADE_MATURATION_DIRECTIVE = "retrograde/maturation_directive"
    RETROGRADE_MATURATION_TARGET = "retrograde/maturation_target"
    RETROGRADE_MATURATION_WEIGHT = "retrograde/maturation_weight"
    RETROGRADE_MECHANICAL_TAG_RULES = "retrograde/mechanical_tag_rules"
    RETROGRADE_PAIR_TAG_RULE = "retrograde/pair_tag_rule"
    RETROGRADE_RELATIONSHIP_HINT = "retrograde/relationship_hint"
    RETROGRADE_RELATIONSHIP_TYPE_RETRY = "retrograde/relationship_type_retry"
    RETROGRADE_REVIEW_CONTRACT = "retrograde/review_contract"
    RETROGRADE_SEED_GENERATION = "retrograde/seed_generation"
    RETROGRADE_SEED_SELECTION = "retrograde/seed_selection"
    RETROGRADE_SELECTION_PRIORITIES = "retrograde/selection_priorities"
    RETROGRADE_SELECTION_SYSTEM = "retrograde/selection_system"
    RETROGRADE_SELECTION_TASK = "retrograde/selection_task"
    RETROGRADE_SINGLE_ENTITY_TAG_HINT = "retrograde/single_entity_tag_hint"
    RETROGRADE_UNUSED_PLAN_FIELDS = "retrograde/unused_plan_fields"
    RETROGRADE_WEAVER_INSTRUCTIONS = "retrograde/weaver_instructions"
    RETRY_CLOSED_REGISTRY = "retry/closed_registry"
    RETRY_FACTION_DECLARATION_ALLOWED = "retry/faction_declaration_allowed"
    RETRY_FACTION_DECLARATION_DISABLED = "retry/faction_declaration_disabled"
    RETRY_FACTION_EXACT_NAME = "retry/faction_exact_name"
    RETRY_FACTION_NEW_NAME = "retry/faction_new_name"
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
    WIZARD_CANONICAL_FAME = "wizard/canonical_fame"
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
    WIZARD_WILDCARD_TAG_RETRY = "wizard/wildcard_tag_retry"


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
        PromptId.CORRESPONDENCE_PRIVACY: PromptSpec(
            "correspondence/privacy.md",
            ("skald_writer", "gaia", "correspondence_compaction"),
            frozenset(()),
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
        PromptId.OPERATORS_FACTION_CHARACTER_SYSTEM: PromptSpec(
            "operators/faction_character_system.md",
            ("legacy_operator",),
            frozenset(("VALUE_1",)),
        ),
        PromptId.OPERATORS_FACTION_CHARACTER_USER: PromptSpec(
            "operators/faction_character_user.md",
            ("legacy_operator",),
            frozenset(
                (
                    "VALUE_1",
                    "VALUE_2",
                    "VALUE_3",
                    "VALUE_4",
                    "VALUE_5",
                    "VALUE_6",
                    "VALUE_7",
                )
            ),
        ),
        PromptId.OPERATORS_FACTION_RELATIONSHIP_SYSTEM: PromptSpec(
            "operators/faction_relationship_system.md",
            ("legacy_operator",),
            frozenset(("VALUE_1",)),
        ),
        PromptId.OPERATORS_FACTION_RELATIONSHIP_USER: PromptSpec(
            "operators/faction_relationship_user.md",
            ("legacy_operator",),
            frozenset(
                (
                    "VALUE_1",
                    "VALUE_2",
                    "VALUE_3",
                    "VALUE_4",
                    "VALUE_5",
                    "VALUE_6",
                    "VALUE_7",
                )
            ),
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
        PromptId.OPERATORS_MAP_BUILDER_JSON_REMINDER: PromptSpec(
            "operators/map_builder_json_reminder.md",
            ("legacy_operator",),
            frozenset(()),
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
        PromptId.OPERATORS_RETRIEVAL_QUERY_SYSTEM: PromptSpec(
            "operators/retrieval_query_system.md",
            ("retrieval_query_bakeoff",),
            frozenset(()),
        ),
        PromptId.ORRERY_PRESSURE_HUNGER: PromptSpec(
            "orrery/pressure_hunger.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(("LABEL", "DEBT_SCORE")),
        ),
        PromptId.ORRERY_PRESSURE_INTIMACY: PromptSpec(
            "orrery/pressure_intimacy.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(("LABEL", "DEBT_SCORE")),
        ),
        PromptId.ORRERY_PRESSURE_SLEEP: PromptSpec(
            "orrery/pressure_sleep.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(("LABEL", "DEBT_SCORE")),
        ),
        PromptId.ORRERY_PRESSURE_SOCIALIZE: PromptSpec(
            "orrery/pressure_socialize.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(("LABEL", "DEBT_SCORE")),
        ),
        PromptId.ORRERY_PRESSURE_THIRST: PromptSpec(
            "orrery/pressure_thirst.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(("LABEL", "DEBT_SCORE")),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_ACCOMPANIMENT: PromptSpec(
            "orrery/scene_pressure/accompaniment.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_AFFECTION: PromptSpec(
            "orrery/scene_pressure/affection.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_ARRIVAL: PromptSpec(
            "orrery/scene_pressure/arrival.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_CONFRONTATION: PromptSpec(
            "orrery/scene_pressure/confrontation.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_CONTEMPLATION: PromptSpec(
            "orrery/scene_pressure/contemplation.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_CONVERSATION: PromptSpec(
            "orrery/scene_pressure/conversation.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_FIRST_AID: PromptSpec(
            "orrery/scene_pressure/first_aid.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_GRUDGE: PromptSpec(
            "orrery/scene_pressure/grudge.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_HELD_CONTACT: PromptSpec(
            "orrery/scene_pressure/held_contact.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_INTEL: PromptSpec(
            "orrery/scene_pressure/intel.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_INTERMEDIARY: PromptSpec(
            "orrery/scene_pressure/intermediary.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_INTERVENE: PromptSpec(
            "orrery/scene_pressure/intervene.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_NO_CONTACT: PromptSpec(
            "orrery/scene_pressure/no_contact.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_OVERTURE: PromptSpec(
            "orrery/scene_pressure/overture.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_PASSIVE_OVERTURE: PromptSpec(
            "orrery/scene_pressure/passive_overture.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_PUBLIC_PATTERN: PromptSpec(
            "orrery/scene_pressure/public_pattern.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_RESTORATION: PromptSpec(
            "orrery/scene_pressure/restoration.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_RIVAL_MEETING: PromptSpec(
            "orrery/scene_pressure/rival_meeting.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_SIGNALS: PromptSpec(
            "orrery/scene_pressure/signals.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_SILENT_VIGIL: PromptSpec(
            "orrery/scene_pressure/silent_vigil.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_SPEAKING_VIGIL: PromptSpec(
            "orrery/scene_pressure/speaking_vigil.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_SURVEILLANCE: PromptSpec(
            "orrery/scene_pressure/surveillance.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.ORRERY_SCENE_PRESSURE_WELFARE: PromptSpec(
            "orrery/scene_pressure/welfare.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.OUTPUT_FORMAT_GUIDE: PromptSpec(
            "output/format_guide.md",
            ("skald_writer", "gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.OUTPUT_STRUCTURED_TOOL: PromptSpec(
            "output/structured_tool.md", ("all",), frozenset(())
        ),
        PromptId.RETROGRADE_ABSENT_SUPPORTING_FIELDS: PromptSpec(
            "retrograde/absent_supporting_fields.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_EVENT_TYPE_HINT: PromptSpec(
            "retrograde/event_type_hint.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
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
        PromptId.RETROGRADE_INTENT_TARGET_REFS: PromptSpec(
            "retrograde/intent_target_refs.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_MATURATION_BUDGET: PromptSpec(
            "retrograde/maturation_budget.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_MATURATION_DIRECTIVE: PromptSpec(
            "retrograde/maturation_directive.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(("ROW_ENTITY_NAME", "ROW_ENTITY_KIND")),
        ),
        PromptId.RETROGRADE_MATURATION_TARGET: PromptSpec(
            "retrograde/maturation_target.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_MATURATION_WEIGHT: PromptSpec(
            "retrograde/maturation_weight.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_MECHANICAL_TAG_RULES: PromptSpec(
            "retrograde/mechanical_tag_rules.md", ("retrograde_seed_candidates",)
        ),
        PromptId.RETROGRADE_PAIR_TAG_RULE: PromptSpec(
            "retrograde/pair_tag_rule.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_RELATIONSHIP_HINT: PromptSpec(
            "retrograde/relationship_hint.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_RELATIONSHIP_TYPE_RETRY: PromptSpec(
            "retrograde/relationship_type_retry.md",
            ("retrograde_expansion",),
            frozenset(
                (
                    "REDEMPTION_SEED_IDS",
                    "INDEX",
                    "RELATIONSHIP_RELATIONSHIP_TYPE",
                    "EXC",
                    "SORTED_RELATIONSHIP_TYPES",
                )
            ),
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
            "retrograde/selection_priorities.md", ("retrograde_seed_selection",)
        ),
        PromptId.RETROGRADE_SELECTION_SYSTEM: PromptSpec(
            "retrograde/selection_system.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_SELECTION_TASK: PromptSpec(
            "retrograde/selection_task.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
        ),
        PromptId.RETROGRADE_SINGLE_ENTITY_TAG_HINT: PromptSpec(
            "retrograde/single_entity_tag_hint.md",
            ("retrograde_seed_candidates", "retrograde_seed_selection"),
            frozenset(()),
        ),
        PromptId.RETROGRADE_UNUSED_PLAN_FIELDS: PromptSpec(
            "retrograde/unused_plan_fields.md", ("retrograde_expansion",), frozenset(())
        ),
        PromptId.RETROGRADE_WEAVER_INSTRUCTIONS: PromptSpec(
            "retrograde/weaver_instructions.md", ("retrograde_seed_candidates",)
        ),
        PromptId.RETRY_CLOSED_REGISTRY: PromptSpec(
            "retry/closed_registry.md",
            ("gaia", "skald_single_pass"),
            frozenset(("DECLARATION_GUIDANCE", "FORMATTED")),
        ),
        PromptId.RETRY_FACTION_DECLARATION_ALLOWED: PromptSpec(
            "retry/faction_declaration_allowed.md",
            ("gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.RETRY_FACTION_DECLARATION_DISABLED: PromptSpec(
            "retry/faction_declaration_disabled.md",
            ("gaia", "skald_single_pass"),
            frozenset(()),
        ),
        PromptId.RETRY_FACTION_EXACT_NAME: PromptSpec(
            "retry/faction_exact_name.md", ("gaia", "skald_single_pass"), frozenset(())
        ),
        PromptId.RETRY_FACTION_NEW_NAME: PromptSpec(
            "retry/faction_new_name.md", ("gaia", "skald_single_pass"), frozenset(())
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
            "turn_blocks/authors_note.md", ("skald_writer", "gaia", "skald_single_pass")
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
            "turn_blocks/joint_beats.md", ("skald_writer", "gaia", "skald_single_pass")
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
            "wizard/accept_fate.md", ("wizard", "wizard_wildcard", "wizard_debug")
        ),
        PromptId.WIZARD_ACCEPT_FATE_RETRY: PromptSpec(
            "wizard/accept_fate_retry.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
            frozenset(("TOOL_NAME",)),
        ),
        PromptId.WIZARD_CANONICAL_FAME: PromptSpec(
            "wizard/canonical_fame.md", ("trait_input_derivation",), frozenset(())
        ),
        PromptId.WIZARD_CHARACTER_PHASE: PromptSpec(
            "wizard/character_phase.md", ("wizard", "wizard_wildcard", "wizard_debug")
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
            "wizard/legacy_character_system.md", ("legacy_generator", "set_designer")
        ),
        PromptId.WIZARD_LEGACY_CHARACTER_USER: PromptSpec(
            "wizard/legacy_character_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(("SETTING_CONTEXT", "CHARACTER_CONCEPT")),
        ),
        PromptId.WIZARD_LEGACY_LOCATION_SYSTEM: PromptSpec(
            "wizard/legacy_location_system.md", ("legacy_generator", "set_designer")
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
            "wizard/legacy_seed_system.md", ("legacy_generator", "set_designer")
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
            "wizard/legacy_setting_system.md", ("legacy_generator", "set_designer")
        ),
        PromptId.WIZARD_LEGACY_SETTING_USER: PromptSpec(
            "wizard/legacy_setting_user.md",
            ("legacy_generator", "set_designer"),
            frozenset(("USER_PREFERENCES",)),
        ),
        PromptId.WIZARD_SEED_PHASE: PromptSpec(
            "wizard/seed_phase.md", ("wizard", "wizard_wildcard", "wizard_debug")
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
        PromptId.WIZARD_WILDCARD_TAG_RETRY: PromptSpec(
            "wizard/wildcard_tag_retry.md",
            ("wizard", "wizard_wildcard", "wizard_debug"),
            frozenset(("FORMATTED",)),
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

"""Skald-facing Retrograde R6 expansion plan schema and validation."""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.agents.orrery.retrograde_seed_candidates import (
    validate_seed_candidate_response,
)
from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary

ExpansionSchemaVersion = Literal["orrery_retrograde_expansion_plan.v0"]
RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION: ExpansionSchemaVersion = (
    "orrery_retrograde_expansion_plan.v0"
)
RETROGRADE_COMMIT_BLOCKERS: tuple[dict[str, str], ...] = (
    {
        "id": "pre_game_tick_chunk_id",
        "reason": (
            "world_events.tick_chunk_id is currently NOT NULL and references "
            "narrative_chunks(id); Retrograde needs a wizard-time anchor before "
            "canonical event writes are legal."
        ),
    },
    {
        "id": "event_source_kind_retrograde",
        "reason": (
            "event_source_kind does not yet include 'retrograde'; using "
            "'authored' would conflate generated setup history with hand-authored "
            "content."
        ),
    },
)


class RetrogradeExpansionValidationError(ValueError):
    """Raised when an R6 expansion plan is shaped correctly but illegal."""


class RetrogradeExpansionParticipant(BaseModel):
    """One entity reference participating in a planned Retrograde event."""

    entity_ref: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    role: Literal["actor", "target", "observer", "beneficiary", "witness"] = Field(
        default="observer"
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionEventPlan(BaseModel):
    """One future world_events row, without database ids or tick anchor."""

    event_ref: str = Field(
        min_length=1,
        description="Expansion-local stable event identifier.",
    )
    seed_ids: list[str] = Field(
        min_length=1,
        description="Selected seed ids this planned event weaves together.",
    )
    event_type: str = Field(
        min_length=1,
        description="Registered Orrery event type.",
    )
    summary: str = Field(
        min_length=1,
        max_length=900,
        description="Concise event prose suitable for future world_events payload.",
    )
    chronology: Literal["deep_past", "recent_past", "opening_pressure"] = Field(
        description="Relative placement before the first narrative chunk."
    )
    participants: list[RetrogradeExpansionParticipant] = Field(default_factory=list)
    location_ref: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Prompt-local place ref for future location_id resolution.",
    )
    changed_fields: list[str] = Field(
        default_factory=list,
        description="Future world_events.changed_fields entries.",
    )
    magnitude: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Optional future world_events.magnitude value.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Small future world_events.payload sketch.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionEntityTagPlan(BaseModel):
    """One future entity_tags write implied by the woven history."""

    entity_ref: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    source_event_ref: Optional[str] = Field(
        default=None,
        description=(
            "Required for event-anchored tags; references event_plan.event_ref."
        ),
    )
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionPairTagPlan(BaseModel):
    """One future entity_pair_tags write implied by the woven history."""

    subject_ref: str = Field(min_length=1)
    subject_kind: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    object_kind: str = Field(min_length=1)
    source_event_ref: Optional[str] = Field(default=None)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionRelationshipPlan(BaseModel):
    """One future relationship-table write implied by the woven history."""

    subject_ref: str = Field(min_length=1)
    subject_kind: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    object_kind: str = Field(min_length=1)
    source_event_ref: Optional[str] = Field(default=None)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionThreadPlan(BaseModel):
    """Accounting for one selected seed after R6 weaving."""

    seed_id: str = Field(min_length=1)
    status: Literal["woven", "deferred", "rejected"] = Field(
        description="Whether the selected seed survived expansion."
    )
    event_refs: list[str] = Field(default_factory=list)
    present_leaf_anchor: str = Field(
        min_length=1,
        max_length=900,
        description="Concrete connection back to present canon or rejection reason.",
    )
    note: Optional[str] = Field(default=None, max_length=700)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionCommitReadiness(BaseModel):
    """Why this R6 output is still dry-run instead of canonical writes."""

    writes: Literal["none"] = "none"
    planned_source: Literal["retrograde"] = "retrograde"
    blocked_by: list[str] = Field(
        default_factory=lambda: [
            blocker["id"] for blocker in RETROGRADE_COMMIT_BLOCKERS
        ]
    )
    explanation: str = Field(
        default=(
            "Expansion produces future row-shaped plans only. Canonical writes "
            "wait for a pre-game tick anchor, a retrograde event source enum, "
            "idempotency policy, and transaction semantics."
        )
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionPlanResponse(BaseModel):
    """Structured R6 response from Skald-as-weaver."""

    schema_version: ExpansionSchemaVersion = (
        RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION
    )
    selected_seed_ids: list[str] = Field(
        min_length=1,
        description="Selected seed ids considered by this expansion.",
    )
    event_plan: list[RetrogradeExpansionEventPlan] = Field(default_factory=list)
    entity_tag_plan: list[RetrogradeExpansionEntityTagPlan] = Field(
        default_factory=list
    )
    pair_tag_plan: list[RetrogradeExpansionPairTagPlan] = Field(default_factory=list)
    relationship_plan: list[RetrogradeExpansionRelationshipPlan] = Field(
        default_factory=list
    )
    thread_plan: list[RetrogradeExpansionThreadPlan] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    commit_readiness: RetrogradeExpansionCommitReadiness = Field(
        default_factory=RetrogradeExpansionCommitReadiness
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="after")
    def _validate_expansion_id_sets(self) -> "RetrogradeExpansionPlanResponse":
        duplicate_seed_ids = _duplicates(self.selected_seed_ids)
        if duplicate_seed_ids:
            raise ValueError(
                f"Duplicate selected_seed_ids: {sorted(duplicate_seed_ids)}"
            )
        duplicate_event_refs = _duplicates(
            [event.event_ref for event in self.event_plan]
        )
        if duplicate_event_refs:
            raise ValueError(
                f"Duplicate event_ref values: {sorted(duplicate_event_refs)}"
            )
        duplicate_threads = _duplicates([thread.seed_id for thread in self.thread_plan])
        if duplicate_threads:
            raise ValueError(
                f"Duplicate thread_plan seed_id values: {duplicate_threads}"
            )
        return self


def expansion_response_schema() -> dict[str, Any]:
    """Return the Pydantic JSON schema for R6 expansion responses."""

    return RetrogradeExpansionPlanResponse.model_json_schema()


def render_expansion_prompt(
    *,
    packet: Mapping[str, Any],
    seed_candidate_response: Mapping[str, Any],
) -> str:
    """Render a deterministic Skald prompt for non-mutating R6 expansion."""

    seed_generation_request = _required_mapping(
        packet.get("seed_generation_request"),
        "packet.seed_generation_request",
    )
    vocabulary = _seed_vocabulary(packet.get("seed_eligible_vocabulary"))
    candidates = validate_seed_candidate_response(
        payload=seed_candidate_response,
        seed_generation_request=seed_generation_request,
        vocabulary=vocabulary,
    )
    selected_candidates = [
        candidate.model_dump(mode="json")
        for candidate in candidates.candidates
        if candidate.seed_id in set(candidates.selected_seed_ids)
    ]
    prompt_payload = {
        "task": (
            "Weave selected Retrograde seed candidates into a compact, coherent "
            "R6 expansion plan. Do not write canon. Return JSON only."
        ),
        "mutation_policy": {
            "writes": "none",
            "reason": "R6 expansion remains dry-run until commit blockers resolve.",
        },
        "commit_blockers": list(RETROGRADE_COMMIT_BLOCKERS),
        "budget": seed_generation_request.get("budget", {}),
        "selected_seed_ids": candidates.selected_seed_ids,
        "selected_candidates": selected_candidates,
        "core_prompt_sections": (
            seed_generation_request.get("prompt_sections", [])[:4]
        ),
        "allowed_vocabulary": _prompt_vocabulary(vocabulary),
        "hard_validation_rules": _hard_validation_rules(),
        "response_contract": _prompt_response_contract(),
    }
    return (
        "You are Skald-as-weaver for Retrograde R6 expansion.\n"
        "Weave the selected seeds into a sparse history web with row-shaped "
        "event/tag/relationship plans, but do not claim canonical persistence.\n"
        "Every selected seed must be accounted for as woven, deferred, or "
        "rejected. Every woven thread must terminate in a present leaf anchor.\n"
        "If a mechanical plan cannot satisfy the hard validation rules, omit "
        "that mechanical item or reject/defer the seed.\n"
        "Return JSON only.\n\n"
        "RETROGRADE_EXPANSION_REQUEST:\n"
        f"{json.dumps(prompt_payload, indent=2, sort_keys=True)}"
    )


def validate_expansion_plan(
    *,
    payload: Mapping[str, Any],
    packet: Mapping[str, Any],
    seed_candidate_response: Mapping[str, Any],
) -> RetrogradeExpansionPlanResponse:
    """Validate a Skald R6 expansion plan against selected seeds and vocabulary."""

    seed_generation_request = _required_mapping(
        packet.get("seed_generation_request"),
        "packet.seed_generation_request",
    )
    vocabulary = _seed_vocabulary(packet.get("seed_eligible_vocabulary"))
    candidates = validate_seed_candidate_response(
        payload=seed_candidate_response,
        seed_generation_request=seed_generation_request,
        vocabulary=vocabulary,
    )
    response = RetrogradeExpansionPlanResponse.model_validate(payload)
    issues = _expansion_contract_issues(
        response=response,
        selected_seed_ids=set(candidates.selected_seed_ids),
        vocabulary=vocabulary,
        known_entity_keys=_packet_known_entity_keys(packet),
        max_new_entity_stubs=_budget_entity_stub_cap(seed_generation_request),
    )
    if issues:
        formatted = "\n".join(f"- {issue}" for issue in issues)
        raise RetrogradeExpansionValidationError(formatted)
    return response


def generate_expansion_with_skald(
    *,
    packet: Mapping[str, Any],
    seed_candidate_response: Mapping[str, Any],
    model_name: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict[str, Any]:
    """Make a non-mutating Skald call to weave selected seeds into an R6 plan."""

    from pydantic_ai import Agent, ModelRetry, RunContext
    from pydantic_ai.settings import ModelSettings

    from nexus.api.config_utils import (
        get_new_story_model,
        get_wizard_max_tokens,
        get_wizard_retry_budget,
    )
    from nexus.api.pydantic_ai_utils import build_pydantic_ai_model

    prompt = render_expansion_prompt(
        packet=packet,
        seed_candidate_response=seed_candidate_response,
    )
    selected_model = model_name or get_new_story_model()
    agent = Agent(
        model=build_pydantic_ai_model(selected_model),
        output_type=RetrogradeExpansionPlanResponse,
        system_prompt=(
            "You are Skald-as-weaver for a NEXUS Retrograde expansion pass. "
            "Return a non-mutating expansion plan only."
        ),
        model_settings=ModelSettings(max_tokens=max_tokens or get_wizard_max_tokens()),
        retries=get_wizard_retry_budget(),
    )

    async def _validate_output(
        _ctx: RunContext[None],
        output: RetrogradeExpansionPlanResponse,
    ) -> RetrogradeExpansionPlanResponse:
        try:
            return validate_expansion_plan(
                payload=output.model_dump(mode="json"),
                packet=packet,
                seed_candidate_response=seed_candidate_response,
            )
        except RetrogradeExpansionValidationError as exc:
            raise ModelRetry(
                "Retrograde expansion plan failed validation. Repair the JSON "
                "by omitting invalid mechanics, accounting for every selected "
                f"seed, or adding required refs:\n{exc}"
            ) from exc

    agent.output_validator(_validate_output)
    result = agent.run_sync(prompt)
    response = result.output
    if not isinstance(response, RetrogradeExpansionPlanResponse):
        raise TypeError(
            "Skald expansion call returned "
            f"{type(response).__name__}, expected RetrogradeExpansionPlanResponse"
        )

    return {
        "model": selected_model,
        "prompt_chars": len(prompt),
        "retrograde_expansion_plan": response.model_dump(mode="json"),
    }


def _expansion_contract_issues(
    *,
    response: RetrogradeExpansionPlanResponse,
    selected_seed_ids: set[str],
    vocabulary: SeedEligibleVocabulary,
    known_entity_keys: Optional[set[tuple[str, str]]] = None,
    max_new_entity_stubs: Optional[int] = None,
) -> list[str]:
    issues: list[str] = []
    issues.extend(
        _new_entity_budget_issues(
            response=response,
            known_entity_keys=known_entity_keys or set(),
            max_new_entity_stubs=max_new_entity_stubs,
        )
    )
    response_seed_ids = set(response.selected_seed_ids)
    unknown_response_seeds = sorted(response_seed_ids - selected_seed_ids)
    if unknown_response_seeds:
        issues.append(
            "expansion selected_seed_ids include non-selected seeds "
            f"{unknown_response_seeds}"
        )
    missing_response_seeds = sorted(selected_seed_ids - response_seed_ids)
    if missing_response_seeds:
        issues.append(
            "expansion selected_seed_ids omit selected seeds "
            f"{missing_response_seeds}"
        )

    event_refs = {event.event_ref for event in response.event_plan}
    event_types = set(vocabulary["event_types"])
    entity_kinds = set(vocabulary["entity_kinds"])
    relationship_types = set(vocabulary["relationship_types"])
    pair_definitions = {
        definition["tag"]: definition
        for definition in vocabulary["multi_entity_tag_definitions"]
    }
    registered_tags = set(vocabulary["registered_single_entity_tags"])
    tags_by_seed_policy = {
        policy: set(tags)
        for policy, tags in vocabulary.get("registered_tags_by_seed_policy", {}).items()
    }

    for event in response.event_plan:
        issues.extend(
            _event_plan_issues(
                event=event,
                selected_seed_ids=selected_seed_ids,
                event_types=event_types,
                entity_kinds=entity_kinds,
            )
        )

    for tag_plan in response.entity_tag_plan:
        issues.extend(
            _entity_tag_plan_issues(
                tag_plan=tag_plan,
                entity_kinds=entity_kinds,
                registered_tags=registered_tags,
                tags_by_seed_policy=tags_by_seed_policy,
                event_refs=event_refs,
            )
        )

    for pair_plan in response.pair_tag_plan:
        issues.extend(
            _pair_tag_plan_issues(
                pair_plan=pair_plan,
                entity_kinds=entity_kinds,
                pair_definitions=pair_definitions,
                event_refs=event_refs,
            )
        )

    for relationship_plan in response.relationship_plan:
        issues.extend(
            _relationship_plan_issues(
                relationship_plan=relationship_plan,
                entity_kinds=entity_kinds,
                relationship_types=relationship_types,
                event_refs=event_refs,
            )
        )

    issues.extend(
        _thread_plan_issues(
            thread_plan=response.thread_plan,
            selected_seed_ids=selected_seed_ids,
            event_refs=event_refs,
        )
    )
    issues.extend(_commit_readiness_issues(response.commit_readiness))
    return issues


STUB_CREATABLE_ENTITY_KINDS = frozenset({"character", "place", "faction"})


def _new_entity_budget_issues(
    *,
    response: RetrogradeExpansionPlanResponse,
    known_entity_keys: set[tuple[str, str]],
    max_new_entity_stubs: Optional[int],
) -> list[str]:
    """Enforce the Decision 8 entity-coverage cap against plan entity refs."""

    if max_new_entity_stubs is None:
        return []
    new_keys = sorted(
        key
        for key in _collect_plan_entity_keys(response)
        if key[0] in STUB_CREATABLE_ENTITY_KINDS and key not in known_entity_keys
    )
    if len(new_keys) <= max_new_entity_stubs:
        return []
    listed = ", ".join(f"{kind}:{ref}" for kind, ref in new_keys)
    return [
        f"expansion introduces {len(new_keys)} entities beyond the first-class "
        f"starting set, exceeding budget.max_new_entity_stubs="
        f"{max_new_entity_stubs}: {listed}. Drop or merge minor entities, or "
        "reattach their threads to first-class starting entities."
    ]


def _collect_plan_entity_keys(
    response: RetrogradeExpansionPlanResponse,
) -> set[tuple[str, str]]:
    """Collect distinct (kind, normalized ref) keys across all plan sections."""

    keys: set[tuple[str, str]] = set()
    for event in response.event_plan:
        for participant in event.participants:
            keys.add(
                (participant.entity_kind, _normalize_entity_ref(participant.entity_ref))
            )
        if event.location_ref:
            keys.add(("place", _normalize_entity_ref(event.location_ref)))
    for tag_plan in response.entity_tag_plan:
        keys.add((tag_plan.entity_kind, _normalize_entity_ref(tag_plan.entity_ref)))
    for pair_plan in response.pair_tag_plan:
        keys.add((pair_plan.subject_kind, _normalize_entity_ref(pair_plan.subject_ref)))
        keys.add((pair_plan.object_kind, _normalize_entity_ref(pair_plan.object_ref)))
    for relationship in response.relationship_plan:
        keys.add(
            (relationship.subject_kind, _normalize_entity_ref(relationship.subject_ref))
        )
        keys.add(
            (relationship.object_kind, _normalize_entity_ref(relationship.object_ref))
        )
    return keys


def _packet_known_entity_keys(packet: Mapping[str, Any]) -> set[tuple[str, str]]:
    """First-class starting entity keys known to the Retrograde packet.

    Reads both the top-level candidate scaffolds (full dry-run packets) and
    the seed request prompt sections (always present in loadable packets), so
    saved or compacted packets keep the same first-class entity surface.
    """

    keys: set[tuple[str, str]] = set()

    def add_card(card: Any) -> None:
        if not isinstance(card, Mapping):
            return
        kind = card.get("kind")
        name = card.get("name")
        if kind in STUB_CREATABLE_ENTITY_KINDS and name:
            keys.add((str(kind), _normalize_entity_ref(str(name))))

    scaffolds = packet.get("candidate_scaffolds")
    if isinstance(scaffolds, Mapping):
        for card in scaffolds.get("core_entities") or ():
            add_card(card)
        for npc in scaffolds.get("named_seed_npcs") or ():
            add_card(npc)

    seed_generation_request = packet.get("seed_generation_request")
    if isinstance(seed_generation_request, Mapping):
        for section in seed_generation_request.get("prompt_sections") or ():
            if not isinstance(section, Mapping):
                continue
            if section.get("heading") not in {"Core entities", "Named seed NPCs"}:
                continue
            for card in section.get("items") or ():
                add_card(card)
    return keys


def _budget_entity_stub_cap(
    seed_generation_request: Mapping[str, Any],
) -> Optional[int]:
    """Read the optional Decision 8 stub cap from the request budget."""

    budget = seed_generation_request.get("budget")
    if not isinstance(budget, Mapping):
        return None
    cap = budget.get("max_new_entity_stubs")
    if cap is None:
        return None
    return int(cap)


def _normalize_entity_ref(value: str) -> str:
    """Match the persistence layer's prompt-local ref normalization."""

    return " ".join(value.split()).casefold()


def _event_plan_issues(
    *,
    event: RetrogradeExpansionEventPlan,
    selected_seed_ids: set[str],
    event_types: set[str],
    entity_kinds: set[str],
) -> list[str]:
    issues: list[str] = []
    prefix = f"event {event.event_ref!r}"
    unknown_seed_ids = sorted(set(event.seed_ids) - selected_seed_ids)
    if unknown_seed_ids:
        issues.append(f"{prefix} references non-selected seeds {unknown_seed_ids}")
    if event.event_type not in event_types:
        issues.append(f"{prefix} uses unknown event_type {event.event_type!r}")
    for participant in event.participants:
        if participant.entity_kind not in entity_kinds:
            issues.append(
                f"{prefix} participant {participant.entity_ref!r} uses unknown "
                f"entity_kind {participant.entity_kind!r}"
            )
    return issues


def _entity_tag_plan_issues(
    *,
    tag_plan: RetrogradeExpansionEntityTagPlan,
    entity_kinds: set[str],
    registered_tags: set[str],
    tags_by_seed_policy: Mapping[str, set[str]],
    event_refs: set[str],
) -> list[str]:
    issues: list[str] = []
    prefix = f"entity tag {tag_plan.tag!r} on {tag_plan.entity_ref!r}"
    if tag_plan.entity_kind not in entity_kinds:
        issues.append(f"{prefix} uses unknown entity_kind {tag_plan.entity_kind!r}")
    if tag_plan.tag not in registered_tags:
        issues.append(f"{prefix} is not a registered single-entity tag")
        return issues
    policy = _tag_seed_policy(tag_plan.tag, tags_by_seed_policy)
    if policy is None:
        issues.append(f"{prefix} has no Retrograde seed policy")
        return issues
    if policy == "prompt_visible_only":
        issues.append(f"{prefix} is prompt-visible-only and cannot be written")
        return issues
    if policy == "event_anchored" and not tag_plan.source_event_ref:
        issues.append(f"{prefix} requires source_event_ref")
    if tag_plan.source_event_ref and tag_plan.source_event_ref not in event_refs:
        issues.append(
            f"{prefix} references unknown source_event_ref "
            f"{tag_plan.source_event_ref!r}"
        )
    return issues


def _pair_tag_plan_issues(
    *,
    pair_plan: RetrogradeExpansionPairTagPlan,
    entity_kinds: set[str],
    pair_definitions: Mapping[str, Mapping[str, Any]],
    event_refs: set[str],
) -> list[str]:
    issues: list[str] = []
    prefix = f"pair tag {pair_plan.tag!r}"
    if pair_plan.subject_kind not in entity_kinds:
        issues.append(f"{prefix} uses unknown subject_kind {pair_plan.subject_kind!r}")
    if pair_plan.object_kind not in entity_kinds:
        issues.append(f"{prefix} uses unknown object_kind {pair_plan.object_kind!r}")
    definition = pair_definitions.get(pair_plan.tag)
    if definition is None:
        issues.append(f"{prefix} is not registered")
        return issues
    if pair_plan.subject_kind not in set(definition["subject_kinds"]):
        issues.append(
            f"{prefix} does not allow subject_kind {pair_plan.subject_kind!r}"
        )
    if pair_plan.object_kind not in set(definition["object_kinds"]):
        issues.append(f"{prefix} does not allow object_kind {pair_plan.object_kind!r}")
    if pair_plan.source_event_ref and pair_plan.source_event_ref not in event_refs:
        issues.append(
            f"{prefix} references unknown source_event_ref "
            f"{pair_plan.source_event_ref!r}"
        )
    return issues


def _relationship_plan_issues(
    *,
    relationship_plan: RetrogradeExpansionRelationshipPlan,
    entity_kinds: set[str],
    relationship_types: set[str],
    event_refs: set[str],
) -> list[str]:
    issues: list[str] = []
    prefix = f"relationship {relationship_plan.relationship_type!r}"
    if relationship_plan.subject_kind not in entity_kinds:
        issues.append(
            f"{prefix} uses unknown subject_kind {relationship_plan.subject_kind!r}"
        )
    if relationship_plan.object_kind not in entity_kinds:
        issues.append(
            f"{prefix} uses unknown object_kind {relationship_plan.object_kind!r}"
        )
    if relationship_plan.relationship_type not in relationship_types:
        issues.append(f"{prefix} is not registered")
    if (
        relationship_plan.subject_kind != "character"
        or relationship_plan.object_kind != "character"
    ):
        issues.append(
            f"{prefix} must be character->character; use event_plan or "
            "pair_tag_plan for faction/place mechanics"
        )
    if (
        relationship_plan.source_event_ref
        and relationship_plan.source_event_ref not in event_refs
    ):
        issues.append(
            f"{prefix} references unknown source_event_ref "
            f"{relationship_plan.source_event_ref!r}"
        )
    return issues


def _thread_plan_issues(
    *,
    thread_plan: list[RetrogradeExpansionThreadPlan],
    selected_seed_ids: set[str],
    event_refs: set[str],
) -> list[str]:
    issues: list[str] = []
    thread_seed_ids = {thread.seed_id for thread in thread_plan}
    missing_threads = sorted(selected_seed_ids - thread_seed_ids)
    if missing_threads:
        issues.append(f"thread_plan omits selected seeds {missing_threads}")
    unknown_threads = sorted(thread_seed_ids - selected_seed_ids)
    if unknown_threads:
        issues.append(f"thread_plan references non-selected seeds {unknown_threads}")
    for thread in thread_plan:
        unknown_event_refs = sorted(set(thread.event_refs) - event_refs)
        if unknown_event_refs:
            issues.append(
                f"thread {thread.seed_id!r} references unknown event_refs "
                f"{unknown_event_refs}"
            )
        if thread.status == "woven" and not thread.event_refs:
            issues.append(f"woven thread {thread.seed_id!r} must include event_refs")
    return issues


def _commit_readiness_issues(
    commit_readiness: RetrogradeExpansionCommitReadiness,
) -> list[str]:
    issues: list[str] = []
    required_blockers = {blocker["id"] for blocker in RETROGRADE_COMMIT_BLOCKERS}
    missing = sorted(required_blockers - set(commit_readiness.blocked_by))
    if missing:
        issues.append(f"commit_readiness.blocked_by omits blockers {missing}")
    if commit_readiness.writes != "none":
        issues.append("commit_readiness.writes must remain 'none'")
    return issues


def _hard_validation_rules() -> list[str]:
    """Return concise Skald-facing R6 validation rules."""

    return [
        "Every event_plan item must reference one or more selected seed ids.",
        "Every selected seed must appear once in thread_plan.",
        "Woven threads must reference planned event_ref values.",
        (
            "Event-anchored single-entity tags require source_event_ref that "
            "matches event_plan.event_ref."
        ),
        "Prompt-visible-only tags must not appear in entity_tag_plan.",
        "Pair tags must obey registered subject/object kind constraints.",
        (
            "relationship_plan currently supports only character->character "
            "rows; express faction/place pressure through events or pair tags."
        ),
        (
            "commit_readiness must keep writes='none' and include both current "
            "commit blockers."
        ),
    ]


def _prompt_response_contract() -> dict[str, Any]:
    """Return a compact prompt-facing R6 response contract."""

    return {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "top_level_fields": [
            "schema_version",
            "selected_seed_ids",
            "event_plan",
            "entity_tag_plan",
            "pair_tag_plan",
            "relationship_plan",
            "thread_plan",
            "coverage_notes",
            "commit_readiness",
        ],
    }


def _prompt_vocabulary(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    """Return the vocabulary subset worth placing in the Skald prompt."""

    return {
        "entity_kinds": vocabulary["entity_kinds"],
        "event_types": vocabulary["event_types"],
        "relationship_types": vocabulary["relationship_types"],
        "registered_tags_by_seed_policy": vocabulary.get(
            "registered_tags_by_seed_policy", {}
        ),
        "multi_entity_tag_definitions": vocabulary["multi_entity_tag_definitions"],
    }


def _tag_seed_policy(
    tag: str,
    tags_by_seed_policy: Mapping[str, set[str]],
) -> Optional[str]:
    for policy, tags in tags_by_seed_policy.items():
        if tag in tags:
            return policy
    return None


def _seed_vocabulary(value: Any) -> SeedEligibleVocabulary:
    vocabulary = _required_mapping(value, "packet.seed_eligible_vocabulary")
    required_keys = (
        "entity_kinds",
        "registered_single_entity_tags",
        "registered_tags_by_seed_policy",
        "multi_entity_tag_definitions",
        "event_types",
        "relationship_types",
    )
    missing = [key for key in required_keys if key not in vocabulary]
    if missing:
        raise ValueError(
            "packet.seed_eligible_vocabulary is missing required keys " f"{missing}"
        )
    return cast(SeedEligibleVocabulary, vocabulary)


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates

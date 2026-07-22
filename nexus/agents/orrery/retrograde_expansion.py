"""Skald-facing Retrograde R6 expansion plan schema and validation."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Mapping, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.agents.logon.apex_schema import Coordinates
from nexus.agents.orrery.geo_authoring import geo_prompt_from_context
from nexus.agents.orrery.retrograde_junctions import resolve_junctions
from nexus.agents.orrery.retrograde_packet import (
    CORE_ENTITIES_HEADING,
    NAMED_SEED_NPCS_HEADING,
)
from nexus.agents.orrery.retrograde_seed_candidates import (
    validate_seed_candidate_response,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    SeedEligibleVocabulary,
    normalize_entity_ref,
)

EntityRef = Annotated[str, Field(min_length=1, max_length=ENTITY_REF_MAX_LENGTH)]
"""Prompt-local entity ref: a proper name, never a description.

Bounded because refs become canonical ``name`` values when persistence
stages minimum-viable stubs (``characters.name``/``places.name`` are
``varchar(50)``).
"""

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


class RetrogradePayloadEntry(BaseModel):
    """Strict key/value entry for future world_events.payload sketches."""

    key: str = Field(min_length=1)
    value: str = Field(description="Payload value rendered as concise prose or JSON.")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _stringify_payload_value(value: Any) -> str:
    """Render arbitrary legacy payload values into strict-schema strings."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RetrogradeExpansionParticipant(BaseModel):
    """One entity reference participating in a planned Retrograde event."""

    entity_ref: EntityRef
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
    location_ref: Optional[EntityRef] = Field(
        default=None,
        description=(
            "Prompt-local place name for future location_id resolution: a "
            f"proper name of at most {ENTITY_REF_MAX_LENGTH} characters, "
            "never a description."
        ),
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
    payload: list[RetrogradePayloadEntry] = Field(
        default_factory=list,
        description="Small future world_events.payload sketch as key/value entries.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payload(cls, data: Any) -> Any:
        """Accept legacy payload dicts while emitting strict list schema."""

        if not isinstance(data, dict):
            return data
        payload = data.get("payload")
        if payload is None or isinstance(payload, list):
            return data
        if isinstance(payload, Mapping):
            data = dict(data)
            data["payload"] = [
                {"key": str(key), "value": _stringify_payload_value(value)}
                for key, value in payload.items()
            ]
        return data

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionEntityTagPlan(BaseModel):
    """One future entity_tags write implied by the woven history."""

    entity_ref: EntityRef
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

    subject_ref: EntityRef
    subject_kind: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    object_ref: EntityRef
    object_kind: str = Field(min_length=1)
    source_event_ref: Optional[str] = Field(default=None)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionRelationshipPlan(BaseModel):
    """One future relationship-table write implied by the woven history."""

    subject_ref: EntityRef
    subject_kind: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    object_ref: EntityRef
    object_kind: str = Field(min_length=1)
    source_event_ref: Optional[str] = Field(default=None)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionDeathPlan(BaseModel):
    """One entity dead, destroyed, or dissolved as of story start.

    A death asserted only in event-summary prose is invisible to the engine:
    the entity stays ``is_active`` and the Orrery keeps animating it. This
    row is the machine-readable assertion that flips the kill switch.
    """

    entity_ref: EntityRef
    entity_kind: str = Field(min_length=1)
    cause_event_ref: Optional[str] = Field(
        default=None,
        description=("Required: event_plan.event_ref documenting the death as a fact."),
    )
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


class RetrogradeExpansionWireEventPlan(BaseModel):
    """Provider-facing event plan with absence represented as empty strings."""

    event_ref: str = Field(min_length=1)
    seed_ids: list[str] = Field(default_factory=list)
    event_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    chronology: Literal["deep_past", "recent_past", "opening_pressure"]
    participants: list[RetrogradeExpansionParticipant] = Field(default_factory=list)
    location_ref: str = Field(
        default="",
        description="Prompt-local place name, or empty string when absent.",
    )
    changed_fields: list[str] = Field(default_factory=list)
    magnitude: str = Field(
        default="",
        description="0..1 as text, or empty string when absent.",
    )
    payload: list[RetrogradePayloadEntry] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionWireMechanicPlan(BaseModel):
    """Provider-facing generic mechanics row expanded by runtime."""

    plan: Literal["entity_tag", "pair_tag", "relationship", "death"]
    subject_ref: EntityRef
    subject_kind: str = Field(min_length=1)
    tag: str = Field(
        default="",
        description="Single-entity or pair tag; empty for relationship rows.",
    )
    object_ref: str = Field(
        default="",
        description="Object entity ref for pair tags/relationships; empty otherwise.",
    )
    object_kind: str = Field(
        default="",
        description="Object entity kind for pair tags/relationships; empty otherwise.",
    )
    relationship_type: str = Field(
        default="",
        description="Relationship type for relationship rows; empty otherwise.",
    )
    source_event_ref: str = Field(
        default="",
        description="Planned event_ref source, or empty string when absent.",
    )
    rationale: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionWireThreadPlan(BaseModel):
    """Provider-facing thread accounting with absence represented as strings."""

    seed_id: str = Field(min_length=1)
    status: Literal["woven", "deferred", "rejected"]
    event_refs: list[str] = Field(default_factory=list)
    present_leaf_anchor: str = Field(min_length=1)
    note: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeExpansionWireResponse(BaseModel):
    """Provider-facing R6 response with deterministic fields omitted."""

    event_plan: list[RetrogradeExpansionWireEventPlan] = Field(default_factory=list)
    mechanical_plan: list[RetrogradeExpansionWireMechanicPlan] = Field(
        default_factory=list
    )
    thread_plan: list[RetrogradeExpansionWireThreadPlan] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description=(
            "For a maturation-target place that lacks coordinates, its "
            "plausible real-Earth point; otherwise null."
        ),
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
    death_plan: list[RetrogradeExpansionDeathPlan] = Field(default_factory=list)
    thread_plan: list[RetrogradeExpansionThreadPlan] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description="Authored coordinates for a place maturation target.",
    )
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
        duplicate_deaths = _duplicates(
            [
                f"{death.entity_kind}:{normalize_entity_ref(death.entity_ref)}"
                for death in self.death_plan
            ]
        )
        if duplicate_deaths:
            raise ValueError(
                f"Duplicate death_plan entities: {sorted(duplicate_deaths)}"
            )
        return self


def expansion_response_schema() -> dict[str, Any]:
    """Return the Pydantic JSON schema for R6 expansion responses."""

    return RetrogradeExpansionPlanResponse.model_json_schema()


def coerce_expansion_response_payload(
    payload: Mapping[str, Any],
    *,
    selected_seed_ids: list[str],
) -> RetrogradeExpansionPlanResponse:
    """Fill deterministic R6 fields and return the full app contract."""

    data = _expand_wire_payload(payload)
    data.setdefault("schema_version", RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION)
    data.setdefault("selected_seed_ids", list(selected_seed_ids))
    data.setdefault("commit_readiness", {})
    return RetrogradeExpansionPlanResponse.model_validate(data)


def _none_if_empty(value: Any) -> Any:
    if value == "":
        return None
    return value


def _float_if_present(value: Any) -> Optional[float]:
    if value in {"", None}:
        return None
    return float(value)


def _expand_wire_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Expand compact provider mechanics into the full persistence plan shape."""

    data = dict(payload)
    if "mechanical_plan" not in data:
        return data

    event_plan = []
    for event in data.get("event_plan") or []:
        row = dict(event)
        row["location_ref"] = _none_if_empty(row.get("location_ref"))
        row["magnitude"] = _float_if_present(row.get("magnitude"))
        event_plan.append(row)

    entity_tag_plan = []
    pair_tag_plan = []
    relationship_plan = []
    death_plan = []
    for mechanic in data.get("mechanical_plan") or []:
        plan = str(mechanic.get("plan"))
        source_event_ref = _none_if_empty(mechanic.get("source_event_ref"))
        rationale = _none_if_empty(mechanic.get("rationale"))
        if plan == "entity_tag":
            entity_tag_plan.append(
                {
                    "entity_ref": mechanic.get("subject_ref"),
                    "entity_kind": mechanic.get("subject_kind"),
                    "tag": mechanic.get("tag"),
                    "source_event_ref": source_event_ref,
                    "rationale": rationale,
                }
            )
        elif plan == "pair_tag":
            pair_tag_plan.append(
                {
                    "subject_ref": mechanic.get("subject_ref"),
                    "subject_kind": mechanic.get("subject_kind"),
                    "tag": mechanic.get("tag"),
                    "object_ref": mechanic.get("object_ref"),
                    "object_kind": mechanic.get("object_kind"),
                    "source_event_ref": source_event_ref,
                    "rationale": rationale,
                }
            )
        elif plan == "relationship":
            relationship_plan.append(
                {
                    "subject_ref": mechanic.get("subject_ref"),
                    "subject_kind": mechanic.get("subject_kind"),
                    "relationship_type": mechanic.get("relationship_type"),
                    "object_ref": mechanic.get("object_ref"),
                    "object_kind": mechanic.get("object_kind"),
                    "source_event_ref": source_event_ref,
                    "rationale": rationale,
                }
            )
        elif plan == "death":
            death_plan.append(
                {
                    "entity_ref": mechanic.get("subject_ref"),
                    "entity_kind": mechanic.get("subject_kind"),
                    "cause_event_ref": source_event_ref,
                    "rationale": rationale,
                }
            )

    thread_plan = []
    for thread in data.get("thread_plan") or []:
        row = dict(thread)
        row["note"] = _none_if_empty(row.get("note"))
        thread_plan.append(row)

    return {
        "event_plan": event_plan,
        "entity_tag_plan": entity_tag_plan,
        "pair_tag_plan": pair_tag_plan,
        "relationship_plan": relationship_plan,
        "death_plan": death_plan,
        "thread_plan": thread_plan,
        "coverage_notes": data.get("coverage_notes") or [],
        "coordinates": data.get("coordinates"),
    }


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
    resolved_junctions, junction_issues = resolve_junctions(
        seed_generation_request=seed_generation_request,
        candidates_payload=candidates.model_dump(mode="json"),
    )
    if junction_issues:
        formatted = "; ".join(junction_issues)
        raise ValueError(f"Retrograde junction resolution failed: {formatted}")
    selected_seed_ids = set(candidates.selected_seed_ids)
    selected_junctions = [
        junction
        for junction in resolved_junctions
        if set(junction["seed_ids"]) <= selected_seed_ids
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
        "selected_junctions": selected_junctions,
        "core_prompt_sections": (
            seed_generation_request.get("prompt_sections", [])[:4]
        ),
        "allowed_vocabulary": _prompt_vocabulary(vocabulary),
        "hard_validation_rules": _hard_validation_rules(),
        "response_contract": _prompt_response_contract(),
    }
    geo_prompt = geo_prompt_from_context(packet)
    if geo_prompt is not None:
        prompt_payload["geo_authoring"] = geo_prompt
    return (
        "You are Skald-as-weaver for Retrograde R6 expansion.\n"
        "Weave the selected seeds into a sparse history web with row-shaped "
        "event/tag/relationship plans, but do not claim canonical persistence.\n"
        "Write each event summary in a diegetic archival register — a fact "
        "as a record-keeper, chronicler, or registry would state it (who, "
        "what, when-relative, where) — never as scene prose or narration. "
        "These summaries surface later as retrieved documents, not story.\n"
        "Every selected seed must be accounted for as woven, deferred, or "
        "rejected. Every woven thread must terminate in a present leaf anchor.\n"
        "For every selected junction, either weave both member seeds through "
        "the promised shared entity using structured event participants/location, "
        "or reject both without planning events for either seed. Junction members "
        "cannot be deferred or survive independently.\n"
        "If the woven history means an entity is dead, destroyed, or "
        "dissolved before the story opens, declare it as a mechanical_plan "
        "row with plan='death' citing the causing event; a death asserted "
        "only in summary prose leaves the entity alive to the engine and is "
        "invalid.\n"
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
    resolved_junctions, junction_issues = resolve_junctions(
        seed_generation_request=seed_generation_request,
        candidates_payload=candidates.model_dump(mode="json"),
    )
    if junction_issues:
        formatted = "\n".join(f"- {issue}" for issue in junction_issues)
        raise RetrogradeExpansionValidationError(formatted)
    selected_seed_ids = set(candidates.selected_seed_ids)
    selected_junctions = [
        junction
        for junction in resolved_junctions
        if set(junction["seed_ids"]) <= selected_seed_ids
    ]
    response = coerce_expansion_response_payload(
        payload,
        selected_seed_ids=list(candidates.selected_seed_ids),
    )
    issues = _expansion_contract_issues(
        response=response,
        selected_seed_ids=selected_seed_ids,
        selected_junctions=selected_junctions,
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

    from pydantic_ai import ModelRetry

    from nexus.api.config_utils import (
        get_new_story_model,
        get_wizard_max_tokens,
        get_wizard_retry_budget,
    )
    from nexus.api.native_structured_output import build_native_structured_provider

    prompt = render_expansion_prompt(
        packet=packet,
        seed_candidate_response=seed_candidate_response,
    )
    selected_model = model_name or get_new_story_model()
    provider = build_native_structured_provider(
        model=selected_model,
        max_tokens=max_tokens or get_wizard_max_tokens(),
        system_prompt=(
            "You are Skald-as-weaver for a NEXUS Retrograde expansion pass. "
            "Return a non-mutating expansion plan only."
        ),
        structured_output_retries=get_wizard_retry_budget(),
    )

    async def _validate_output(
        _ctx: Any,
        output: RetrogradeExpansionWireResponse,
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

    provider.output_validator = _validate_output
    response, _llm_response = provider.get_structured_completion(
        prompt,
        RetrogradeExpansionWireResponse,
    )
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
    selected_junctions: list[dict[str, Any]],
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
    tags_by_entity_kind = {
        kind: set(tags)
        for kind, tags in vocabulary["registered_tags_by_entity_kind"].items()
    }
    status_edge_counts: dict[tuple[str, str, str, str], int] = {}
    for pair_plan in response.pair_tag_plan:
        if not pair_plan.tag.startswith("status:"):
            continue
        edge = (
            pair_plan.subject_kind,
            normalize_entity_ref(pair_plan.subject_ref),
            pair_plan.object_kind,
            normalize_entity_ref(pair_plan.object_ref),
        )
        status_edge_counts[edge] = status_edge_counts.get(edge, 0) + 1

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
                tags_by_entity_kind=tags_by_entity_kind,
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
                status_edge_counts=status_edge_counts,
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

    events_by_ref = {event.event_ref: event for event in response.event_plan}
    for death in response.death_plan:
        issues.extend(
            _death_plan_issues(
                death=death,
                entity_kinds=entity_kinds,
                events_by_ref=events_by_ref,
                known_entity_keys=known_entity_keys or set(),
            )
        )

    issues.extend(
        _thread_plan_issues(
            thread_plan=response.thread_plan,
            selected_seed_ids=selected_seed_ids,
            events_by_ref=events_by_ref,
        )
    )
    issues.extend(
        _junction_plan_issues(
            response=response,
            selected_junctions=selected_junctions,
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
                (participant.entity_kind, normalize_entity_ref(participant.entity_ref))
            )
        if event.location_ref:
            keys.add(("place", normalize_entity_ref(event.location_ref)))
    for tag_plan in response.entity_tag_plan:
        keys.add((tag_plan.entity_kind, normalize_entity_ref(tag_plan.entity_ref)))
    for pair_plan in response.pair_tag_plan:
        keys.add((pair_plan.subject_kind, normalize_entity_ref(pair_plan.subject_ref)))
        keys.add((pair_plan.object_kind, normalize_entity_ref(pair_plan.object_ref)))
    for relationship in response.relationship_plan:
        keys.add(
            (relationship.subject_kind, normalize_entity_ref(relationship.subject_ref))
        )
        keys.add(
            (relationship.object_kind, normalize_entity_ref(relationship.object_ref))
        )
    for death in response.death_plan:
        keys.add((death.entity_kind, normalize_entity_ref(death.entity_ref)))
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
            keys.add((str(kind), normalize_entity_ref(str(name))))

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
            if section.get("heading") not in {
                CORE_ENTITIES_HEADING,
                NAMED_SEED_NPCS_HEADING,
            }:
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
    tags_by_entity_kind: Mapping[str, set[str]],
    event_refs: set[str],
) -> list[str]:
    issues: list[str] = []
    prefix = f"entity tag {tag_plan.tag!r} on {tag_plan.entity_ref!r}"
    if tag_plan.entity_kind not in entity_kinds:
        issues.append(f"{prefix} uses unknown entity_kind {tag_plan.entity_kind!r}")
    if tag_plan.tag not in registered_tags:
        issues.append(f"{prefix} is not a registered single-entity tag")
        return issues
    # Mirror the persistence layer's tag_category_registry kind check so an
    # incompatible plan is repaired by ModelRetry at generation time instead
    # of failing later at persistence time. The mapping is a required packet
    # vocabulary key, so the check is unconditional.
    if tag_plan.tag not in tags_by_entity_kind.get(tag_plan.entity_kind, set()):
        issues.append(
            f"{prefix} is not registered for entity_kind "
            f"{tag_plan.entity_kind!r}; use a tag from "
            "registered_tags_by_entity_kind for that kind"
        )
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
    status_edge_counts: Mapping[tuple[str, str, str, str], int],
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
    status_edge = (
        pair_plan.subject_kind,
        normalize_entity_ref(pair_plan.subject_ref),
        pair_plan.object_kind,
        normalize_entity_ref(pair_plan.object_ref),
    )
    if (
        pair_plan.tag.startswith("status:")
        and status_edge_counts.get(status_edge, 0) > 1
    ):
        issues.append(
            f"{prefix} duplicates a status ladder row for edge "
            f"{pair_plan.subject_ref!r} -> {pair_plan.object_ref!r}; plan only "
            "the final standing and express the status arc in event_plan"
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


def _death_plan_issues(
    *,
    death: RetrogradeExpansionDeathPlan,
    entity_kinds: set[str],
    events_by_ref: Mapping[str, RetrogradeExpansionEventPlan],
    known_entity_keys: set[tuple[str, str]],
) -> list[str]:
    issues: list[str] = []
    prefix = f"death {death.entity_kind}:{death.entity_ref}"
    if death.entity_kind not in entity_kinds:
        issues.append(f"{prefix} uses unknown entity_kind {death.entity_kind!r}")
    death_key = (death.entity_kind, normalize_entity_ref(death.entity_ref))
    if death_key in known_entity_keys:
        issues.append(
            f"{prefix} targets a first-class starting entity; deaths may only "
            "target backstory figures this expansion itself introduces — drop "
            "the death or invent a new named figure for it"
        )
    if not death.cause_event_ref:
        issues.append(
            f"{prefix} is missing cause_event_ref; a death asserted only in "
            "summary prose is invalid — plan the causing event and cite it"
        )
        return issues
    cause = events_by_ref.get(death.cause_event_ref)
    if cause is None:
        issues.append(
            f"{prefix} cites unknown cause_event_ref {death.cause_event_ref!r}"
        )
        return issues
    participant_keys = {
        (participant.entity_kind, normalize_entity_ref(participant.entity_ref))
        for participant in cause.participants
    }
    if death_key not in participant_keys:
        issues.append(
            f"{prefix}: cause event {death.cause_event_ref!r} must list the "
            "dying entity as a participant"
        )
    return issues


def _thread_plan_issues(
    *,
    thread_plan: list[RetrogradeExpansionThreadPlan],
    selected_seed_ids: set[str],
    events_by_ref: Mapping[str, RetrogradeExpansionEventPlan],
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
        unknown_event_refs = sorted(set(thread.event_refs) - set(events_by_ref))
        if unknown_event_refs:
            issues.append(
                f"thread {thread.seed_id!r} references unknown event_refs "
                f"{unknown_event_refs}"
            )
        for event_ref in sorted(set(thread.event_refs) & set(events_by_ref)):
            event = events_by_ref[event_ref]
            if thread.seed_id not in event.seed_ids:
                issues.append(
                    f"thread {thread.seed_id!r} references event {event_ref!r}, "
                    "but that event does not list the thread's seed_id"
                )
        if thread.status == "woven" and not thread.event_refs:
            issues.append(f"woven thread {thread.seed_id!r} must include event_refs")
    return issues


def _junction_plan_issues(
    *,
    response: RetrogradeExpansionPlanResponse,
    selected_junctions: list[dict[str, Any]],
) -> list[str]:
    """Require selected junctions to survive or fail as realized atomic pairs."""

    issues: list[str] = []
    threads_by_seed = {thread.seed_id: thread for thread in response.thread_plan}
    events_by_ref = {event.event_ref: event for event in response.event_plan}

    for junction in selected_junctions:
        junction_id = str(junction["junction_id"])
        seed_ids = [str(seed_id) for seed_id in junction["seed_ids"]]
        threads = [threads_by_seed.get(seed_id) for seed_id in seed_ids]
        # The general thread-plan validator reports missing accounting. Avoid
        # duplicating that error while still validating complete junctions.
        if any(thread is None for thread in threads):
            continue

        complete_threads = [thread for thread in threads if thread is not None]
        statuses = [thread.status for thread in complete_threads]
        if all(status == "rejected" for status in statuses):
            referenced_events = sorted(
                {
                    event.event_ref
                    for event in response.event_plan
                    if set(event.seed_ids) & set(seed_ids)
                }
                | {
                    event_ref
                    for thread in complete_threads
                    for event_ref in thread.event_refs
                }
            )
            if referenced_events:
                issues.append(
                    f"junction {junction_id!r} rejects both seeds but still "
                    f"plans or references events {referenced_events}"
                )
            continue

        if not all(status == "woven" for status in statuses):
            status_by_seed = {
                seed_id: thread.status
                for seed_id, thread in zip(seed_ids, complete_threads)
            }
            issues.append(
                f"junction {junction_id!r} members must be both woven or both "
                f"rejected, not {status_by_seed}"
            )
            continue

        entity_kind = str(junction["entity_kind"])
        normalized_entity_ref = str(junction["normalized_entity_ref"])
        for seed_id, thread in zip(seed_ids, complete_threads):
            evidence_refs = [
                event_ref
                for event_ref in thread.event_refs
                if event_ref in events_by_ref
                and seed_id in events_by_ref[event_ref].seed_ids
                and _event_contains_junction_entity(
                    events_by_ref[event_ref],
                    entity_kind=entity_kind,
                    normalized_entity_ref=normalized_entity_ref,
                )
            ]
            if not evidence_refs:
                issues.append(
                    f"junction {junction_id!r} woven seed {seed_id!r} lacks a "
                    "thread event containing the promised shared "
                    f"{entity_kind} {junction['entity_ref']!r}"
                )

    return issues


def _event_contains_junction_entity(
    event: RetrogradeExpansionEventPlan,
    *,
    entity_kind: str,
    normalized_entity_ref: str,
) -> bool:
    participant_keys = {
        (participant.entity_kind, normalize_entity_ref(participant.entity_ref))
        for participant in event.participants
    }
    if (entity_kind, normalized_entity_ref) in participant_keys:
        return True
    return bool(
        entity_kind == "place"
        and event.location_ref
        and normalize_entity_ref(event.location_ref) == normalized_entity_ref
    )


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
        (
            "Woven threads must reference planned event_ref values whose "
            "event seed_ids include that thread's seed_id."
        ),
        (
            "Each selected junction must have both member seeds woven through "
            "its promised shared entity in structured event participants/location, "
            "or both rejected with no events; junction members cannot be deferred."
        ),
        (
            "mechanical_plan rows use plan='entity_tag', 'pair_tag', "
            "'relationship', or 'death'. Leave fields irrelevant to that "
            "plan as empty strings."
        ),
        (
            "death mechanics require source_event_ref naming the causing "
            "event, and that event must list the dying entity as a "
            "participant."
        ),
        (
            "death mechanics may only target new backstory figures this "
            "plan itself introduces — never first-class starting entities "
            "or entities already live in the story."
        ),
        (
            "Event-anchored entity_tag mechanics require source_event_ref that "
            "matches event_plan.event_ref."
        ),
        "Prompt-visible-only tags must not appear in mechanical_plan.",
        "Pair tags must obey registered subject/object kind constraints.",
        (
            "Plan at most one status:* pair tag per subject/object edge; it "
            "records final standing, while the arc belongs in event_plan."
        ),
        (
            "Single-entity tags must be registered for the tagged entity_kind "
            "in registered_tags_by_entity_kind; a tag listed only under another "
            "kind is illegal."
        ),
        (
            "relationship mechanics currently support only character->character "
            "rows; express faction/place pressure through events or pair tags."
        ),
        (
            "Entity refs (subject_ref, object_ref, location_ref) "
            f"are proper names of at most {ENTITY_REF_MAX_LENGTH} characters "
            "-- never sentences or descriptive phrases. New implied entities "
            "get a short invented name, not a description."
        ),
    ]


def _prompt_response_contract() -> dict[str, Any]:
    """Return a compact prompt-facing R6 response contract."""

    return {
        "top_level_fields": [
            "event_plan",
            "mechanical_plan",
            "thread_plan",
            "coverage_notes",
        ],
        "mechanical_plan_fields": {
            "common": ["plan", "subject_ref", "subject_kind", "source_event_ref"],
            "entity_tag": ["tag"],
            "pair_tag": ["tag", "object_ref", "object_kind"],
            "relationship": ["relationship_type", "object_ref", "object_kind"],
            "death": [],
            "unused_fields": "Use empty strings for fields irrelevant to the plan.",
        },
        "deterministic_fields_filled_by_runtime": [
            "schema_version",
            "selected_seed_ids",
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
        # The validator enforces per-kind tag registration, so Skald must see
        # the same mapping up front; otherwise kind mismatches burn retries.
        "registered_tags_by_entity_kind": vocabulary["registered_tags_by_entity_kind"],
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
        "registered_tags_by_entity_kind",
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

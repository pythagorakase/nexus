"""Skald-facing Retrograde seed candidate schema and validation."""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary

SeedCandidateSchemaVersion = Literal["orrery_retrograde_seed_candidates.v0"]
SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION: SeedCandidateSchemaVersion = (
    "orrery_retrograde_seed_candidates.v0"
)


class RetrogradeSeedCandidateValidationError(ValueError):
    """Raised when a seed candidate response is shaped correctly but illegal."""


class RetrogradeSeedEventHint(BaseModel):
    """One explicit retrograde event a candidate seed would imply."""

    event_ref: str = Field(
        min_length=1,
        description="Candidate-local event identifier used by tag hints.",
    )
    event_type: str = Field(
        min_length=1,
        description="Registered Orrery event type.",
    )
    summary: str = Field(
        min_length=1,
        max_length=600,
        description="Brief natural-language event summary.",
    )
    participating_entities: list[str] = Field(
        default_factory=list,
        description="Prompt-local entity names or refs involved in the event.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeSingleEntityTagHint(BaseModel):
    """One proposed single-entity tag outcome for a candidate seed."""

    entity_ref: str = Field(
        min_length=1,
        description="Prompt-local entity name or ref receiving the tag.",
    )
    entity_kind: str = Field(
        min_length=1,
        description="Registered Orrery entity kind for the tagged entity.",
    )
    tag: str = Field(
        min_length=1,
        description="Registered single-entity tag name.",
    )
    supporting_event_ref: Optional[str] = Field(
        default=None,
        description=(
            "Required for event-anchored tags; references an event_ref in this "
            "candidate's mechanical_hints.events."
        ),
    )
    rationale: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Brief reason this tag follows from the seed.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradePairTagHint(BaseModel):
    """One proposed directed multi-entity tag outcome."""

    subject_ref: str = Field(min_length=1)
    subject_kind: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    object_kind: str = Field(min_length=1)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeRelationshipHint(BaseModel):
    """One proposed relationship primitive implied by a candidate seed."""

    subject_ref: str = Field(min_length=1)
    subject_kind: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    object_kind: str = Field(min_length=1)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeMechanicalHints(BaseModel):
    """Substrate-facing hints Skald may propose for one seed candidate."""

    events: list[RetrogradeSeedEventHint] = Field(default_factory=list)
    single_entity_tags: list[RetrogradeSingleEntityTagHint] = Field(
        default_factory=list
    )
    pair_tags: list[RetrogradePairTagHint] = Field(default_factory=list)
    relationships: list[RetrogradeRelationshipHint] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeSeedCandidate(BaseModel):
    """One over-generated Retrograde seed candidate."""

    seed_id: str = Field(
        min_length=1,
        description="Candidate-local stable identifier.",
    )
    summary: str = Field(
        min_length=1,
        max_length=1200,
        description="Concise seed summary.",
    )
    origin_friction: Literal["low", "medium", "high"] = Field(
        description="How orthogonal/surprising the seed origin is."
    )
    present_leaf_anchor: str = Field(
        min_length=1,
        max_length=800,
        description="Concrete connection back to present canon.",
    )
    coverage_functions: list[str] = Field(
        default_factory=list,
        description="Coverage function ids served by this seed.",
    )
    mechanical_hints: RetrogradeMechanicalHints = Field(
        default_factory=RetrogradeMechanicalHints
    )
    defer_or_reject_if: list[str] = Field(
        default_factory=list,
        description="Conditions under which Skald should discard the seed.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeSeedCandidateResponse(BaseModel):
    """Structured response from the non-mutating Skald-as-weaver seed pass."""

    schema_version: SeedCandidateSchemaVersion = SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION
    candidates: list[RetrogradeSeedCandidate] = Field(
        default_factory=list,
        description="Over-generated candidate seeds.",
    )
    selected_seed_ids: list[str] = Field(
        default_factory=list,
        description="Candidate ids recommended for the later expansion pass.",
    )
    rejected_seed_ids: list[str] = Field(
        default_factory=list,
        description="Candidate ids explicitly rejected during selection.",
    )
    selection_notes: Optional[str] = Field(
        default=None,
        max_length=1200,
        description="Brief selection rationale for audit/debugging.",
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="after")
    def _validate_seed_id_sets(self) -> "RetrogradeSeedCandidateResponse":
        seed_ids = [candidate.seed_id for candidate in self.candidates]
        duplicate_ids = _duplicates(seed_ids)
        if duplicate_ids:
            raise ValueError(f"Duplicate seed_id values: {sorted(duplicate_ids)}")

        known_ids = set(seed_ids)
        unknown_selected = sorted(set(self.selected_seed_ids) - known_ids)
        if unknown_selected:
            raise ValueError(
                "selected_seed_ids reference unknown candidates: " f"{unknown_selected}"
            )

        unknown_rejected = sorted(set(self.rejected_seed_ids) - known_ids)
        if unknown_rejected:
            raise ValueError(
                "rejected_seed_ids reference unknown candidates: " f"{unknown_rejected}"
            )

        overlap = sorted(set(self.selected_seed_ids) & set(self.rejected_seed_ids))
        if overlap:
            raise ValueError(f"Seed ids cannot be selected and rejected: {overlap}")

        return self


def seed_candidate_response_schema() -> dict[str, Any]:
    """Return the Pydantic JSON schema for Skald seed candidate responses."""

    return RetrogradeSeedCandidateResponse.model_json_schema()


def render_seed_generation_prompt(
    *,
    seed_generation_request: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
) -> str:
    """Render a deterministic Skald prompt for non-mutating seed generation."""

    prompt_payload = {
        "task": (
            "Generate and select Retrograde deep-history seed candidates. "
            "Do not write canon. Return JSON only. Keep every candidate concise."
        ),
        "mutation_policy": seed_generation_request.get("mutation_policy", {}),
        "budget": seed_generation_request.get("budget", {}),
        "weird_policy": seed_generation_request.get("weird_policy", {}),
        "mechanical_tag_policy": seed_generation_request.get(
            "mechanical_tag_policy", {}
        ),
        "hard_validation_rules": _hard_validation_rules(),
        "allowed_vocabulary": _prompt_vocabulary(vocabulary),
        "coverage_functions": seed_generation_request.get("coverage_functions", []),
        "selection_rubric": seed_generation_request.get("selection_rubric", {}),
        "prompt_sections": seed_generation_request.get("prompt_sections", []),
        "response_contract": _prompt_response_contract(),
    }
    return (
        "You are Skald-as-weaver for a Retrograde seed-generation pass.\n"
        "Generate surprising candidate history seeds, select the strongest "
        "subset, and leave all persistence to a later reviewed expansion pass.\n"
        "Keep summaries, rationales, and rejection conditions compact.\n"
        "If a mechanical hint cannot satisfy the hard validation rules, omit it.\n"
        "Return JSON only. Unknown mechanical primitives are invalid.\n\n"
        "RETROGRADE_SEED_GENERATION_REQUEST:\n"
        f"{json.dumps(prompt_payload, indent=2, sort_keys=True)}"
    )


def validate_seed_candidate_response(
    *,
    payload: Mapping[str, Any],
    seed_generation_request: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
) -> RetrogradeSeedCandidateResponse:
    """Validate a Skald seed response against request budgets and vocabulary."""

    response = RetrogradeSeedCandidateResponse.model_validate(payload)
    issues = _response_contract_issues(
        response=response,
        seed_generation_request=seed_generation_request,
        vocabulary=vocabulary,
    )
    if issues:
        formatted = "\n".join(f"- {issue}" for issue in issues)
        raise RetrogradeSeedCandidateValidationError(formatted)
    return response


def generate_seed_candidates_with_skald(
    *,
    packet: Mapping[str, Any],
    model_name: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict[str, Any]:
    """Make a non-mutating Skald call to generate Retrograde seed candidates."""

    from pydantic_ai import Agent, ModelRetry, RunContext
    from pydantic_ai.settings import ModelSettings

    from nexus.api.config_utils import (
        get_new_story_model,
        get_wizard_max_tokens,
        get_wizard_retry_budget,
    )
    from nexus.api.pydantic_ai_utils import build_pydantic_ai_model

    seed_generation_request = _required_mapping(
        packet.get("seed_generation_request"),
        "packet.seed_generation_request",
    )
    vocabulary = _seed_vocabulary(packet.get("seed_eligible_vocabulary"))
    prompt = packet.get("seed_generation_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        prompt = render_seed_generation_prompt(
            seed_generation_request=seed_generation_request,
            vocabulary=vocabulary,
        )

    selected_model = model_name or get_new_story_model()
    agent = Agent(
        model=build_pydantic_ai_model(selected_model),
        output_type=RetrogradeSeedCandidateResponse,
        system_prompt=(
            "You are Skald-as-weaver for a NEXUS Retrograde seed pass. "
            "Generate candidate history seeds, select a subset, and do not "
            "claim any canonical write has occurred."
        ),
        model_settings=ModelSettings(max_tokens=max_tokens or get_wizard_max_tokens()),
        retries=get_wizard_retry_budget(),
    )

    async def _validate_output(
        _ctx: RunContext[None],
        output: RetrogradeSeedCandidateResponse,
    ) -> RetrogradeSeedCandidateResponse:
        try:
            return validate_seed_candidate_response(
                payload=output.model_dump(mode="json"),
                seed_generation_request=seed_generation_request,
                vocabulary=vocabulary,
            )
        except RetrogradeSeedCandidateValidationError as exc:
            raise ModelRetry(
                "Retrograde seed candidate mechanics failed validation. "
                "Repair the JSON by omitting invalid mechanical hints or adding "
                f"the required refs:\n{exc}"
            ) from exc

    agent.output_validator(_validate_output)
    result = agent.run_sync(prompt)
    response = result.output
    if not isinstance(response, RetrogradeSeedCandidateResponse):
        raise TypeError(
            "Skald seed candidate call returned "
            f"{type(response).__name__}, expected RetrogradeSeedCandidateResponse"
        )

    return {
        "model": selected_model,
        "prompt_chars": len(prompt),
        "seed_candidate_response": response.model_dump(mode="json"),
    }


def _response_contract_issues(
    *,
    response: RetrogradeSeedCandidateResponse,
    seed_generation_request: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
) -> list[str]:
    budget = _mapping(seed_generation_request.get("budget"))
    issues: list[str] = []
    generate_limit = _optional_positive_int(budget.get("generate_candidates"))
    select_limit = _optional_positive_int(budget.get("select_target"))

    if generate_limit is not None and len(response.candidates) > generate_limit:
        issues.append(
            "response generated "
            f"{len(response.candidates)} candidates, exceeding budget "
            f"{generate_limit}"
        )
    if select_limit is not None and len(response.selected_seed_ids) > select_limit:
        issues.append(
            "response selected "
            f"{len(response.selected_seed_ids)} seeds, exceeding target "
            f"{select_limit}"
        )

    coverage_ids = {
        str(function.get("id"))
        for function in seed_generation_request.get("coverage_functions", [])
        if isinstance(function, Mapping) and function.get("id")
    }
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

    for candidate in response.candidates:
        issues.extend(
            _candidate_contract_issues(
                candidate=candidate,
                coverage_ids=coverage_ids,
                event_types=event_types,
                entity_kinds=entity_kinds,
                relationship_types=relationship_types,
                pair_definitions=pair_definitions,
                registered_tags=registered_tags,
                tags_by_seed_policy=tags_by_seed_policy,
            )
        )

    return issues


def _candidate_contract_issues(
    *,
    candidate: RetrogradeSeedCandidate,
    coverage_ids: set[str],
    event_types: set[str],
    entity_kinds: set[str],
    relationship_types: set[str],
    pair_definitions: Mapping[str, Mapping[str, Any]],
    registered_tags: set[str],
    tags_by_seed_policy: Mapping[str, set[str]],
) -> list[str]:
    issues: list[str] = []
    candidate_prefix = f"candidate {candidate.seed_id!r}"

    unknown_coverage = sorted(set(candidate.coverage_functions) - coverage_ids)
    if unknown_coverage:
        issues.append(
            f"{candidate_prefix} uses unknown coverage functions {unknown_coverage}"
        )

    events_by_ref: dict[str, RetrogradeSeedEventHint] = {}
    duplicate_event_refs = _duplicates(
        [event.event_ref for event in candidate.mechanical_hints.events]
    )
    if duplicate_event_refs:
        issues.append(
            f"{candidate_prefix} repeats event_ref values "
            f"{sorted(duplicate_event_refs)}"
        )

    for event in candidate.mechanical_hints.events:
        events_by_ref[event.event_ref] = event
        if event.event_type not in event_types:
            issues.append(
                f"{candidate_prefix} event {event.event_ref!r} uses "
                f"unknown event_type {event.event_type!r}"
            )

    for tag_hint in candidate.mechanical_hints.single_entity_tags:
        issues.extend(
            _single_tag_issues(
                candidate_prefix=candidate_prefix,
                tag_hint=tag_hint,
                entity_kinds=entity_kinds,
                registered_tags=registered_tags,
                tags_by_seed_policy=tags_by_seed_policy,
                events_by_ref=events_by_ref,
            )
        )

    for pair_hint in candidate.mechanical_hints.pair_tags:
        issues.extend(
            _pair_tag_issues(
                candidate_prefix=candidate_prefix,
                pair_hint=pair_hint,
                entity_kinds=entity_kinds,
                pair_definitions=pair_definitions,
            )
        )

    for relationship_hint in candidate.mechanical_hints.relationships:
        issues.extend(
            _relationship_issues(
                candidate_prefix=candidate_prefix,
                relationship_hint=relationship_hint,
                entity_kinds=entity_kinds,
                relationship_types=relationship_types,
            )
        )

    return issues


def _single_tag_issues(
    *,
    candidate_prefix: str,
    tag_hint: RetrogradeSingleEntityTagHint,
    entity_kinds: set[str],
    registered_tags: set[str],
    tags_by_seed_policy: Mapping[str, set[str]],
    events_by_ref: Mapping[str, RetrogradeSeedEventHint],
) -> list[str]:
    issues: list[str] = []
    if tag_hint.entity_kind not in entity_kinds:
        issues.append(
            f"{candidate_prefix} tag {tag_hint.tag!r} uses unknown "
            f"entity_kind {tag_hint.entity_kind!r}"
        )
    if tag_hint.tag not in registered_tags:
        issues.append(
            f"{candidate_prefix} proposes unregistered single-entity tag "
            f"{tag_hint.tag!r}"
        )
        return issues

    policy = _tag_seed_policy(tag_hint.tag, tags_by_seed_policy)
    if policy is None:
        issues.append(
            f"{candidate_prefix} tag {tag_hint.tag!r} has no Retrograde seed " "policy"
        )
        return issues
    if policy == "prompt_visible_only":
        issues.append(
            f"{candidate_prefix} tag {tag_hint.tag!r} is prompt-visible-only "
            "and cannot be a mechanical seed write"
        )
        return issues
    if policy == "event_anchored":
        if not tag_hint.supporting_event_ref:
            issues.append(
                f"{candidate_prefix} event-anchored tag {tag_hint.tag!r} "
                "requires supporting_event_ref"
            )
        elif tag_hint.supporting_event_ref not in events_by_ref:
            issues.append(
                f"{candidate_prefix} tag {tag_hint.tag!r} references unknown "
                f"supporting_event_ref {tag_hint.supporting_event_ref!r}"
            )
    elif (
        tag_hint.supporting_event_ref
        and tag_hint.supporting_event_ref not in events_by_ref
    ):
        issues.append(
            f"{candidate_prefix} tag {tag_hint.tag!r} references unknown "
            f"supporting_event_ref {tag_hint.supporting_event_ref!r}"
        )

    return issues


def _pair_tag_issues(
    *,
    candidate_prefix: str,
    pair_hint: RetrogradePairTagHint,
    entity_kinds: set[str],
    pair_definitions: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    issues: list[str] = []
    if pair_hint.subject_kind not in entity_kinds:
        issues.append(
            f"{candidate_prefix} pair tag {pair_hint.tag!r} uses unknown "
            f"subject_kind {pair_hint.subject_kind!r}"
        )
    if pair_hint.object_kind not in entity_kinds:
        issues.append(
            f"{candidate_prefix} pair tag {pair_hint.tag!r} uses unknown "
            f"object_kind {pair_hint.object_kind!r}"
        )

    definition = pair_definitions.get(pair_hint.tag)
    if definition is None:
        issues.append(f"{candidate_prefix} proposes unknown pair tag {pair_hint.tag!r}")
        return issues

    subject_kinds = set(definition["subject_kinds"])
    object_kinds = set(definition["object_kinds"])
    if pair_hint.subject_kind not in subject_kinds:
        issues.append(
            f"{candidate_prefix} pair tag {pair_hint.tag!r} does not allow "
            f"subject_kind {pair_hint.subject_kind!r}"
        )
    if pair_hint.object_kind not in object_kinds:
        issues.append(
            f"{candidate_prefix} pair tag {pair_hint.tag!r} does not allow "
            f"object_kind {pair_hint.object_kind!r}"
        )
    return issues


def _relationship_issues(
    *,
    candidate_prefix: str,
    relationship_hint: RetrogradeRelationshipHint,
    entity_kinds: set[str],
    relationship_types: set[str],
) -> list[str]:
    issues: list[str] = []
    if relationship_hint.subject_kind not in entity_kinds:
        issues.append(
            f"{candidate_prefix} relationship uses unknown subject_kind "
            f"{relationship_hint.subject_kind!r}"
        )
    if relationship_hint.object_kind not in entity_kinds:
        issues.append(
            f"{candidate_prefix} relationship uses unknown object_kind "
            f"{relationship_hint.object_kind!r}"
        )
    if relationship_hint.relationship_type not in relationship_types:
        issues.append(
            f"{candidate_prefix} proposes unknown relationship_type "
            f"{relationship_hint.relationship_type!r}"
        )
    return issues


def _tag_seed_policy(
    tag: str,
    tags_by_seed_policy: Mapping[str, set[str]],
) -> Optional[str]:
    for policy, tags in tags_by_seed_policy.items():
        if tag in tags:
            return policy
    return None


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


def _prompt_response_contract() -> dict[str, Any]:
    """Return a compact prompt-facing response contract.

    The full Pydantic JSON schema remains in the packet and is supplied to
    Skald by Pydantic AI. Duplicating it inside the prompt bloats live calls.
    """

    return {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "top_level_fields": [
            "schema_version",
            "candidates",
            "selected_seed_ids",
            "rejected_seed_ids",
            "selection_notes",
        ],
        "candidate_fields": [
            "seed_id",
            "summary",
            "origin_friction",
            "present_leaf_anchor",
            "coverage_functions",
            "mechanical_hints",
            "defer_or_reject_if",
        ],
        "mechanical_hint_fields": [
            "events",
            "single_entity_tags",
            "pair_tags",
            "relationships",
        ],
    }


def _hard_validation_rules() -> list[str]:
    """Return concise Skald-facing rules mirrored by local validation."""

    return [
        (
            "Every event_anchored single_entity_tag must include "
            "supporting_event_ref that matches a mechanical_hints.events event_ref "
            "inside the same candidate."
        ),
        (
            "Prompt-visible-only tags may influence prose but must not appear in "
            "mechanical_hints.single_entity_tags."
        ),
        (
            "Pair tags must use the exact subject_kind/object_kind constraints "
            "from multi_entity_tag_definitions."
        ),
        (
            "selected_seed_ids and rejected_seed_ids must reference returned "
            "candidate seed_id values, and a seed cannot be both selected and "
            "rejected."
        ),
        "If a hint is marginal or cannot satisfy these rules, omit the hint.",
    ]


def _optional_positive_int(value: Any) -> Optional[int]:
    if not isinstance(value, int) or value <= 0:
        return None
    return value


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


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

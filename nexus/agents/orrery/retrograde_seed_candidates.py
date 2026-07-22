"""Skald-facing Retrograde seed candidate schema and validation."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Mapping, Optional, Sequence, cast

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from nexus.agents.orrery.retrograde_junctions import resolve_junctions
from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    SeedEligibleVocabulary,
)

EntityRef = Annotated[str, Field(min_length=1, max_length=ENTITY_REF_MAX_LENGTH)]
"""Prompt-local entity ref: a proper name, never a description.

Bounded because refs become canonical ``name`` values when persistence
stages minimum-viable stubs (``characters.name``/``places.name`` are
``varchar(50)``).
"""

SeedCandidateSchemaVersion = Literal["orrery_retrograde_seed_candidates.v0"]
SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION: SeedCandidateSchemaVersion = (
    "orrery_retrograde_seed_candidates.v0"
)

RetrogradeProjectType = Literal[
    "plan_relocation",
    "recruit_ally",
    "build_venture",
    "pursue_romance",
    "court_patron",
    "seek_redemption",
]


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
    participating_entities: list[EntityRef] = Field(
        default_factory=list,
        description=(
            "Prompt-local entity names involved in the event. Each entry is a "
            f"proper name of at most {ENTITY_REF_MAX_LENGTH} characters, never "
            "a descriptive phrase."
        ),
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeSingleEntityTagHint(BaseModel):
    """One proposed single-entity tag outcome for a candidate seed."""

    entity_ref: EntityRef = Field(
        description=(
            "Prompt-local entity name receiving the tag: a proper name of at "
            f"most {ENTITY_REF_MAX_LENGTH} characters, never a description."
        ),
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

    subject_ref: EntityRef
    subject_kind: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    object_ref: EntityRef
    object_kind: str = Field(min_length=1)
    rationale: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeRelationshipHint(BaseModel):
    """One proposed relationship primitive implied by a candidate seed."""

    subject_ref: EntityRef
    subject_kind: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    object_ref: EntityRef
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


class RetrogradeWireSingleEntityTagHint(BaseModel):
    """Provider-facing tag hint using a grammar-safe kind/tag enum ref."""

    entity_ref: EntityRef
    tag_ref: str = Field(
        min_length=1,
        description="Exact single-entity tag ref in the form entity_kind|tag.",
    )
    supporting_event_ref: str = Field(
        default="",
        description="Event ref for event-anchored tags, or empty string.",
    )
    rationale: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWirePairTagHint(BaseModel):
    """Provider-facing pair tag hint using a grammar-safe kind/tag enum ref."""

    subject_ref: EntityRef
    tag_ref: str = Field(
        min_length=1,
        description="Exact pair tag ref in the form subject_kind|object_kind|tag.",
    )
    object_ref: EntityRef
    rationale: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWireRelationshipHint(BaseModel):
    """Provider-facing relationship hint using a grammar-safe kind/type ref."""

    subject_ref: EntityRef
    relationship_ref: str = Field(
        min_length=1,
        description=(
            "Exact relationship ref in the form "
            "subject_kind|object_kind|relationship_type."
        ),
    )
    object_ref: EntityRef
    rationale: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWireMechanicalHints(BaseModel):
    """Provider-facing hints with dynamic enum fields injected at runtime."""

    events: list[RetrogradeSeedEventHint] = Field(default_factory=list)
    single_entity_tags: list[RetrogradeWireSingleEntityTagHint] = Field(
        default_factory=list
    )
    pair_tags: list[RetrogradeWirePairTagHint] = Field(default_factory=list)
    relationships: list[RetrogradeWireRelationshipHint] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWireClaimedEdge(BaseModel):
    """Provider-facing claimed dangling edge (issue #442)."""

    edge_id: str = Field(min_length=1)
    open_endpoint_name: str = Field(
        min_length=1,
        max_length=ENTITY_REF_MAX_LENGTH,
    )
    open_endpoint_kind: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeProjectIntent(BaseModel):
    """Optional long-arc project implied by one generated seed."""

    project_type: RetrogradeProjectType
    target_ref: Optional[EntityRef] = Field(
        default=None,
        description="Compact character/place ref when the project type needs one.",
    )
    rationale: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="after")
    def _validate_typed_target(self) -> "RetrogradeProjectIntent":
        validate_project_target_shape(
            project_type=self.project_type,
            target_ref=self.target_ref,
            context="project intent",
        )
        return self


class RetrogradeWireProjectIntent(BaseModel):
    """Provider-facing twin of :class:`RetrogradeProjectIntent`."""

    project_type: RetrogradeProjectType
    target_ref: str = Field(
        default="",
        max_length=ENTITY_REF_MAX_LENGTH,
        description="Compact target ref, or an empty string when targetless.",
    )
    rationale: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWireSeedCandidate(BaseModel):
    """Provider-facing seed candidate with compact mechanical refs."""

    seed_id: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1200)
    origin_friction: Literal["low", "medium", "high"]
    present_leaf_anchor: str = Field(min_length=1, max_length=800)
    coverage_functions: list[str] = Field(default_factory=list)
    mechanical_hints: RetrogradeWireMechanicalHints = Field(
        default_factory=RetrogradeWireMechanicalHints
    )
    defer_or_reject_if: list[str] = Field(default_factory=list)
    claimed_edges: list[RetrogradeWireClaimedEdge] = Field(default_factory=list)
    project_intent: Optional[RetrogradeWireProjectIntent] = None

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeWireSeedCandidateResponse(BaseModel):
    """Provider-facing seed response with compact mechanical refs."""

    schema_version: SeedCandidateSchemaVersion = SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION
    candidates: list[RetrogradeWireSeedCandidate] = Field(default_factory=list)
    selected_seed_ids: list[str] = Field(default_factory=list)
    rejected_seed_ids: list[str] = Field(default_factory=list)
    selection_notes: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RetrogradeClaimedEdge(BaseModel):
    """A dangling graph edge this seed claims and resolves (issue #442).

    The R3 candidate graph rolls edge ingredients the model did not
    choose; a claim binds the seed to one of them and names the edge's
    open endpoint. The seed's story must make the claimed edge_type true.
    """

    edge_id: str = Field(min_length=1, description="Dangling edge id claimed.")
    open_endpoint_name: str = Field(
        min_length=1,
        max_length=ENTITY_REF_MAX_LENGTH,
        description="Name for the edge's unknown endpoint (new or existing).",
    )
    open_endpoint_kind: str = Field(
        min_length=1,
        description="Entity kind of the named endpoint; must match the edge.",
    )

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
    claimed_edges: list[RetrogradeClaimedEdge] = Field(
        default_factory=list,
        description=(
            "One or two dangling edges from the request's candidate_graph "
            "that this seed claims and resolves."
        ),
    )
    project_intent: Optional[RetrogradeProjectIntent] = Field(
        default=None,
        description="Rare optional project generator carried into R6 weaving.",
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


def seed_candidate_wire_response_model(
    *,
    seed_generation_request: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
) -> type[BaseModel]:
    """Build the provider-facing R4/R5 schema from live Orrery vocabulary."""

    event_hint_model = create_model(
        "RetrogradeWireSeedEventHintRuntime",
        __base__=RetrogradeSeedEventHint,
        event_type=(
            _literal_or_str(vocabulary["event_types"]),
            Field(description="Registered Orrery event type."),
        ),
    )
    single_tag_model = create_model(
        "RetrogradeWireSingleEntityTagHintRuntime",
        __base__=RetrogradeWireSingleEntityTagHint,
        tag_ref=(
            _literal_or_str(_single_entity_tag_refs(vocabulary)),
            Field(
                description=(
                    "Exact single-entity tag ref from "
                    "allowed_vocabulary.single_entity_tag_refs."
                )
            ),
        ),
    )
    pair_tag_model = create_model(
        "RetrogradeWirePairTagHintRuntime",
        __base__=RetrogradeWirePairTagHint,
        tag_ref=(
            _literal_or_str(_pair_tag_refs(vocabulary)),
            Field(
                description=(
                    "Exact pair tag ref from allowed_vocabulary.pair_tag_refs."
                )
            ),
        ),
    )
    relationship_model = create_model(
        "RetrogradeWireRelationshipHintRuntime",
        __base__=RetrogradeWireRelationshipHint,
        relationship_ref=(
            _literal_or_str(_relationship_refs(vocabulary)),
            Field(
                description=(
                    "Exact relationship ref from "
                    "allowed_vocabulary.relationship_refs."
                )
            ),
        ),
    )
    mechanical_hints_model = create_model(
        "RetrogradeWireMechanicalHintsRuntime",
        __base__=RetrogradeWireMechanicalHints,
        events=(list[event_hint_model], Field(default_factory=list)),
        single_entity_tags=(list[single_tag_model], Field(default_factory=list)),
        pair_tags=(list[pair_tag_model], Field(default_factory=list)),
        relationships=(list[relationship_model], Field(default_factory=list)),
    )
    coverage_type = _literal_or_str(_coverage_function_ids(seed_generation_request))
    graph = seed_generation_request.get("candidate_graph") or {}
    edge_ids = [
        str(edge.get("edge_id"))
        for edge in graph.get("dangling_edges", [])
        if isinstance(edge, Mapping) and edge.get("edge_id")
    ]
    endpoint_kinds = sorted(
        {
            str(edge.get("open_endpoint_kind"))
            for edge in graph.get("dangling_edges", [])
            if isinstance(edge, Mapping) and edge.get("open_endpoint_kind")
        }
    )
    claimed_edge_model = create_model(
        "RetrogradeWireClaimedEdgeRuntime",
        __base__=RetrogradeWireClaimedEdge,
        edge_id=(
            _literal_or_str(edge_ids),
            Field(description="Dangling edge id from candidate_graph."),
        ),
        open_endpoint_kind=(
            _literal_or_str(endpoint_kinds),
            Field(description="Entity kind matching the claimed edge."),
        ),
    )
    candidate_model = create_model(
        "RetrogradeWireSeedCandidateRuntime",
        __base__=RetrogradeWireSeedCandidate,
        coverage_functions=(list[coverage_type], Field(default_factory=list)),
        mechanical_hints=(
            mechanical_hints_model,
            Field(default_factory=mechanical_hints_model),
        ),
        claimed_edges=(list[claimed_edge_model], Field(default_factory=list)),
    )
    return create_model(
        "RetrogradeWireSeedCandidateResponseRuntime",
        __base__=RetrogradeWireSeedCandidateResponse,
        candidates=(list[candidate_model], Field(default_factory=list)),
    )


def coerce_seed_candidate_response_payload(
    payload: Mapping[str, Any],
) -> RetrogradeSeedCandidateResponse:
    """Expand provider-facing mechanical refs into the full app contract."""

    data = _expand_wire_seed_candidate_payload(payload)
    data.setdefault("schema_version", SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION)
    return RetrogradeSeedCandidateResponse.model_validate(data)


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
        "candidate_graph": seed_generation_request.get("candidate_graph", {}),
        "selection_rubric": seed_generation_request.get("selection_rubric", {}),
        "project_intent_policy": seed_generation_request.get(
            "project_intent_policy",
            {
                "optional": True,
                "rarity": "At most two candidates per cast should carry an intent.",
                "unresolved_ledger": ["court_patron", "seek_redemption"],
                "trait_bound_hook": [
                    "build_venture",
                    "pursue_romance",
                    "recruit_ally",
                ],
                "target_refs": (
                    "Use the same compact entity-ref language as mechanical_hints."
                ),
            },
        ),
        "prompt_sections": seed_generation_request.get("prompt_sections", []),
        "response_contract": _prompt_response_contract(),
    }
    return (
        "You are Skald-as-weaver for a Retrograde seed-generation pass.\n"
        "Generate surprising candidate history seeds and leave all "
        "persistence to a later reviewed expansion pass. Do NOT select in "
        "this pass: return selected_seed_ids and rejected_seed_ids as empty "
        "lists — selection happens in a separate, decoupled call.\n"
        "candidate_graph.dangling_edges are rolled ingredients you did not "
        "choose: every candidate must claim 1-2 edge_ids via claimed_edges, "
        "name each claimed edge's open endpoint, and make the edge_type "
        "true in the seed's story. Reconcile the roll; do not ignore it.\n"
        "candidate_graph.junctions are mandatory shared-entity constraints: "
        "each junction's two edge_ids must be claimed exactly once by two "
        "different candidates, and both claims must use the same endpoint "
        "name and required kind.\n"
        "Keep summaries, rationales, and rejection conditions compact.\n"
        "If a mechanical hint cannot satisfy the hard validation rules, omit it.\n"
        "Project intent is optional and rare: propose it only for a seed serving "
        "the listed unresolved_ledger or trait_bound_hook functions, and use it "
        "on at most two candidates in the cast.\n"
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

    response = coerce_seed_candidate_response_payload(payload)
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

    from pydantic_ai import ModelRetry

    from nexus.api.config_utils import (
        get_new_story_model,
        get_wizard_max_tokens,
        get_wizard_retry_budget,
    )
    from nexus.api.native_structured_output import build_native_structured_provider

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
    schema_model = seed_candidate_wire_response_model(
        seed_generation_request=seed_generation_request,
        vocabulary=vocabulary,
    )

    selected_model = model_name or get_new_story_model()
    provider = build_native_structured_provider(
        model=selected_model,
        max_tokens=max_tokens or get_wizard_max_tokens(),
        system_prompt=(
            "You are Skald-as-weaver for a NEXUS Retrograde seed pass. "
            "Generate candidate history seeds only — selection happens in a "
            "separate call — and do not claim any canonical write has "
            "occurred."
        ),
        structured_output_retries=get_wizard_retry_budget(),
    )

    async def _validate_output(
        _ctx: Any,
        output: BaseModel,
    ) -> RetrogradeSeedCandidateResponse:
        try:
            payload = coerce_seed_candidate_response_payload(
                output.model_dump(mode="json")
            )
            return validate_seed_candidate_response(
                payload=payload.model_dump(mode="json"),
                seed_generation_request=seed_generation_request,
                vocabulary=vocabulary,
            )
        except RetrogradeSeedCandidateValidationError as exc:
            raise ModelRetry(
                "Retrograde seed candidate mechanics failed validation. "
                "Repair the JSON by omitting invalid mechanical hints or adding "
                f"the required refs:\n{exc}"
            ) from exc

    provider.output_validator = _validate_output
    response, _llm_response = provider.get_structured_completion(
        prompt,
        schema_model,
    )
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


def _expand_wire_seed_candidate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return data

    expanded_candidates = []
    for candidate in candidates:
        candidate_row = dict(candidate)
        hints = candidate_row.get("mechanical_hints")
        if isinstance(hints, Mapping):
            candidate_row["mechanical_hints"] = _expand_wire_mechanical_hints(hints)
        project_intent = candidate_row.get("project_intent")
        if isinstance(project_intent, Mapping):
            candidate_row["project_intent"] = {
                **dict(project_intent),
                "target_ref": _none_if_empty(project_intent.get("target_ref")),
            }
        expanded_candidates.append(candidate_row)

    data["candidates"] = expanded_candidates
    if data.get("selection_notes") == "":
        data["selection_notes"] = None
    return data


def _expand_wire_mechanical_hints(hints: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(hints)
    data["single_entity_tags"] = [
        _expand_wire_single_entity_tag(tag)
        for tag in data.get("single_entity_tags") or []
    ]
    data["pair_tags"] = [
        _expand_wire_pair_tag(tag) for tag in data.get("pair_tags") or []
    ]
    data["relationships"] = [
        _expand_wire_relationship(relationship)
        for relationship in data.get("relationships") or []
    ]
    return data


def _expand_wire_single_entity_tag(tag: Mapping[str, Any]) -> dict[str, Any]:
    if "tag_ref" not in tag:
        return dict(tag)

    entity_kind, tag_name = _split_ref(str(tag.get("tag_ref", "")), parts=2)
    return {
        "entity_ref": tag.get("entity_ref"),
        "entity_kind": entity_kind,
        "tag": tag_name,
        "supporting_event_ref": _none_if_empty(tag.get("supporting_event_ref")),
        "rationale": _none_if_empty(tag.get("rationale")),
    }


def _expand_wire_pair_tag(tag: Mapping[str, Any]) -> dict[str, Any]:
    if "tag_ref" not in tag:
        return dict(tag)

    subject_kind, object_kind, tag_name = _split_ref(
        str(tag.get("tag_ref", "")),
        parts=3,
    )
    return {
        "subject_ref": tag.get("subject_ref"),
        "subject_kind": subject_kind,
        "tag": tag_name,
        "object_ref": tag.get("object_ref"),
        "object_kind": object_kind,
        "rationale": _none_if_empty(tag.get("rationale")),
    }


def _expand_wire_relationship(relationship: Mapping[str, Any]) -> dict[str, Any]:
    if "relationship_ref" not in relationship:
        return dict(relationship)

    subject_kind, object_kind, relationship_type = _split_ref(
        str(relationship.get("relationship_ref", "")),
        parts=3,
    )
    return {
        "subject_ref": relationship.get("subject_ref"),
        "subject_kind": subject_kind,
        "relationship_type": relationship_type,
        "object_ref": relationship.get("object_ref"),
        "object_kind": object_kind,
        "rationale": _none_if_empty(relationship.get("rationale")),
    }


def _split_ref(value: str, *, parts: int) -> tuple[str, ...]:
    split = value.split("|")
    if len(split) != parts or any(part == "" for part in split):
        raise ValueError(
            f"Malformed compact Retrograde ref {value!r}; expected {parts} "
            "non-empty pipe-delimited parts"
        )
    return tuple(split)


def _none_if_empty(value: Any) -> Any:
    if value == "":
        return None
    return value


def validate_project_target_shape(
    *,
    project_type: str,
    target_ref: Optional[str],
    context: str,
) -> None:
    character_targeted = {
        "recruit_ally",
        "pursue_romance",
        "court_patron",
        "seek_redemption",
    }
    if project_type == "build_venture" and target_ref is not None:
        raise ValueError(f"{context} build_venture forbids a target_ref")
    if project_type in character_targeted and target_ref is None:
        raise ValueError(f"{context} {project_type} requires a target_ref")


def _literal_or_str(values: list[str]) -> Any:
    unique_values = tuple(dict.fromkeys(str(value) for value in values if value))
    if not unique_values:
        return str
    return Literal.__getitem__(unique_values)


def _coverage_function_ids(seed_generation_request: Mapping[str, Any]) -> list[str]:
    return [
        str(function.get("id"))
        for function in seed_generation_request.get("coverage_functions", [])
        if isinstance(function, Mapping) and function.get("id")
    ]


def _single_entity_tag_refs(vocabulary: SeedEligibleVocabulary) -> list[str]:
    tags_by_entity_kind = {
        kind: set(tags)
        for kind, tags in vocabulary.get("registered_tags_by_entity_kind", {}).items()
    }
    allowed_mechanical_tags = set(
        vocabulary.get("registered_tags_by_seed_policy", {}).get("stable_seed", [])
    ) | set(
        vocabulary.get("registered_tags_by_seed_policy", {}).get("event_anchored", [])
    )
    if not tags_by_entity_kind:
        tags_by_entity_kind = {
            kind: set(vocabulary.get("registered_single_entity_tags", []))
            for kind in vocabulary["entity_kinds"]
        }

    refs: list[str] = []
    for kind in vocabulary["entity_kinds"]:
        for tag in sorted(
            tags_by_entity_kind.get(kind, set()) & allowed_mechanical_tags
        ):
            refs.append(_join_ref(kind, tag))
    return refs


def _pair_tag_refs(vocabulary: SeedEligibleVocabulary) -> list[str]:
    refs: list[str] = []
    for definition in vocabulary["multi_entity_tag_definitions"]:
        tag = str(definition["tag"])
        for subject_kind in definition["subject_kinds"]:
            for object_kind in definition["object_kinds"]:
                refs.append(_join_ref(subject_kind, object_kind, tag))
    return refs


def _relationship_refs(vocabulary: SeedEligibleVocabulary) -> list[str]:
    refs: list[str] = []
    for subject_kind in vocabulary["entity_kinds"]:
        for object_kind in vocabulary["entity_kinds"]:
            for relationship_type in vocabulary["relationship_types"]:
                refs.append(_join_ref(subject_kind, object_kind, relationship_type))
    return refs


def _join_ref(*parts: str) -> str:
    return "|".join(str(part) for part in parts)


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
    tags_by_entity_kind = {
        kind: set(tags)
        for kind, tags in vocabulary.get("registered_tags_by_entity_kind", {}).items()
    }

    graph = _mapping(seed_generation_request.get("candidate_graph"))
    graph_edges = {
        str(edge.get("edge_id")): edge
        for edge in graph.get("dangling_edges", [])
        if isinstance(edge, Mapping) and edge.get("edge_id")
    }
    contract = _mapping(graph.get("attachment_contract"))
    claims_min = _optional_positive_int(contract.get("claims_per_seed_min")) or 1
    claims_max = _optional_positive_int(contract.get("claims_per_seed_max")) or 2

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
                tags_by_entity_kind=tags_by_entity_kind,
            )
        )
        if graph_edges:
            issues.extend(
                _claimed_edge_issues(
                    candidate=candidate,
                    graph_edges=graph_edges,
                    claims_min=claims_min,
                    claims_max=claims_max,
                )
            )

    resolved_junctions, junction_issues = resolve_junctions(
        seed_generation_request=seed_generation_request,
        candidates_payload=response.model_dump(mode="json"),
    )
    issues.extend(junction_issues)

    selection_started = bool(response.selected_seed_ids or response.rejected_seed_ids)
    if selection_started:
        issues.extend(
            _selection_contract_issues(
                candidate_ids=[candidate.seed_id for candidate in response.candidates],
                selected_seed_ids=response.selected_seed_ids,
                rejected_seed_ids=response.rejected_seed_ids,
                select_limit=select_limit,
                resolved_junctions=resolved_junctions,
                require_selected=True,
                require_complete=True,
            )
        )

    return issues


def _claimed_edge_issues(
    *,
    candidate: RetrogradeSeedCandidate,
    graph_edges: Mapping[str, Mapping[str, Any]],
    claims_min: int,
    claims_max: int,
) -> list[str]:
    """Enforce the R3 attachment contract: rolled ingredients must be used.

    A candidate that ignores the dice is the failure mode issue #442
    exists to prevent — the model quietly reverting to its own priors.
    """

    issues: list[str] = []
    prefix = f"candidate {candidate.seed_id!r}"
    claims = candidate.claimed_edges

    if len(claims) < claims_min:
        issues.append(
            f"{prefix} claims {len(claims)} dangling edges; the attachment "
            f"contract requires at least {claims_min}"
        )
    if len(claims) > claims_max:
        issues.append(
            f"{prefix} claims {len(claims)} dangling edges, exceeding the "
            f"contract maximum {claims_max}"
        )
    duplicate_ids = _duplicates([claim.edge_id for claim in claims])
    if duplicate_ids:
        issues.append(f"{prefix} claims duplicate edges {sorted(duplicate_ids)}")

    for claim in claims:
        edge = graph_edges.get(claim.edge_id)
        if edge is None:
            issues.append(
                f"{prefix} claims unknown edge {claim.edge_id!r}; valid ids "
                f"are {sorted(graph_edges)}"
            )
            continue
        expected_kind = str(edge.get("open_endpoint_kind"))
        if claim.open_endpoint_kind != expected_kind:
            issues.append(
                f"{prefix} resolves edge {claim.edge_id!r} with endpoint "
                f"kind {claim.open_endpoint_kind!r}; the edge requires "
                f"{expected_kind!r}"
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
    tags_by_entity_kind: Mapping[str, set[str]],
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
                tags_by_entity_kind=tags_by_entity_kind,
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
    tags_by_entity_kind: Mapping[str, set[str]],
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
    # Persistence resolves tag <-> entity-kind compatibility through the
    # slot's tag_category_registry; enforce the same constraint here so an
    # incompatible hint is repaired at generation time instead of blocking
    # the wizard transition. Only enforceable when the live registry mapping
    # is present in the vocabulary (i.e., enumeration ran against a slot).
    if tags_by_entity_kind and tag_hint.tag not in tags_by_entity_kind.get(
        tag_hint.entity_kind, set()
    ):
        issues.append(
            f"{candidate_prefix} tag {tag_hint.tag!r} is not registered for "
            f"entity_kind {tag_hint.entity_kind!r}"
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
        # The validator enforces per-kind tag registration, so Skald must see
        # the same mapping up front; otherwise kind mismatches burn retries.
        "registered_tags_by_entity_kind": vocabulary.get(
            "registered_tags_by_entity_kind", {}
        ),
        "multi_entity_tag_definitions": vocabulary["multi_entity_tag_definitions"],
        "single_entity_tag_refs": _single_entity_tag_refs(vocabulary),
        "pair_tag_refs": _pair_tag_refs(vocabulary),
        "relationship_refs": _relationship_refs(vocabulary),
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
            "claimed_edges",
            "project_intent",
        ],
        "mechanical_hint_fields": [
            "events",
            "single_entity_tags: entity_ref, tag_ref, supporting_event_ref, rationale",
            "pair_tags: subject_ref, tag_ref, object_ref, rationale",
            "relationships: subject_ref, relationship_ref, object_ref, rationale",
        ],
        "compact_ref_format": {
            "single_entity_tags.tag_ref": "entity_kind|tag",
            "pair_tags.tag_ref": "subject_kind|object_kind|tag",
            "relationships.relationship_ref": (
                "subject_kind|object_kind|relationship_type"
            ),
            "claimed_edges": ("edge_id, open_endpoint_name, open_endpoint_kind"),
            "project_intent": "project_type, target_ref, rationale",
            "absence": "Use empty strings for absent supporting_event_ref/rationale.",
        },
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
            "single_entity_tags use tag_ref values from "
            "allowed_vocabulary.single_entity_tag_refs; this encodes the legal "
            "entity_kind|tag pair."
        ),
        (
            "Prompt-visible-only tags may influence prose but must not appear in "
            "mechanical_hints.single_entity_tags."
        ),
        (
            "Pair tags use tag_ref values from allowed_vocabulary.pair_tag_refs; "
            "relationships use relationship_ref values from "
            "allowed_vocabulary.relationship_refs."
        ),
        (
            "Single-entity tags must be registered for the tagged entity_kind "
            "in registered_tags_by_entity_kind; a tag listed only under another "
            "kind is illegal."
        ),
        (
            "selected_seed_ids and rejected_seed_ids must reference returned "
            "candidate seed_id values, and a seed cannot be both selected and "
            "rejected."
        ),
        (
            "Every candidate_graph.junctions entry has exactly two edge legs. "
            "Those legs must be claimed exactly once by two different "
            "candidates using the same endpoint kind and normalized name."
        ),
        (
            "Entity refs (entity_ref, subject_ref, object_ref, "
            "participating_entities) are proper names of at most "
            f"{ENTITY_REF_MAX_LENGTH} characters -- never sentences or "
            "descriptive phrases. Implied new entities get a short invented "
            "name, not a description."
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


def _selection_contract_issues(
    *,
    candidate_ids: list[str],
    selected_seed_ids: list[str],
    rejected_seed_ids: list[str],
    select_limit: Optional[int],
    resolved_junctions: Sequence[Mapping[str, Any]],
    require_selected: bool,
    require_complete: bool,
) -> list[str]:
    """Return ordinary R5 accounting and junction-atomicity violations."""

    issues: list[str] = []
    known = set(candidate_ids)
    selected = set(selected_seed_ids)
    rejected = set(rejected_seed_ids)
    unknown = sorted((selected | rejected) - known)
    if unknown:
        issues.append(f"selection references unknown seed ids {unknown}")
    if require_selected and not selected_seed_ids:
        issues.append("selection must select at least one seed")
    if select_limit is not None and len(selected_seed_ids) > select_limit:
        issues.append(
            f"response selected {len(selected_seed_ids)} seeds, exceeding "
            f"target {select_limit}"
        )
    overlap = sorted(selected & rejected)
    if overlap:
        issues.append(f"seed ids both selected and rejected: {overlap}")
    if require_complete:
        unaccounted = sorted(known - selected - rejected)
        if unaccounted:
            issues.append(
                "every candidate must be selected or rejected; missing "
                f"{unaccounted}"
            )

    for junction in resolved_junctions:
        junction_id = str(junction.get("junction_id") or "")
        seed_ids = [str(seed_id) for seed_id in junction.get("seed_ids") or []]
        dispositions = []
        for seed_id in seed_ids:
            if seed_id in selected and seed_id in rejected:
                dispositions.append("both")
            elif seed_id in selected:
                dispositions.append("selected")
            elif seed_id in rejected:
                dispositions.append("rejected")
            else:
                dispositions.append("unaccounted")
        if len(set(dispositions)) > 1:
            issues.append(
                f"junction {junction_id!r} seeds {seed_ids} must be selected "
                "or rejected together"
            )

    return issues


class RetrogradeSeedSelectionResponse(BaseModel):
    """Structured response from the decoupled R5 selection pass."""

    selected_seed_ids: list[str] = Field(default_factory=list)
    rejected_seed_ids: list[str] = Field(default_factory=list)
    selection_notes: str = Field(default="")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def render_seed_selection_prompt(
    *,
    seed_generation_request: Mapping[str, Any],
    candidates_payload: Mapping[str, Any],
) -> str:
    """Render the R5 selection prompt: a menu decoupled from generation.

    Selection in the same call as generation collapses into
    self-selection (the model anchors on its own output); the spec's
    "semi-constrained selection" gets its own context instead
    (issue #442).
    """

    resolved_junctions, junction_issues = resolve_junctions(
        seed_generation_request=seed_generation_request,
        candidates_payload=candidates_payload,
    )
    prompt_payload = {
        "task": (
            "Select the strongest subset of the candidate seeds below. "
            "You did not write these; judge them on the rubric alone. "
            "Return JSON only."
        ),
        "budget": seed_generation_request.get("budget", {}),
        "selection_rubric": seed_generation_request.get("selection_rubric", {}),
        "weird_policy": seed_generation_request.get("weird_policy", {}),
        "attachment_contract": (
            seed_generation_request.get("candidate_graph", {}) or {}
        ).get("attachment_contract", {}),
        # Full edge definitions (edge_type, anchor, orthogonality,
        # guidance): without them the judge cannot tell an honored claim
        # from lip service.
        "dangling_edges": (
            seed_generation_request.get("candidate_graph", {}) or {}
        ).get("dangling_edges", []),
        "resolved_junctions": resolved_junctions,
        "junction_resolution_issues": junction_issues,
        "candidates": candidates_payload.get("candidates", []),
    }
    return (
        "You are the Retrograde selection judge for a NEXUS seed pass.\n"
        "Choose up to budget.select_target seeds. Prefer seeds that serve "
        "coverage functions, honor their claimed dangling edges with "
        "conviction rather than lip service, and would take real creative "
        "work to weave into the story — merge-difficulty is value, not "
        "risk. Reject seeds that ignore their claimed edges.\n"
        "Resolved junction seed pairs are atomic: select both member seeds "
        "or reject both. A pair consumes two ordinary selection slots.\n"
        "Every non-selected candidate must appear in rejected_seed_ids.\n\n"
        "RETROGRADE_SEED_SELECTION_REQUEST:\n"
        f"{json.dumps(prompt_payload, indent=2, sort_keys=True)}"
    )


def select_seed_candidates_with_skald(
    *,
    packet: Mapping[str, Any],
    candidates_payload: Mapping[str, Any],
    model_name: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict[str, Any]:
    """Make the decoupled R5 selection call over generated candidates."""

    from pydantic_ai import ModelRetry

    from nexus.api.config_utils import (
        get_new_story_model,
        get_wizard_max_tokens,
        get_wizard_retry_budget,
    )
    from nexus.api.native_structured_output import build_native_structured_provider

    seed_generation_request = _required_mapping(
        packet.get("seed_generation_request"),
        "packet.seed_generation_request",
    )
    candidate_ids = [
        str(candidate.get("seed_id"))
        for candidate in candidates_payload.get("candidates", [])
        if isinstance(candidate, Mapping) and candidate.get("seed_id")
    ]
    if not candidate_ids:
        raise ValueError("Seed selection requires at least one candidate")

    budget = _mapping(seed_generation_request.get("budget"))
    select_limit = _optional_positive_int(budget.get("select_target"))
    resolved_junctions, junction_issues = resolve_junctions(
        seed_generation_request=seed_generation_request,
        candidates_payload=candidates_payload,
    )
    if junction_issues:
        formatted = "\n".join(f"- {issue}" for issue in junction_issues)
        raise RetrogradeSeedCandidateValidationError(
            "Seed selection received unresolved R3 junctions:\n" + formatted
        )

    prompt = render_seed_selection_prompt(
        seed_generation_request=seed_generation_request,
        candidates_payload=candidates_payload,
    )
    selection_model = create_model(
        "RetrogradeSeedSelectionResponseRuntime",
        __base__=RetrogradeSeedSelectionResponse,
        selected_seed_ids=(
            list[_literal_or_str(candidate_ids)],
            Field(default_factory=list),
        ),
        rejected_seed_ids=(
            list[_literal_or_str(candidate_ids)],
            Field(default_factory=list),
        ),
    )

    selected_model = model_name or get_new_story_model()
    provider = build_native_structured_provider(
        model=selected_model,
        max_tokens=max_tokens or get_wizard_max_tokens(),
        system_prompt=(
            "You are the Retrograde selection judge for a NEXUS seed pass. "
            "Judge the provided candidates on the rubric; you did not write "
            "them. No canonical writes occur at this stage."
        ),
        structured_output_retries=get_wizard_retry_budget(),
    )

    async def _validate_output(
        _ctx: Any,
        output: BaseModel,
    ) -> RetrogradeSeedSelectionResponse:
        selection = RetrogradeSeedSelectionResponse.model_validate(
            output.model_dump(mode="json")
        )
        issues = _selection_contract_issues(
            candidate_ids=candidate_ids,
            selected_seed_ids=selection.selected_seed_ids,
            rejected_seed_ids=selection.rejected_seed_ids,
            select_limit=select_limit,
            resolved_junctions=resolved_junctions,
            require_selected=True,
            require_complete=True,
        )
        if issues:
            raise ModelRetry(
                "Retrograde seed selection failed validation:\n"
                + "\n".join(f"- {issue}" for issue in issues)
            )
        return selection

    provider.output_validator = _validate_output
    selection, _llm_response = provider.get_structured_completion(
        prompt,
        selection_model,
    )
    if not isinstance(selection, RetrogradeSeedSelectionResponse):
        raise TypeError(
            "Skald seed selection call returned "
            f"{type(selection).__name__}, expected RetrogradeSeedSelectionResponse"
        )
    return {
        "model": selected_model,
        "prompt_chars": len(prompt),
        "selection": selection.model_dump(mode="json"),
    }


def run_seed_stage(
    *,
    packet: Mapping[str, Any],
    model_name: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict[str, Any]:
    """Run R4 generation and R5 selection as decoupled calls, merged.

    Returns the same shape generate_seed_candidates_with_skald returned
    when it selected inline, so R6 expansion and persistence are
    untouched downstream.
    """

    generation = generate_seed_candidates_with_skald(
        packet=packet,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    candidates_payload = dict(generation["seed_candidate_response"])
    selection_result = select_seed_candidates_with_skald(
        packet=packet,
        candidates_payload=candidates_payload,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    selection = selection_result["selection"]
    candidates_payload["selected_seed_ids"] = list(selection["selected_seed_ids"])
    candidates_payload["rejected_seed_ids"] = list(selection["rejected_seed_ids"])
    if selection.get("selection_notes"):
        candidates_payload["selection_notes"] = selection["selection_notes"]

    seed_generation_request = _required_mapping(
        packet.get("seed_generation_request"),
        "packet.seed_generation_request",
    )
    vocabulary = _seed_vocabulary(packet.get("seed_eligible_vocabulary"))
    merged = validate_seed_candidate_response(
        payload=candidates_payload,
        seed_generation_request=seed_generation_request,
        vocabulary=vocabulary,
    )
    return {
        "model": generation["model"],
        "selection_model": selection_result["model"],
        "prompt_chars": generation["prompt_chars"],
        "selection_prompt_chars": selection_result["prompt_chars"],
        "seed_candidate_response": merged.model_dump(mode="json"),
    }

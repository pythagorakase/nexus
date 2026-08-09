"""Context state tracking for LORE's custom memory subsystem."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Union,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    StrictInt,
    model_validator,
)

logger = logging.getLogger(__name__)


MemoryIdentity = Union[int, str]
RETROGRADE_SUMMARY_CONTENT_TYPE = "retrograde_summary"
RETROGRADE_SUMMARY_ID_PREFIX = "retrograde_summary:"
PASS2_BASELINE_SCHEMA_VERSION = 1
PASS2_BASELINE_PRODUCER = "nexus.memory.context_memory_manager"

PersistedRetrogradeIdentity = Annotated[
    str,
    Field(pattern=r"^retrograde_summary:[1-9][0-9]*$"),
]
PersistedMemoryIdentity = Union[StrictInt, PersistedRetrogradeIdentity]


class Pass2BaselineV1(BaseModel):
    """Durable Pass-1 state required to run Pass 2 on the next turn."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = PASS2_BASELINE_SCHEMA_VERSION
    producer: Literal["nexus.memory.context_memory_manager"] = PASS2_BASELINE_PRODUCER
    config_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    parent_chunk_id: Optional[PositiveInt] = None
    memory_identities: List[PersistedMemoryIdentity]
    prior_token_accounting: Dict[str, NonNegativeInt]
    remaining_budget: NonNegativeInt

    @model_validator(mode="after")
    def validate_memory_identities(self) -> "Pass2BaselineV1":
        """Reject booleans, non-positive chunk ids, and duplicate identities."""

        identities: List[MemoryIdentity] = list(self.memory_identities)
        for identity in identities:
            if isinstance(identity, int) and identity <= 0:
                raise ValueError("narrative memory identities must be positive")
        if len(set(identities)) != len(identities):
            raise ValueError("memory identities must be unique")
        return self


def validate_staged_pass2_baseline(payload: Any) -> Pass2BaselineV1:
    """Validate an incubator baseline and require it to remain ID-unbound."""

    baseline = Pass2BaselineV1.model_validate(payload)
    if baseline.parent_chunk_id is not None:
        raise ValueError("Staged Pass-2 baseline must not predict an accepted chunk id")
    return baseline


def bind_pass2_baseline(payload: Any, chunk_id: int) -> Pass2BaselineV1:
    """Bind a validated staged baseline to the actual accepted chunk id."""

    if isinstance(chunk_id, bool) or not isinstance(chunk_id, int) or chunk_id <= 0:
        raise ValueError("Accepted Pass-2 baseline chunk id must be positive")
    staged = validate_staged_pass2_baseline(payload)
    return staged.model_copy(update={"parent_chunk_id": chunk_id})


def is_retrograde_summary(memory: Dict[str, Any]) -> bool:
    """Return whether a retrieval row is a dedicated Retrograde summary."""

    if memory.get("content_type") == RETROGRADE_SUMMARY_CONTENT_TYPE:
        return True
    for key in ("memory_id", "id"):
        value = memory.get(key)
        if isinstance(value, str) and value.startswith(RETROGRADE_SUMMARY_ID_PREFIX):
            return True
    return False


def memory_identity(memory: Dict[str, Any]) -> Optional[MemoryIdentity]:
    """Return a corpus-aware identity without inventing a narrative chunk id.

    Narrative rows retain the historical integer coercion used by LORE's
    baseline state. Retrograde summaries use their public typed identity so a
    summary id can never collide with a narrative chunk id.
    """

    if is_retrograde_summary(memory):
        raw_identity = memory.get("memory_id") or memory.get("id")
        if isinstance(raw_identity, str) and raw_identity.startswith(
            RETROGRADE_SUMMARY_ID_PREFIX
        ):
            return raw_identity

        summary_id = memory.get("summary_id")
        if summary_id is None:
            return None
        try:
            return f"{RETROGRADE_SUMMARY_ID_PREFIX}{int(summary_id)}"
        except (TypeError, ValueError):
            return None

    raw_id = memory.get("chunk_id")
    if raw_id is None:
        raw_id = memory.get("id")
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


@dataclass
class ContextPackage:
    """State container for baseline and incremental context across passes."""

    baseline_chunks: Set[MemoryIdentity] = field(default_factory=set)
    baseline_entities: Dict[str, Any] = field(default_factory=dict)
    baseline_themes: List[str] = field(default_factory=list)
    structured_passages: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    divergence_detected: bool = False
    divergence_confidence: float = 0.0
    additional_chunks: Set[MemoryIdentity] = field(default_factory=set)
    gap_analysis: Dict[str, str] = field(default_factory=dict)


@dataclass
class PassTransition:
    """Information needed to transition from Pass 1 (baseline) to Pass 2."""

    storyteller_output: str
    expected_user_themes: List[str] = field(default_factory=list)
    assembled_context: Dict[str, Any] = field(default_factory=dict)
    remaining_budget: int = 0
    structured_passages: List[Dict[str, Any]] = field(default_factory=list)


class ContextStateManager:
    """Manage shared state between Pass 1 and Pass 2."""

    def __init__(self) -> None:
        self._context: Optional[ContextPackage] = None
        self._transition: Optional[PassTransition] = None
        self._chunk_cache: Dict[MemoryIdentity, Dict[str, Any]] = {}
        self._additional_chunk_token_costs: Dict[MemoryIdentity, int] = {}

    # ------------------------------------------------------------------
    # Baseline context management
    # ------------------------------------------------------------------
    def store_baseline(
        self,
        package: ContextPackage,
        transition: PassTransition,
        chunk_details: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a new baseline package and associated transition metadata."""

        logger.debug(
            "Storing new baseline context: %s chunks, remaining budget=%s",
            len(package.baseline_chunks),
            transition.remaining_budget,
        )

        package.additional_chunks.clear()
        package.gap_analysis.clear()
        package.divergence_detected = False
        package.divergence_confidence = 0.0

        self._context = package
        self._transition = transition
        self._chunk_cache = {}
        self._additional_chunk_token_costs = {}

        if chunk_details:
            self.register_chunks(chunk_details)

    def register_chunks(self, chunks: Iterable[Dict[str, Any]]) -> None:
        """Register chunk payloads for quick lookup and deduplication."""

        for chunk in chunks:
            identity = memory_identity(chunk)
            if identity is None:
                continue
            if self._context:
                if (
                    identity in self._context.baseline_chunks
                    or identity in self._context.additional_chunks
                ):
                    self._chunk_cache[identity] = chunk
            else:
                self._chunk_cache[identity] = chunk

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def context(self) -> Optional[ContextPackage]:
        return self._context

    @property
    def transition(self) -> Optional[PassTransition]:
        return self._transition

    def get_current_context(self) -> Optional[ContextPackage]:
        """Convenience accessor used by status reporting."""
        return self._context

    def get_structured_passages(self) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        return list(self._context.structured_passages)

    # ------------------------------------------------------------------
    # Chunk helpers
    # ------------------------------------------------------------------
    def is_chunk_known(self, chunk_id: MemoryIdentity) -> bool:
        if not self._context:
            return False
        return (
            chunk_id in self._context.baseline_chunks
            or chunk_id in self._context.additional_chunks
        )

    def register_additional_chunks(
        self,
        chunks: Iterable[Dict[str, Any]],
        *,
        token_costs: Optional[Mapping[MemoryIdentity, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Register new chunks and optionally charge their exact Pass-2 costs."""

        if not self._context:
            logger.debug(
                "No baseline context loaded; skipping additional chunk registration"
            )
            return []

        new_chunks: List[Dict[str, Any]] = []
        new_identities: Set[MemoryIdentity] = set()
        for chunk in chunks:
            identity = memory_identity(chunk)
            if (
                identity is None
                or identity in new_identities
                or self.is_chunk_known(identity)
            ):
                continue
            new_chunks.append(chunk)
            new_identities.add(identity)

        tracked_costs: Dict[MemoryIdentity, int] = {}
        if token_costs is not None:
            for identity in new_identities:
                if identity not in token_costs:
                    raise RuntimeError(
                        "Pass-2 token accounting is missing a cost for newly "
                        f"registered memory {identity!r}"
                    )
                cost = token_costs[identity]
                if isinstance(cost, bool) or not isinstance(cost, int):
                    raise TypeError(
                        f"Pass-2 token cost for memory {identity!r} must be an int"
                    )
                if cost < 0:
                    raise ValueError(
                        f"Pass-2 token cost for memory {identity!r} cannot be negative"
                    )
                tracked_costs[identity] = cost

            total_cost = sum(tracked_costs.values())
            if total_cost > self.get_remaining_budget():
                raise RuntimeError(
                    "Pass-2 chunk registration exceeds the remaining budget: "
                    f"cost={total_cost}, remaining={self.get_remaining_budget()}"
                )

        for chunk in new_chunks:
            identity = memory_identity(chunk)
            assert identity is not None
            self._context.additional_chunks.add(identity)
            self._chunk_cache[identity] = chunk

        if tracked_costs:
            consumed = self.consume_budget(sum(tracked_costs.values()))
            if consumed != sum(tracked_costs.values()):
                raise RuntimeError(
                    "Pass-2 chunk registration failed to consume its full token cost"
                )
            self._additional_chunk_token_costs.update(tracked_costs)
        return new_chunks

    def unregister_chunks(
        self, chunks: Iterable[Dict[str, Any]]
    ) -> tuple[Set[MemoryIdentity], int]:
        """Forget dropped payload chunks and refund tracked Pass-2 token costs."""

        if not self._context:
            return set(), 0

        identities = {
            identity
            for chunk in chunks
            for identity in [memory_identity(chunk)]
            if identity is not None
        }
        removed: Set[MemoryIdentity] = set()
        refunded_tokens = 0
        for identity in identities:
            was_known = (
                identity in self._context.baseline_chunks
                or identity in self._context.additional_chunks
            )
            if not was_known:
                continue
            self._context.baseline_chunks.discard(identity)
            self._context.additional_chunks.discard(identity)
            self._chunk_cache.pop(identity, None)
            refunded_tokens += self._additional_chunk_token_costs.pop(identity, 0)
            removed.add(identity)

        if refunded_tokens:
            if not self._transition:
                raise RuntimeError(
                    "Cannot refund dropped Pass-2 chunks without transition state"
                )
            self._transition.remaining_budget += refunded_tokens
            logger.debug(
                "Refunded %s tokens from dropped Pass-2 chunks (now %s)",
                refunded_tokens,
                self._transition.remaining_budget,
            )

        return removed, refunded_tokens

    def get_all_chunks(self) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        # Return chunks in a deterministic order: baseline first, then additional
        ordered_ids = list(self._context.baseline_chunks) + list(
            self._context.additional_chunks
        )
        seen: Set[MemoryIdentity] = set()
        result: List[Dict[str, Any]] = []
        for chunk_id in ordered_ids:
            if chunk_id in seen:
                continue
            chunk = self._chunk_cache.get(chunk_id)
            if chunk:
                result.append(chunk)
                seen.add(chunk_id)
        return result

    def get_additional_chunk_details(self) -> List[Dict[str, Any]]:
        if not self._context:
            return []
        details: List[Dict[str, Any]] = []
        for chunk_id in self._context.additional_chunks:
            chunk = self._chunk_cache.get(chunk_id)
            if chunk:
                details.append(chunk)
        return details

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------
    def get_remaining_budget(self) -> int:
        if not self._transition:
            return 0
        return max(0, int(self._transition.remaining_budget))

    def consume_budget(self, amount: int) -> int:
        if not self._transition or amount <= 0:
            return 0
        available = self.get_remaining_budget()
        to_consume = min(available, amount)
        self._transition.remaining_budget = max(0, available - to_consume)
        logger.debug(
            "Consumed %s tokens from remaining budget (now %s)",
            to_consume,
            self._transition.remaining_budget,
        )
        return to_consume

    def adjust_budget(self, remaining_budget: int) -> None:
        if not self._transition:
            return
        self._transition.remaining_budget = max(0, remaining_budget)

    # ------------------------------------------------------------------
    # Divergence tracking
    # ------------------------------------------------------------------
    def update_divergence(
        self, detected: bool, confidence: float, gaps: Dict[str, str]
    ) -> None:
        if not self._context:
            return
        self._context.divergence_detected = detected
        self._context.divergence_confidence = confidence
        self._context.gap_analysis = gaps

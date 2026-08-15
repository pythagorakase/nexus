"""High level manager orchestrating LORE's custom memory flows."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

from sqlalchemy import text

from nexus.agents.orrery.player_identity import canonical_player_character_id

from .context_state import (
    ContextPackage,
    ContextStateManager,
    MemoryIdentity,
    PASS2_BASELINE_PRODUCER,
    RETROGRADE_SUMMARY_ID_PREFIX,
    Pass2BaselineV1,
    PassTransition,
    is_retrograde_summary,
    memory_identity,
)
from .correspondence import correspondence_settings, load_accepted_correspondence
from .divergence import DivergenceDetector, DivergenceResult
from .entity_detector import EntityMatch, HighSpecificityEntityDetector
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory
from .retrieval_coverage import audit_retrieval_coverage, coerce_chunk_id

load_aliases_from_db: Optional[Callable[[Any], Dict[str, List[str]]]]
try:  # pragma: no cover - optional dependency during unit tests
    from nexus.agents.memnon.utils.alias_search import (
        load_aliases_from_db as _load_aliases_from_db,
    )

    load_aliases_from_db = _load_aliases_from_db
except ImportError:  # pragma: no cover - fallback if module unavailable
    load_aliases_from_db = None

logger = logging.getLogger(__name__)

_STORYTELLER_WIRE_CLASSES = frozenset({"openai", "anthropic", "local"})


class MissingPass2BaselineError(RuntimeError):
    """An accepted parent chunk has no durable Pass-2 baseline."""


def pass2_baseline_config_fingerprint(settings: Mapping[str, Any]) -> str:
    """Fingerprint configuration that determines two-pass memory behavior."""

    legacy_agent_settings = settings.get("Agent Settings")
    legacy_lore_settings = (
        legacy_agent_settings.get("LORE")
        if isinstance(legacy_agent_settings, Mapping)
        else None
    )
    lore_settings = (
        legacy_lore_settings
        if isinstance(legacy_lore_settings, Mapping)
        else settings.get("lore", {})
    )
    payload = {
        "memory": settings.get("memory", {}),
        "lore_token_budget": (
            lore_settings.get("token_budget", {})
            if isinstance(lore_settings, Mapping)
            else {}
        ),
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def empty_pass2_baseline(settings: Mapping[str, Any]) -> Pass2BaselineV1:
    """Build the explicit empty baseline staged by bootstrap/admin boundary tools."""

    return Pass2BaselineV1(
        producer=PASS2_BASELINE_PRODUCER,
        config_fingerprint=pass2_baseline_config_fingerprint(settings),
        memory_identities=[],
        prior_token_accounting={},
        remaining_budget=0,
    )


def _storyteller_token_budget(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the validated LORE token-budget mapping."""
    legacy_agent_settings = settings.get("Agent Settings")
    legacy_lore_settings = (
        legacy_agent_settings.get("LORE")
        if isinstance(legacy_agent_settings, Mapping)
        else None
    )
    lore_settings = (
        legacy_lore_settings
        if isinstance(legacy_lore_settings, Mapping)
        else settings.get("lore")
    )
    if not isinstance(lore_settings, Mapping):
        raise ValueError("LORE settings are required to resolve the context budget")

    token_budget = lore_settings.get("token_budget")
    if not isinstance(token_budget, Mapping):
        raise ValueError(
            "token_budget must be configured under the LORE settings section"
        )
    if "apex_context_window" not in token_budget:
        raise ValueError(
            "apex_context_window must be configured under LORE token_budget"
        )
    return token_budget


def resolve_base_storyteller_context_window(settings: Mapping[str, Any]) -> int:
    """Resolve the base context ceiling used when LOGON is explicitly disabled."""
    token_budget = _storyteller_token_budget(settings)

    apex_context_window = token_budget["apex_context_window"]
    if not isinstance(apex_context_window, int):
        raise TypeError("apex_context_window must be an integer")
    return apex_context_window


def resolve_storyteller_prompt_overhead_tokens(
    settings: Mapping[str, Any],
) -> int:
    """Resolve the post-assembly reserve for LOGON prompt formatting."""
    token_budget = _storyteller_token_budget(settings)
    if "prompt_overhead_tokens" not in token_budget:
        raise ValueError(
            "prompt_overhead_tokens must be configured under LORE token_budget"
        )
    prompt_overhead_tokens = token_budget["prompt_overhead_tokens"]
    if isinstance(prompt_overhead_tokens, bool) or not isinstance(
        prompt_overhead_tokens, int
    ):
        raise TypeError("prompt_overhead_tokens must be an integer")
    if prompt_overhead_tokens < 0:
        raise ValueError("prompt_overhead_tokens cannot be negative")
    return prompt_overhead_tokens


def resolve_storyteller_context_window(
    settings: Mapping[str, Any],
    provider_wire_type: Optional[str],
    provider_name: Optional[str],
) -> int:
    """Resolve the assembled-context ceiling for one storyteller provider.

    The wire class proves an active route was resolved; the override lookup
    keys on the registry provider NAME, because resource profiles belong to
    the serving provider, not the wire dialect (an OpenAI-compatible remote
    provider such as openrouter shares the "local" wire class but must not
    inherit the compute-bound local payload squeeze).
    """
    if provider_wire_type not in _STORYTELLER_WIRE_CLASSES:
        raise RuntimeError(
            "Cannot resolve the storyteller context budget without a valid active "
            "provider wire class; expected one of "
            f"{sorted(_STORYTELLER_WIRE_CLASSES)}, got {provider_wire_type!r}"
        )
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise RuntimeError(
            "Cannot resolve the storyteller context budget without the active "
            f"registry provider name; got {provider_name!r}"
        )

    token_budget = _storyteller_token_budget(settings)
    apex_context_window = resolve_base_storyteller_context_window(settings)

    provider_overrides = token_budget.get("provider_overrides", {})
    if not isinstance(provider_overrides, Mapping):
        raise TypeError("token_budget provider_overrides must be a mapping")

    override = provider_overrides.get(provider_name)
    if override is None:
        return apex_context_window
    if not isinstance(override, int):
        raise TypeError(
            f"token budget provider override for {provider_name!r} must be "
            "an integer"
        )

    logger.debug(
        "Storyteller payload budget override: provider=%s class=%s effective=%s "
        "tokens",
        provider_name,
        provider_wire_type,
        override,
    )
    return override


_COMMON_STOPWORDS: Set[str] = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "almost",
    "already",
    "along",
    "among",
    "around",
    "because",
    "before",
    "being",
    "below",
    "beside",
    "besides",
    "between",
    "beyond",
    "could",
    "doing",
    "during",
    "either",
    "every",
    "having",
    "however",
    "inside",
    "maybe",
    "nearly",
    "other",
    "others",
    "rather",
    "since",
    "still",
    "storyteller",
    "their",
    "there",
    "these",
    "those",
    "through",
    "toward",
    "towards",
    "under",
    "until",
    "where",
    "which",
    "while",
    "whose",
    "would",
    "could",
    "should",
    "might",
    "afterward",
    "beforehand",
    "within",
    "without",
    "though",
    "therefore",
    "whatever",
    "whenever",
    "something",
    "nothing",
    "anything",
    "everything",
}


@dataclass
class Pass2Update:
    """Information returned after handling user input (Pass 2)."""

    divergence: DivergenceResult
    retrieved_chunks: List[Dict[str, Any]]
    tokens_used: int
    baseline_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        retrieved_memory_ids = [
            identity
            for chunk in self.retrieved_chunks
            for identity in [memory_identity(chunk)]
            if identity is not None
        ]
        narrative_chunk_ids = [
            chunk_id
            for chunk in self.retrieved_chunks
            for chunk_id in [coerce_chunk_id(chunk)]
            if chunk_id is not None
        ]
        return {
            "divergence": self.divergence.to_dict(),
            "retrieved_memory_ids": retrieved_memory_ids,
            "retrieved_chunk_ids": narrative_chunk_ids,
            "tokens_used": self.tokens_used,
            "baseline_available": self.baseline_available,
        }


class ContextMemoryManager:
    """Coordinate Pass 1 baseline storage and Pass 2 incremental retrieval."""

    def __init__(
        self,
        settings: Dict[str, Any],
        memnon: Optional[object] = None,
        token_manager: Optional[object] = None,
        provider_wire_type: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.memnon = memnon  # Store reference for entity detector
        memory_settings = settings.get("memory", {})

        # Phase 2 configuration
        self.phase2_fraction = float(
            memory_settings.get("phase2_fraction", 0.1)
        )  # 10% of apex window
        self.raw_search_k = int(
            memory_settings.get("raw_search_k", 30)
        )  # Overretrieve before budget trimming
        self.skip_simple_choices = bool(
            memory_settings.get("skip_simple_choices", True)
        )

        # The active storyteller class is resolved per turn because slots can
        # change models while a LORE instance remains alive.
        self.provider_wire_type: Optional[str] = None
        self.provider_name: Optional[str] = None
        self.phase2_budget: Optional[int] = None
        self._storyteller_budget_configured = False
        if (provider_wire_type is None) != (provider_name is None):
            raise ValueError(
                "provider_wire_type and provider_name must be supplied together"
            )
        if provider_wire_type is not None and provider_name is not None:
            self.configure_storyteller_budget(provider_wire_type, provider_name)

        # Legacy settings (kept for compatibility but may be deprecated)
        self.pass2_reserve = float(memory_settings.get("pass2_budget_reserve", 0.25))
        self.divergence_threshold = float(
            memory_settings.get("divergence_threshold", 0.7)
        )
        self.warm_slice_default = bool(memory_settings.get("warm_slice_default", True))
        self.max_sql_iterations = int(memory_settings.get("max_sql_iterations", 5))

        self.context_state = ContextStateManager()
        self.query_memory = QueryMemory(max_iterations=self.max_sql_iterations)

        db_connection = None
        if self.memnon and hasattr(self.memnon, "db"):
            db_connection = self.memnon.db
        if db_connection is None:
            db_connection = getattr(
                getattr(self.memnon, "db_manager", None), "engine", None
            )

        self.entity_detector = HighSpecificityEntityDetector(db_connection)
        self.divergence_detector = DivergenceDetector(
            threshold=self.divergence_threshold
        )
        logger.info(
            "Using entity-based divergence detector (threshold=%.2f)",
            self.divergence_threshold,
        )

        self.incremental = IncrementalRetriever(
            memnon=memnon,
            context_state=self.context_state,
            query_memory=self.query_memory,
            warm_slice_default=self.warm_slice_default,
        )

        self.token_manager = token_manager

        self.alias_lookup: Dict[str, List[str]] = {}
        self.canonical_name_map: Dict[str, str] = {}
        self.alias_inverse: Dict[str, str] = {}
        self.place_lookup: Dict[str, str] = {}
        self.user_character_name: Optional[str] = None
        self.idf_dictionary = getattr(memnon, "idf_dictionary", None)

        self._initialize_entity_maps(memnon)

    def configure_storyteller_budget(
        self, provider_wire_type: str, provider_name: str
    ) -> int:
        """Apply the active provider's resource profile to payload budgets."""
        apex_context_window = resolve_storyteller_context_window(
            self.settings, provider_wire_type, provider_name
        )
        self.provider_wire_type = provider_wire_type
        self.provider_name = provider_name
        self._storyteller_budget_configured = True
        self._configure_phase2_budget(apex_context_window)
        return apex_context_window

    def configure_base_storyteller_budget(self) -> int:
        """Use the base window for a turn where LOGON is explicitly disabled."""
        apex_context_window = resolve_base_storyteller_context_window(self.settings)
        self.provider_wire_type = None
        self.provider_name = None
        self._storyteller_budget_configured = True
        self._configure_phase2_budget(apex_context_window)
        return apex_context_window

    def _configure_phase2_budget(self, apex_context_window: int) -> None:
        """Apply one resolved context window to the Phase 2 reserve."""
        self.phase2_budget = int(apex_context_window * self.phase2_fraction)
        logger.info(
            "Phase 2 budget: %s tokens (%.0f%% of %s)",
            self.phase2_budget,
            self.phase2_fraction * 100,
            apex_context_window,
        )

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of the current memory state for status reporting."""
        current_package = self.context_state.get_current_context()
        query_snapshot = self.query_memory.snapshot()
        pass1_usage = {}
        pass2_usage = {}

        if current_package:
            pass1_usage = {
                "baseline_tokens": current_package.token_usage.get(
                    "baseline_tokens", 0
                ),
                "reserved_for_pass2": current_package.token_usage.get(
                    "reserved_for_pass2", 0
                ),
            }
            pass2_usage = {
                "reserve_shortfall": current_package.token_usage.get(
                    "reserve_shortfall", 0
                ),
                "remaining_budget": self.context_state.get_remaining_budget(),
            }
        return {
            "pass1": {
                "baseline_chunks": (
                    len(current_package.baseline_chunks) if current_package else 0
                ),
                "baseline_themes": (
                    current_package.baseline_themes if current_package else []
                ),
                "structured_passages": (
                    current_package.structured_passages if current_package else []
                ),
                "token_usage": pass1_usage,
            },
            "pass2": {
                "divergence_detected": (
                    current_package.divergence_detected if current_package else False
                ),
                "divergence_confidence": (
                    current_package.divergence_confidence if current_package else 0.0
                ),
                "additional_chunks": (
                    len(current_package.additional_chunks) if current_package else 0
                ),
                "token_reserve_percent": int(self.pass2_reserve * 100),
                "usage": pass2_usage,
            },
            "query_memory": {
                "history": query_snapshot,
                "max_iterations": self.query_memory.max_iterations,
            },
            "settings": {
                "divergence_threshold": self.divergence_threshold,
                "warm_slice_default": self.warm_slice_default,
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def assemble_correspondence_context(self, dbname: str) -> str:
        """Render private context from accepted DB state only."""

        config = correspondence_settings(self.settings)
        max_tokens = int(config["max_rendered_tokens"])
        return load_accepted_correspondence(
            dbname,
            max_tokens=max_tokens,
        )

    def export_pass2_baseline(self) -> Pass2BaselineV1:
        """Export the current post-trimming Pass-1 state for incubator staging."""

        package = self.context_state.context
        transition = self.context_state.transition
        if package is None or transition is None:
            raise RuntimeError(
                "Cannot export a Pass-2 baseline before Pass 1 completes"
            )

        normalized_identities: Set[MemoryIdentity] = set()
        for identity in package.baseline_chunks:
            if isinstance(identity, str) and not identity.startswith(
                RETROGRADE_SUMMARY_ID_PREFIX
            ):
                try:
                    identity = int(identity)
                except ValueError as exc:
                    raise ValueError(
                        f"Unsupported Pass-2 baseline memory identity {identity!r}"
                    ) from exc
            normalized_identities.add(identity)

        identities = sorted(
            normalized_identities,
            key=lambda identity: (
                0 if isinstance(identity, int) else 1,
                identity if isinstance(identity, int) else str(identity),
            ),
        )
        prior_token_accounting: Dict[str, int] = {}
        for name, value in package.token_usage.items():
            if name == "using_reasoning_model" and isinstance(value, bool):
                continue
            if not isinstance(value, int) or value < 0:
                raise ValueError(
                    "Pass-2 baseline token accounting values must be "
                    f"nonnegative integers: {name}={value!r}"
                )
            prior_token_accounting[name] = value
        return Pass2BaselineV1(
            producer=PASS2_BASELINE_PRODUCER,
            config_fingerprint=pass2_baseline_config_fingerprint(self.settings),
            memory_identities=identities,
            prior_token_accounting=prior_token_accounting,
            remaining_budget=transition.remaining_budget,
        )

    def restore_pass2_baseline(self, parent_chunk_id: int) -> Pass2BaselineV1:
        """Hydrate Pass-2 state from one accepted parent chunk or fail loudly."""

        if (
            isinstance(parent_chunk_id, bool)
            or not isinstance(parent_chunk_id, int)
            or parent_chunk_id <= 0
        ):
            raise ValueError("Pass-2 baseline parent_chunk_id must be positive")
        engine = getattr(getattr(self.memnon, "db_manager", None), "engine", None)
        if engine is None:
            raise RuntimeError(
                "Pass-2 baseline restoration requires MEMNON database access"
            )

        with engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        """
                    SELECT b.schema_version, b.payload, n.storyteller_text
                    FROM lore_pass_baselines AS b
                    JOIN narrative_chunks AS n ON n.id = b.chunk_id
                    WHERE b.chunk_id = :chunk_id
                    """
                    ),
                    {"chunk_id": parent_chunk_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                parent_exists = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM narrative_chunks WHERE id = :id)"
                    ),
                    {"id": parent_chunk_id},
                ).scalar_one()
                if not parent_exists:
                    raise ValueError(
                        f"Cannot restore Pass-2 baseline: parent chunk "
                        f"{parent_chunk_id} does not exist"
                    )
                raise MissingPass2BaselineError(
                    "Accepted parent chunk "
                    f"{parent_chunk_id} has no lore_pass_baselines row. Stamp the "
                    "slot's current migration boundary with "
                    "scripts/stamp_lore_pass_baseline.py --slot <1-5>, then retry."
                )

        baseline = Pass2BaselineV1.model_validate(row["payload"])
        if row["schema_version"] != baseline.schema_version:
            raise RuntimeError(
                "Pass-2 baseline schema columns disagree for parent chunk "
                f"{parent_chunk_id}: column={row['schema_version']}, "
                f"payload={baseline.schema_version}"
            )
        if baseline.parent_chunk_id != parent_chunk_id:
            raise RuntimeError(
                "Pass-2 baseline parent identity mismatch: requested "
                f"{parent_chunk_id}, payload={baseline.parent_chunk_id}"
            )
        expected_fingerprint = pass2_baseline_config_fingerprint(self.settings)
        if baseline.config_fingerprint != expected_fingerprint:
            raise RuntimeError(
                "Pass-2 baseline config fingerprint is incompatible for parent "
                f"chunk {parent_chunk_id}: stored={baseline.config_fingerprint}, "
                f"current={expected_fingerprint}"
            )

        storyteller_output = row["storyteller_text"]
        if not isinstance(storyteller_output, str) or not storyteller_output:
            raise RuntimeError(
                f"Accepted parent chunk {parent_chunk_id} has no storyteller output"
            )
        analysis = self._analyze_storyteller_output(storyteller_output)
        package = ContextPackage(
            baseline_chunks=set(baseline.memory_identities),
            baseline_entities={
                "characters": analysis.get("characters", []),
                "locations": analysis.get("locations", []),
                "keywords": analysis.get("keywords", []),
            },
            baseline_themes=analysis.get("themes", []),
            token_usage=dict(baseline.prior_token_accounting),
        )
        transition = PassTransition(
            storyteller_output=storyteller_output,
            expected_user_themes=analysis.get("expected", []),
            remaining_budget=baseline.remaining_budget,
        )
        self.context_state.store_baseline(package, transition)
        self.query_memory.reset_pass("pass2")
        return baseline

    def handle_storyteller_response(
        self,
        narrative: str,
        warm_slice: Optional[Iterable[Dict[str, Any]]] = None,
        retrieved_passages: Optional[Iterable[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        assembled_context: Optional[Dict[str, Any]] = None,
    ) -> ContextPackage:
        """Run Pass 1 analysis and store baseline context for the next turn."""

        analysis = self._analyze_storyteller_output(narrative)
        baseline_entities = {
            "characters": analysis.get("characters", []),
            "locations": analysis.get("locations", []),
            "keywords": analysis.get("keywords", []),
        }
        baseline_themes = analysis.get("themes", [])
        expected_user_themes = analysis.get("expected", [])

        baseline_chunks: Set[MemoryIdentity] = set()
        chunk_details: List[Dict[str, Any]] = []
        structured_passages: List[Dict[str, Any]] = []

        for collection in warm_slice or []:
            normalized = dict(collection)
            identity = memory_identity(normalized)
            if identity is None:
                structured_passages.append(normalized)
                continue
            if not is_retrograde_summary(normalized):
                normalized.setdefault("chunk_id", identity)
            baseline_chunks.add(identity)
            chunk_details.append(normalized)

        chunk_retrievals: List[Dict[str, Any]] = []
        for passage in retrieved_passages or []:
            normalized = dict(passage)
            identity = memory_identity(normalized)
            if identity is None:
                structured_passages.append(normalized)
                continue
            if not is_retrograde_summary(normalized):
                normalized.setdefault("chunk_id", identity)
            chunk_retrievals.append(normalized)

        if assembled_context is not None:
            structured_section = assembled_context.setdefault("structured_passages", [])
            structured_section.extend(dict(result) for result in structured_passages)

        for passage in chunk_retrievals:
            identity = memory_identity(passage)
            if identity is None:
                continue
            baseline_chunks.add(identity)
            chunk_details.append(passage)

        token_usage = token_usage or {}
        baseline_tokens = sum(
            token_usage.get(key, 0)
            for key in ("warm_slice", "structured", "augmentation")
        )
        total_available = token_usage.get("total_available", 0)
        reserved_for_pass2 = max(0, int(total_available * self.pass2_reserve))
        remaining_budget = max(0, total_available - baseline_tokens)
        reserve_shortfall = max(0, reserved_for_pass2 - remaining_budget)

        package = ContextPackage(
            baseline_chunks=baseline_chunks,
            baseline_entities=baseline_entities,
            baseline_themes=baseline_themes,
            structured_passages=structured_passages,
            token_usage={
                **token_usage,
                "baseline_tokens": baseline_tokens,
                "reserved_for_pass2": reserved_for_pass2,
                "reserve_shortfall": reserve_shortfall,
            },
        )

        transition = PassTransition(
            storyteller_output=narrative,
            expected_user_themes=expected_user_themes,
            assembled_context=assembled_context or {},
            remaining_budget=remaining_budget,
            structured_passages=structured_passages,
        )

        self.context_state.store_baseline(package, transition, chunk_details)
        # Pass 2 queries are always reset when a new baseline is stored
        self.query_memory.reset_pass("pass2")
        logger.debug(
            "Pass 1 baseline stored: %s baseline chunks, %s expected themes, "
            "remaining budget=%s",
            len(baseline_chunks),
            len(expected_user_themes),
            remaining_budget,
        )
        return package

    # ------------------------------------------------------------------
    # Pass 2: User Input Handling
    # ------------------------------------------------------------------
    def _is_simple_choice(self, user_input: str) -> bool:
        """Check if user input is just a simple choice selection.

        Examples that return True:
        - "1", "2", "3" etc.
        - "A", "B", "C" etc.
        - "1.", "A." (with period)
        - "a", "b", "c" (lowercase)
        - " 2 " (with spaces)
        - "1!" or "B?" (with trailing punctuation)

        Returns False for any elaboration like:
        - "2, but carefully"
        - "1 because..."
        - "Option A"
        """
        if not user_input:
            return False

        # Remove leading/trailing whitespace and punctuation
        cleaned = user_input.strip().strip(".,!?;:")

        # Pattern: single digit, or single letter (upper/lower)
        # After stripping, should just be the choice character
        pattern = r"^[1-9]$|^[A-Za-z]$"

        is_simple = bool(re.match(pattern, cleaned))
        if is_simple:
            logger.info(
                "Simple choice detected: '%s' -> '%s' - skipping Phase 2 retrieval",
                user_input,
                cleaned,
            )

        return is_simple

    def _detect_divergence(
        self,
        user_input: str,
        entity_match: Optional["EntityMatch"] = None,
    ) -> DivergenceResult:
        """Detect divergence using high-specificity entity matching."""

        if entity_match is None:
            entity_match = self.entity_detector.detect_entities(user_input)
        summary = self.entity_detector.to_divergence_format(entity_match)
        return DivergenceResult(
            bool(summary.get("detected")),
            float(summary.get("confidence", 0.0)),
            summary.get("gaps", {}),
            set(summary.get("unmatched_entities", set())),
            set(summary.get("references_seen", set())),
        )

    def _compute_available_phase2_budget(
        self, token_counts: Optional[Dict[str, int]]
    ) -> int:
        """Determine the usable Phase 2 budget for this turn."""

        phase2_budget = self.phase2_budget
        if phase2_budget is None or not self._storyteller_budget_configured:
            raise RuntimeError(
                "Storyteller context budget must be configured before resolving "
                "the Phase 2 payload budget"
            )

        remaining_budget = self.context_state.get_remaining_budget()

        if token_counts:
            total_available = token_counts.get("total_available")
            if total_available is not None:
                baseline_tokens = sum(
                    token_counts.get(key, 0)
                    for key in ("warm_slice", "structured", "augmentation")
                )
                actual_remaining = max(0, int(total_available) - int(baseline_tokens))
                if actual_remaining != remaining_budget:
                    logger.debug(
                        "Adjusting remaining budget from %s to %s based on "
                        "token counts",
                        remaining_budget,
                        actual_remaining,
                    )
                    self.context_state.adjust_budget(actual_remaining)
                    remaining_budget = actual_remaining

        return max(0, min(phase2_budget, remaining_budget))

    def handle_user_input(
        self,
        user_input: str,
        token_counts: Optional[Dict[str, int]] = None,
        turn_id: Optional[str] = None,
    ) -> Pass2Update:
        """Run deterministic Phase 2 retrieval from raw user input.

        1. Check if simple choice -> skip if yes
        2. Run raw vector search
        3. Keep chunks that fit the remaining Phase 2 budget
        """

        context = self.context_state.context
        transition = self.context_state.transition

        entity_match = self.entity_detector.detect_entities(user_input)
        divergence = self._detect_divergence(user_input, entity_match=entity_match)
        logger.debug(
            "Divergence detection: %s (confidence=%.2f)",
            divergence.detected,
            divergence.confidence,
        )
        self.context_state.update_divergence(
            divergence.detected,
            divergence.confidence,
            divergence.gaps,
        )

        if not context or not transition:
            logger.debug("No baseline context available; skipping Phase 2")
            audit_retrieval_coverage(
                incremental_retriever=self.incremental,
                entity_match=entity_match,
                turn_id=turn_id,
                user_input=user_input,
                raw_result_count=0,
                kept_chunks=[],
                kept_tokens=0,
                available_budget=0,
            )
            return Pass2Update(
                divergence,
                [],
                0,
                baseline_available=False,
            )

        available_budget = self._compute_available_phase2_budget(token_counts)

        # STEP 1: Check if simple choice -> skip Phase 2 if yes
        if self.skip_simple_choices and self._is_simple_choice(user_input):
            logger.info("📌 Phase 2 skipped: Simple choice detected")
            audit_retrieval_coverage(
                incremental_retriever=self.incremental,
                entity_match=entity_match,
                turn_id=turn_id,
                user_input=user_input,
                raw_result_count=0,
                kept_chunks=[],
                kept_tokens=0,
                available_budget=available_budget,
            )
            return Pass2Update(
                divergence,
                [],
                0,
                baseline_available=True,
            )

        if available_budget <= 0:
            logger.info("📉 Phase 2 skipped: No remaining token budget available")
            audit_retrieval_coverage(
                incremental_retriever=self.incremental,
                entity_match=entity_match,
                turn_id=turn_id,
                user_input=user_input,
                raw_result_count=0,
                kept_chunks=[],
                kept_tokens=0,
                available_budget=available_budget,
            )
            return Pass2Update(
                divergence,
                [],
                0,
                baseline_available=True,
            )

        # STEP 2: Always run raw vector search (unless simple choice)
        logger.info("🔍 Phase 2 Step 1: Raw user input vector search")
        raw_search_results, raw_tokens = self.incremental.retrieve_from_raw_input(
            user_input,
            budget=available_budget,
            k=self.raw_search_k,  # Overretrieve (default 30)
        )

        if not raw_search_results:
            logger.info("No results from raw vector search - Phase 2 complete")
            audit_retrieval_coverage(
                incremental_retriever=self.incremental,
                entity_match=entity_match,
                turn_id=turn_id,
                user_input=user_input,
                raw_result_count=0,
                kept_chunks=[],
                kept_tokens=0,
                available_budget=available_budget,
            )
            return Pass2Update(
                divergence,
                [],
                0,
                baseline_available=True,
            )

        logger.info(
            "Raw search retrieved %s chunks (~%s tokens)",
            len(raw_search_results),
            raw_tokens,
        )

        # STEP 3: Keep chunks that fit in the remaining Phase 2 budget.
        kept_chunks = []
        kept_token_costs: Dict[MemoryIdentity, int] = {}
        total_tokens = 0
        for chunk in raw_search_results:
            chunk_text = chunk.get("text", "")
            if not isinstance(chunk_text, str):
                raise TypeError("Retrieved chunk text must be a string")
            chunk_tokens = self._estimate_tokens(chunk_text)
            if total_tokens + chunk_tokens > available_budget:
                break
            identity = self._memory_identity(chunk)
            if identity is None:
                raise RuntimeError(
                    "Incremental retrieval returned a chunk without a memory identity"
                )
            kept_chunks.append(chunk)
            kept_token_costs[identity] = chunk_tokens
            total_tokens += chunk_tokens

        if kept_chunks:
            new_chunks = self.context_state.register_additional_chunks(
                kept_chunks,
                token_costs=kept_token_costs,
            )
            total_tokens = sum(
                kept_token_costs[identity]
                for chunk in new_chunks
                for identity in [self._memory_identity(chunk)]
                if identity is not None
            )
            budget_percentage = (
                total_tokens / available_budget * 100 if available_budget else 0
            )
            logger.info(
                f"✅ Phase 2 complete: {len(new_chunks)} new chunks, "
                f"{total_tokens} tokens ({budget_percentage:.1f}% of budget)"
            )
        else:
            logger.info("Phase 2 complete: No chunks fit in remaining budget")

        audit_retrieval_coverage(
            incremental_retriever=self.incremental,
            entity_match=entity_match,
            turn_id=turn_id,
            user_input=user_input,
            raw_result_count=len(raw_search_results),
            kept_chunks=kept_chunks,
            kept_tokens=total_tokens,
            available_budget=available_budget,
        )

        return Pass2Update(
            divergence,
            new_chunks if kept_chunks else [],
            total_tokens,
            baseline_available=True,
        )

    def unregister_payload_chunks(
        self, chunks: Iterable[Dict[str, Any]]
    ) -> tuple[Set[MemoryIdentity], int]:
        """Remove Phase-5 drops from memory state and refund tracked retrievals."""

        return self.context_state.unregister_chunks(chunks)

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Simple heuristic: words * 1.25 ≈ tokens
        words = len(text.split())
        return int(words * 1.25)

    def _coerce_chunk_id(self, chunk: Dict[str, Any]) -> Optional[int]:
        """Attempt to coerce a chunk identifier without logging noise."""

        return coerce_chunk_id(chunk)

    def _memory_identity(self, memory: Dict[str, Any]) -> Optional[MemoryIdentity]:
        """Return a typed identity shared by both retrieval corpora."""

        return memory_identity(memory)

    def augment_warm_slice(
        self, warm_slice: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge existing warm slice chunks with any incremental additions."""

        if not warm_slice:
            warm_slice = []

        # Register baseline warm slice for deduplication in future passes
        self.context_state.register_chunks(warm_slice)

        additions = self.context_state.get_additional_chunk_details()
        if not additions:
            return warm_slice

        known_ids = {
            identity
            for chunk in warm_slice
            for identity in [self._memory_identity(chunk)]
            if identity is not None
        }
        for chunk in additions:
            identity = self._memory_identity(chunk)
            if identity is None or identity in known_ids:
                continue
            warm_slice.append(chunk)
            known_ids.add(identity)

        return warm_slice

    def record_pass1_query(self, query: str) -> None:
        """Record a query executed during Pass 1 for future deduplication."""
        self.query_memory.record("pass1", query)

    def reset_pass1_queries(self) -> None:
        self.query_memory.reset_pass("pass1")

    def get_state(self) -> Dict[str, Any]:
        """Return a snapshot of the current memory state (for logging/debug)."""
        package = self.context_state.context
        transition = self.context_state.transition
        return {
            "context": package,
            "transition": transition,
            "queries": self.query_memory.snapshot(),
        }

    # ------------------------------------------------------------------
    # Entity normalization helpers
    # ------------------------------------------------------------------
    def _initialize_entity_maps(self, memnon: Optional[object]) -> None:
        """Load alias and location metadata for canonical entity detection."""

        if not memnon or load_aliases_from_db is None:  # pragma: no cover - defensive
            return

        engine = getattr(getattr(memnon, "db_manager", None), "engine", None)
        if engine is None:
            return

        try:
            with engine.connect() as conn:
                player_character_id = canonical_player_character_id(conn)
                alias_lookup = load_aliases_from_db(conn)

                for canonical_lc, aliases in alias_lookup.items():
                    self.alias_lookup[canonical_lc] = list(aliases)
                    primary = next(
                        (alias for alias in aliases if alias.lower() == canonical_lc),
                        aliases[0] if aliases else canonical_lc.title(),
                    )
                    self.canonical_name_map[canonical_lc] = primary
                    for alias in aliases:
                        self.alias_inverse[alias.lower()] = canonical_lc

                user_row = conn.execute(
                    text("SELECT name FROM characters WHERE id = :id"),
                    {"id": player_character_id},
                ).fetchone()
                if user_row is None or not user_row[0]:
                    raise RuntimeError(
                        "Canonical player character row "
                        f"{player_character_id} has no name"
                    )
                user_character_name = str(user_row[0])
                self.user_character_name = user_character_name
                canonical = user_character_name.lower()
                if canonical not in self.alias_lookup:
                    self.alias_lookup[canonical] = [user_character_name]
                    self.canonical_name_map[canonical] = user_character_name
                for alias in self.alias_lookup[canonical]:
                    self.alias_inverse[alias.lower()] = canonical
                for pronoun in ("you", "your", "yours", "yourself"):
                    self.alias_inverse[pronoun] = canonical

                place_rows = conn.execute(text("SELECT name FROM places")).fetchall()
                for row in place_rows:
                    name = row[0]
                    if not name:
                        continue
                    key = name.lower()
                    self.place_lookup[key] = name
                    if key.startswith("the "):
                        self.place_lookup[key[4:]] = name

        except RuntimeError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to load entity metadata: %s", exc)

    def _normalize_character_name(self, token: str) -> Optional[str]:
        """Map a token to a canonical character name using alias metadata."""

        if not token:
            return None

        key = token.lower()
        canonical = self.alias_inverse.get(key)
        if canonical:
            return self.canonical_name_map.get(canonical, canonical.title())

        # Handle possessive second-person pronouns e.g., "your"
        if key.endswith("'s"):
            base = key[:-2]
            canonical = self.alias_inverse.get(base)
            if canonical:
                return self.canonical_name_map.get(canonical, canonical.title())

        return None

    def _normalize_location_name(self, token: str) -> Optional[str]:
        """Map a token to a canonical place name."""

        if not token:
            return None

        key = token.lower()
        if key in self.place_lookup:
            return self.place_lookup[key]

        if key.startswith("the "):
            trimmed = key[4:]
            if trimmed in self.place_lookup:
                return self.place_lookup[trimmed]

        if key.endswith("'s"):
            base = key[:-2]
            if base in self.place_lookup:
                return self.place_lookup[base]

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _analyze_storyteller_output(self, narrative: str) -> Dict[str, Any]:
        """Lightweight heuristic analysis of storyteller output."""
        text = narrative or ""
        if not text.strip():
            return {
                "characters": [],
                "locations": [],
                "keywords": [],
                "themes": [],
                "expected": [],
            }

        character_candidates = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
        characters: List[str] = []
        locations: List[str] = []

        for candidate in character_candidates:
            normalized = re.sub(r"[^A-Za-z0-9\-'\s]", "", candidate).strip()
            normalized = re.sub(r"'s$", "", normalized)
            if not normalized:
                continue

            character_name = self._normalize_character_name(normalized)
            if character_name:
                if character_name not in characters:
                    characters.append(character_name)
                continue

            location_name = self._normalize_location_name(normalized)
            if location_name:
                if location_name not in locations:
                    locations.append(location_name)
                continue

            # Fallback: standalone capitalised tokens are provisional
            # character names.
            lower_normalized = normalized.lower()
            if (
                " " not in normalized
                and normalized[0].isupper()
                and lower_normalized not in _COMMON_STOPWORDS
            ):
                if normalized not in characters:
                    characters.append(normalized)

        tokens = [token.lower() for token in re.findall(r"[a-zA-Z']+", text)]
        filtered_tokens = [
            token
            for token in tokens
            if len(token) > 4 and token not in _COMMON_STOPWORDS
        ]
        token_counts = Counter(filtered_tokens)
        if self.idf_dictionary and token_counts:
            scored = []
            for word, count in token_counts.items():
                try:
                    idf = self.idf_dictionary.get_idf(word)
                except Exception:  # pragma: no cover - defensive
                    idf = 1.0
                scored.append((word, count * idf, count, idf))
            scored.sort(key=lambda item: (-item[1], -item[2], item[0]))
            keywords = [word for word, *_ in scored[:8]]
        else:
            keywords = [word for word, count in token_counts.most_common(8)]

        themes: List[str] = []
        expected = list(dict.fromkeys(characters))[:10]

        return {
            "characters": sorted(set(characters)),
            "locations": sorted(set(locations)),
            "keywords": keywords,
            "themes": themes,
            "expected": expected,
        }

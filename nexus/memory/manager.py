"""High level manager orchestrating LORE's custom memory flows."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

from sqlalchemy import text

from nexus.agents.orrery.player_identity import canonical_player_character_id
from nexus.config.story_model import StorySettings

from .baseline_compat import (
    config_hash,
    describe_changes,
    diff_config_snapshots,
    pass2_baseline_config_fingerprint,
    snapshot_config,
)
from .context_state import (
    ContextPackage,
    ContextStateManager,
    MemoryIdentity,
    RETROGRADE_SUMMARY_ID_PREFIX,
    Pass2Baseline,
    Pass2BaselineV1,
    Pass2BaselineV2,
    PassTransition,
    is_retrograde_summary,
    memory_identity,
    parse_pass2_baseline,
    restamp_pass2_baseline,
)
from .correspondence import correspondence_settings, load_accepted_correspondence
from .divergence import DivergenceResult
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


_WINDOW_SETTING = "lore.token_budget.apex_context_window"
_REFRESH_COMMAND = (
    "scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --slot <1-5>"
)


def empty_pass2_baseline(settings: Mapping[str, Any]) -> Pass2BaselineV2:
    """Build the explicit empty baseline staged by bootstrap/admin boundary tools."""

    return Pass2BaselineV2.for_settings(
        settings,
        memory_identities=[],
        prior_token_accounting={},
        remaining_budget=0,
    )


def incompatible_pass2_baseline_reason(
    baseline: Pass2Baseline, settings: Mapping[str, Any]
) -> Optional[str]:
    """Explain why a baseline cannot continue under ``settings``.

    Returns ``None`` when the full fingerprints match, or when a schema-2
    baseline differs only in budget-class settings and may be rebased.
    """

    if baseline.config_fingerprint == pass2_baseline_config_fingerprint(settings):
        return None
    if isinstance(baseline, Pass2BaselineV1):
        return (
            "This schema-1 baseline records no settings snapshot, so the change "
            "cannot be classified. After confirming Pass-2 semantics are "
            f"unchanged, run {_REFRESH_COMMAND}."
        )
    stored = baseline.config_snapshot
    if config_hash(stored.legacy_payload()) != baseline.config_fingerprint:
        return (
            "Its settings snapshot does not reproduce its config fingerprint, so "
            "the change cannot be classified. Refresh it with "
            f"{_REFRESH_COMMAND} only after confirming Pass-2 semantics are "
            "unchanged."
        )
    current = snapshot_config(settings)
    if baseline.semantic_fingerprint == current.semantic_fingerprint():
        return None
    changes = diff_config_snapshots(stored, current)
    semantic = [change for change in changes if change.compatibility == "semantic"]
    budget = [change for change in changes if change.compatibility == "budget"]
    return (
        f"Semantic settings changed: {describe_changes(semantic)}. Budget "
        f"settings changed: {describe_changes(budget)}. Restore the previous "
        "semantic values, or accept them for this story as an explicit operator "
        f"intervention with {_REFRESH_COMMAND} (docs/settings_scopes.md)."
    )


def plan_tail_window_rebase(
    baseline: Pass2Baseline,
    *,
    previous_settings: Mapping[str, Any],
    current_settings: Mapping[str, Any],
) -> Optional[Pass2BaselineV2]:
    """Decide whether a player's window change rewrites the accepted tail.

    Only a tail fingerprinted under exactly the pre-change settings is
    restamped under the new ones; any other tail is left for restoration to
    classify (or refuse) loudly.
    """

    previous_fingerprint = pass2_baseline_config_fingerprint(previous_settings)
    if previous_fingerprint == pass2_baseline_config_fingerprint(current_settings):
        return None
    changes = diff_config_snapshots(
        snapshot_config(previous_settings), snapshot_config(current_settings)
    )
    semantic = [change for change in changes if change.compatibility == "semantic"]
    if semantic:
        raise RuntimeError(
            "A story context-window change altered semantic Pass-2 settings: "
            f"{describe_changes(semantic)}"
        )
    if baseline.config_fingerprint != previous_fingerprint:
        return None
    return restamp_pass2_baseline(baseline, current_settings)


def rebase_tail_pass2_baseline(
    cur: Any,
    *,
    previous_settings: Mapping[str, Any],
    current_settings: Mapping[str, Any],
    target: str,
) -> Optional[Pass2BaselineV2]:
    """Rewrite the accepted tail's baseline for a player's window change.

    Runs on the caller's transaction, after the story pin is written, so the
    pin and the rewritten tail commit or roll back together. Returns the
    rewritten baseline, or ``None`` when nothing needed rewriting.
    """

    cur.execute("SELECT id FROM narrative_chunks ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        return None
    chunk_id = int(row[0])
    cur.execute(
        "SELECT schema_version, payload FROM lore_pass_baselines "
        "WHERE chunk_id = %s FOR UPDATE",
        (chunk_id,),
    )
    row = cur.fetchone()
    if row is None:
        # Restoration names the stamping remedy for a missing baseline.
        return None
    baseline = parse_pass2_baseline(row[1])
    if baseline.parent_chunk_id != chunk_id or baseline.schema_version != row[0]:
        raise RuntimeError(
            f"{target} tail chunk {chunk_id} Pass-2 baseline identity or schema "
            f"mismatch: column={row[0]}, payload={baseline.schema_version}, "
            f"parent={baseline.parent_chunk_id}"
        )
    rebased = plan_tail_window_rebase(
        baseline,
        previous_settings=previous_settings,
        current_settings=current_settings,
    )
    if rebased is None:
        if baseline.config_fingerprint != pass2_baseline_config_fingerprint(
            current_settings
        ):
            logger.warning(
                "%s tail chunk %s Pass-2 baseline was not fingerprinted under the "
                "pre-change settings; left unchanged for the next continuation "
                "to classify",
                target,
                chunk_id,
            )
        return None
    cur.execute(
        "UPDATE lore_pass_baselines SET schema_version = %s, payload = %s::jsonb "
        "WHERE chunk_id = %s",
        (
            rebased.schema_version,
            json.dumps(rebased.model_dump(mode="json")),
            chunk_id,
        ),
    )
    old_window = snapshot_config(previous_settings).value(_WINDOW_SETTING)
    logger.warning(
        "Player context-window change on %s rebased tail chunk %s Pass-2 "
        "baseline (schema %s -> %s): window %r -> %r; kept %s memory identities, "
        "the prior token accounting and remaining budget %s",
        target,
        chunk_id,
        baseline.schema_version,
        rebased.schema_version,
        old_window,
        rebased.config_snapshot.value(_WINDOW_SETTING),
        len(rebased.memory_identities),
        rebased.remaining_budget,
    )
    return rebased


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
        dbname: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self._base_settings = settings
        self.dbname = dbname
        self.story_settings: StorySettings | None = None
        self._turn_model: Optional[str] = None
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
        logger.info("Using deterministic entity-based divergence detector")

        self.incremental = IncrementalRetriever(
            memnon=memnon,
            context_state=self.context_state,
            query_memory=self.query_memory,
            warm_slice_default=self.warm_slice_default,
            text_counter=self._estimate_tokens,
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
        self,
        provider_wire_type: str,
        provider_name: str,
        *,
        model: Optional[str] = None,
    ) -> int:
        """Apply the active provider's resource profile to payload budgets."""
        self._turn_model = model
        self._refresh_story_settings()
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
        self._turn_model = None
        self._refresh_story_settings()
        apex_context_window = resolve_base_storyteller_context_window(self.settings)
        self.provider_wire_type = None
        self.provider_name = None
        self._storyteller_budget_configured = True
        self._configure_phase2_budget(apex_context_window)
        return apex_context_window

    def _refresh_story_settings(self) -> None:
        """Resolve this story's budget without mutating another slot's defaults."""
        if self.dbname is not None:
            from nexus.config.story_model import (
                read_story_settings,
                story_context_settings,
            )

            self.story_settings = read_story_settings(self.dbname)
            self.settings = story_context_settings(
                self._base_settings, self.story_settings
            )

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
            story=self._estimator_story(),
        )

    def export_pass2_baseline(self) -> Pass2BaselineV2:
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
        return Pass2BaselineV2.for_settings(
            self.settings,
            memory_identities=identities,
            prior_token_accounting=prior_token_accounting,
            remaining_budget=transition.remaining_budget,
        )

    def restore_pass2_baseline(self, parent_chunk_id: int) -> Pass2Baseline:
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

        self._refresh_story_settings()
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

        return self.hydrate_pass2_baseline(
            parent_chunk_id,
            schema_version=row["schema_version"],
            payload=row["payload"],
            storyteller_text=row["storyteller_text"],
        )

    def hydrate_pass2_baseline(
        self,
        parent_chunk_id: int,
        *,
        schema_version: int,
        payload: Any,
        storyteller_text: Any,
    ) -> Pass2Baseline:
        """Validate one fetched baseline row against current settings and load it.

        An equal config fingerprint proceeds. A schema-2 baseline whose
        semantic settings are unchanged is rebased: its memory identities and
        prior accounting are kept, and this turn re-derives the remaining
        budget from live token counts capped by the new Phase-2 budget. Every
        other mismatch fails loudly.
        """

        baseline = parse_pass2_baseline(payload)
        if schema_version != baseline.schema_version:
            raise RuntimeError(
                "Pass-2 baseline schema columns disagree for parent chunk "
                f"{parent_chunk_id}: column={schema_version}, "
                f"payload={baseline.schema_version}"
            )
        if baseline.parent_chunk_id != parent_chunk_id:
            raise RuntimeError(
                "Pass-2 baseline parent identity mismatch: requested "
                f"{parent_chunk_id}, payload={baseline.parent_chunk_id}"
            )
        expected_fingerprint = pass2_baseline_config_fingerprint(self.settings)
        reason = incompatible_pass2_baseline_reason(baseline, self.settings)
        if reason is not None:
            raise RuntimeError(
                "Pass-2 baseline config fingerprint is incompatible for parent "
                f"chunk {parent_chunk_id}: stored={baseline.config_fingerprint}, "
                f"current={expected_fingerprint}. {reason}"
            )
        if (
            isinstance(baseline, Pass2BaselineV2)
            and baseline.config_fingerprint != expected_fingerprint
        ):
            self._log_budget_rebase(parent_chunk_id, baseline)

        if not isinstance(storyteller_text, str) or not storyteller_text:
            raise RuntimeError(
                f"Accepted parent chunk {parent_chunk_id} has no storyteller output"
            )
        analysis = self._analyze_storyteller_output(storyteller_text)
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
            storyteller_output=storyteller_text,
            expected_user_themes=analysis.get("expected", []),
            remaining_budget=baseline.remaining_budget,
        )
        self.context_state.store_baseline(package, transition)
        self.query_memory.reset_pass("pass2")
        return baseline

    def _log_budget_rebase(
        self, parent_chunk_id: int, baseline: Pass2BaselineV2
    ) -> None:
        """Record a budget-only rebase with the window and everything kept."""

        current = snapshot_config(self.settings)
        changes = diff_config_snapshots(baseline.config_snapshot, current)
        logger.warning(
            "Rebasing Pass-2 baseline for parent chunk %s in %s after budget-only "
            "settings changes (%s): window %r -> %r; kept %s memory identities "
            "and the prior token accounting (%s entries); the stored remaining "
            "budget %s is re-derived from this turn's token counts and capped by "
            "the new Phase-2 budget",
            parent_chunk_id,
            self.dbname or "unscoped settings",
            describe_changes(changes),
            baseline.config_snapshot.value(_WINDOW_SETTING),
            current.value(_WINDOW_SETTING),
            len(baseline.memory_identities),
            len(baseline.prior_token_accounting),
            baseline.remaining_budget,
        )

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
        logger.debug("Divergence detection: %s", divergence.detected)
        self.context_state.update_divergence(
            divergence.detected,
            divergence.gaps,
        )

        if not context or not transition:
            logger.debug("No baseline context available; skipping Phase 2")
            self._stage_retrieval_coverage(
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
            self._stage_retrieval_coverage(
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
            self._stage_retrieval_coverage(
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
            self._stage_retrieval_coverage(
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

        self._stage_retrieval_coverage(
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

    def _stage_retrieval_coverage(self, **kwargs: Any) -> None:
        """Keep retrieval evidence pending until the shipped block set is known."""
        self._pending_retrieval_coverage = kwargs

    def record_rendered_coverage(
        self,
        chunks: Iterable[Dict[str, Any]],
        rendered_chunk_tokens: Dict[MemoryIdentity, int],
    ) -> None:
        """Write coverage from retrieved identities that survived final rendering."""
        pending = getattr(self, "_pending_retrieval_coverage", None)
        if pending is None:
            return
        shipped = {
            self._memory_identity(chunk) for chunk in chunks if chunk.get("text")
        }
        kept = [
            chunk
            for chunk in pending["kept_chunks"]
            if self._memory_identity(chunk) in shipped
        ]
        data = dict(pending)
        data["kept_chunks"] = kept
        data["kept_tokens"] = sum(
            rendered_chunk_tokens[self._memory_identity(chunk)] for chunk in kept
        )
        audit_retrieval_coverage(**data)
        self._pending_retrieval_coverage = None

    def unregister_payload_chunks(
        self, chunks: Iterable[Dict[str, Any]]
    ) -> tuple[Set[MemoryIdentity], int]:
        """Remove Phase-5 drops from memory state and refund tracked retrievals."""

        return self.context_state.unregister_chunks(chunks)

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------
    def _estimator_story(self) -> StorySettings | None:
        """Return the turn writer pin, preserving an explicit route override."""
        return (
            StorySettings(skald_model=self._turn_model)
            if self._turn_model is not None
            else self.story_settings
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate memory admission with the resolved turn writer."""
        from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens

        return calculate_chunk_tokens(text, story=self._estimator_story())

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
            warm_slice.append({**chunk, "is_recalled": True})
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
            idf_scores = self.idf_dictionary.get_idfs(list(token_counts))
            for word, count in token_counts.items():
                idf = idf_scores[word]
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

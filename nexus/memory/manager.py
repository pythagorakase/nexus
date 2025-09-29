"""High level manager orchestrating LORE's custom memory flows."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import text

from .context_state import ContextPackage, ContextStateManager, PassTransition
from .divergence import DivergenceDetector, DivergenceResult
from .incremental import IncrementalRetriever
from .query_memory import QueryMemory

try:  # pragma: no cover - optional dependency during unit tests
    from nexus.agents.memnon.utils.alias_search import load_aliases_from_db
except ImportError:  # pragma: no cover - fallback if module unavailable
    load_aliases_from_db = None

logger = logging.getLogger(__name__)


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
        return {
            "divergence": self.divergence.to_dict(),
            "retrieved_chunk_ids": [chunk.get("chunk_id") or chunk.get("id") for chunk in self.retrieved_chunks],
            "tokens_used": self.tokens_used,
            "baseline_available": self.baseline_available,
        }


class ContextMemoryManager:
    """Coordinate Pass 1 baseline storage and Pass 2 incremental retrieval."""

    def __init__(
        self,
        settings: Dict[str, Any],
        memnon: Optional[object] = None,
        llm_manager: Optional[object] = None,
        token_manager: Optional[object] = None,
    ) -> None:
        self.settings = settings
        memory_settings = settings.get("memory", {})
        self.pass2_reserve = float(memory_settings.get("pass2_budget_reserve", 0.25))
        self.divergence_threshold = float(memory_settings.get("divergence_threshold", 0.7))
        self.warm_slice_default = bool(memory_settings.get("warm_slice_default", True))
        self.max_sql_iterations = int(memory_settings.get("max_sql_iterations", 5))

        self.context_state = ContextStateManager()
        self.query_memory = QueryMemory(max_iterations=self.max_sql_iterations)
        self.divergence_detector = DivergenceDetector(threshold=self.divergence_threshold)
        self.incremental = IncrementalRetriever(
            memnon=memnon,
            context_state=self.context_state,
            query_memory=self.query_memory,
            warm_slice_default=self.warm_slice_default,
        )

        self.llm_manager = llm_manager
        self.token_manager = token_manager

        self.alias_lookup: Dict[str, List[str]] = {}
        self.canonical_name_map: Dict[str, str] = {}
        self.alias_inverse: Dict[str, str] = {}
        self.place_lookup: Dict[str, str] = {}
        self.user_character_name: Optional[str] = None
        self.idf_dictionary = getattr(memnon, "idf_dictionary", None)

        self._initialize_entity_maps(memnon)

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of the current memory state for status reporting."""
        current_package = self.context_state.get_current_context()
        query_snapshot = self.query_memory.snapshot()
        pass1_usage = {}
        pass2_usage = {}

        if current_package:
            pass1_usage = {
                "baseline_tokens": current_package.token_usage.get("baseline_tokens", 0),
                "reserved_for_pass2": current_package.token_usage.get("reserved_for_pass2", 0),
            }
            pass2_usage = {
                "reserve_shortfall": current_package.token_usage.get("reserve_shortfall", 0),
                "remaining_budget": self.context_state.get_remaining_budget(),
            }
        return {
            "pass1": {
                "baseline_chunks": len(current_package.baseline_chunks) if current_package else 0,
                "baseline_themes": current_package.baseline_themes if current_package else [],
                "authorial_directives": current_package.authorial_directives if current_package else [],
                "structured_passages": current_package.structured_passages if current_package else [],
                "token_usage": pass1_usage,
            },
            "pass2": {
                "divergence_detected": current_package.divergence_detected if current_package else False,
                "divergence_confidence": current_package.divergence_confidence if current_package else 0.0,
                "additional_chunks": len(current_package.additional_chunks) if current_package else 0,
                "token_reserve_percent": int(self.pass2_reserve * 100),
                "usage": pass2_usage,
            },
            "query_memory": {
                "history": query_snapshot,
                "max_iterations": self.query_memory.max_iterations,
            },
            "settings": {
                "divergence_threshold": self.divergence_threshold,
                "warm_slice_default": self.warm_slice_default
            }
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def handle_storyteller_response(
        self,
        narrative: str,
        warm_slice: Optional[Iterable[Dict[str, Any]]] = None,
        retrieved_passages: Optional[Iterable[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        assembled_context: Optional[Dict[str, Any]] = None,
        authorial_directives: Optional[Iterable[str]] = None,
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
        directives = [
            directive.strip()
            for directive in (authorial_directives or [])
            if directive and directive.strip()
        ]

        baseline_chunks: set[int] = set()
        chunk_details: List[Dict[str, Any]] = []
        existing_ids: Set[int] = set()
        structured_passages: List[Dict[str, Any]] = []

        for collection in (warm_slice or []):
            normalized = dict(collection)
            chunk_id = self._coerce_chunk_id(normalized)
            if chunk_id is None:
                structured_passages.append(normalized)
                continue
            normalized.setdefault("chunk_id", chunk_id)
            baseline_chunks.add(chunk_id)
            existing_ids.add(chunk_id)
            chunk_details.append({"chunk_id": chunk_id, **normalized})

        chunk_retrievals: List[Dict[str, Any]] = []
        for passage in (retrieved_passages or []):
            normalized = dict(passage)
            chunk_id = self._coerce_chunk_id(normalized)
            if chunk_id is None:
                structured_passages.append(normalized)
                continue
            normalized.setdefault("chunk_id", chunk_id)
            existing_ids.add(chunk_id)
            chunk_retrievals.append(normalized)

        directive_chunks: List[Dict[str, Any]] = []
        directive_structured: List[Dict[str, Any]] = []
        if directives:
            directive_chunks, directive_structured = self._execute_authorial_directives(directives, existing_ids)
            if directive_chunks:
                chunk_retrievals.extend(directive_chunks)
            if directive_structured:
                structured_passages.extend(directive_structured)
            if assembled_context is not None:
                if directive_chunks:
                    retrieval_section = assembled_context.setdefault("retrieved_passages", {})
                    retrieval_results = retrieval_section.setdefault("results", [])
                    retrieval_results.extend(dict(result) for result in directive_chunks)
                if directive_structured:
                    structured_section = assembled_context.setdefault("structured_passages", [])
                    structured_section.extend(dict(result) for result in directive_structured)

        if assembled_context is not None:
            structured_section = assembled_context.setdefault("structured_passages", [])
            structured_section.extend(dict(result) for result in structured_passages)

        for passage in chunk_retrievals:
            chunk_id = passage.get("chunk_id")
            if chunk_id is None:
                continue
            baseline_chunks.add(chunk_id)
            chunk_details.append({"chunk_id": chunk_id, **passage})

        token_usage = token_usage or {}
        baseline_tokens = sum(
            token_usage.get(key, 0) for key in ("warm_slice", "structured", "augmentation")
        )
        total_available = token_usage.get("total_available", 0)
        reserved_for_pass2 = max(0, int(total_available * self.pass2_reserve))
        remaining_budget = max(0, total_available - baseline_tokens)
        reserve_shortfall = max(0, reserved_for_pass2 - remaining_budget)

        package = ContextPackage(
            baseline_chunks=baseline_chunks,
            baseline_entities=baseline_entities,
            baseline_themes=baseline_themes,
            authorial_directives=directives,
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
            authorial_directives=directives,
            structured_passages=structured_passages,
        )

        self.context_state.store_baseline(package, transition, chunk_details)
        if directives:
            for directive in directives:
                self.query_memory.record("pass1", directive)
        # Pass 2 queries are always reset when a new baseline is stored
        self.query_memory.reset_pass("pass2")
        logger.debug(
            "Pass 1 baseline stored: %s baseline chunks, %s expected themes, remaining budget=%s",
            len(baseline_chunks),
            len(expected_user_themes),
            remaining_budget,
        )
        return package

    # ------------------------------------------------------------------
    # Pass 2: User Input Handling
    # ------------------------------------------------------------------
    def handle_user_input(
        self,
        user_input: str,
        token_counts: Optional[Dict[str, int]] = None,
    ) -> Pass2Update:
        """Run Pass 2 divergence analysis and retrieve incremental context if needed."""

        context = self.context_state.context
        transition = self.context_state.transition
        divergence = self.divergence_detector.detect(user_input, context, transition)
        self.context_state.update_divergence(divergence.detected, divergence.confidence, divergence.gaps)

        if not context or not transition:
            logger.debug("No baseline context available; skipping incremental retrieval")
            return Pass2Update(divergence, [], 0, baseline_available=False)

        if token_counts and "total_available" in token_counts:
            # Adjust remaining budget if calculation changed significantly for this turn
            total_available = token_counts.get("total_available", transition.remaining_budget)
            baseline_tokens = context.token_usage.get("baseline_tokens", 0)
            reserve = int(total_available * self.pass2_reserve)
            new_budget = max(0, total_available - baseline_tokens)
            self.context_state.adjust_budget(new_budget)
            context.token_usage["reserved_for_pass2"] = reserve
            context.token_usage["reserve_shortfall"] = max(0, reserve - new_budget)

        budget = self.context_state.get_remaining_budget()
        retrieved: List[Dict[str, Any]] = []
        tokens_used = 0

        if divergence.detected and budget > 0:
            retrieved, tokens_used = self.incremental.retrieve_gap_context(divergence.gaps, budget)
        elif not divergence.detected and budget > 0:
            retrieved, tokens_used = self.incremental.expand_warm_slice(budget)

        if retrieved:
            new_chunks = self.context_state.register_additional_chunks(retrieved)
            tokens_consumed = self.context_state.consume_budget(tokens_used)
            logger.debug(
                "Pass 2 retrieved %s new chunks (tokens used=%s, consumed=%s)",
                len(new_chunks),
                tokens_used,
                tokens_consumed,
            )
        else:
            tokens_consumed = 0

        if context:
            reserve = context.token_usage.get("reserved_for_pass2", 0)
            context.token_usage["reserve_shortfall"] = max(
                0, reserve - self.context_state.get_remaining_budget()
            )

        return Pass2Update(divergence, retrieved, tokens_consumed, baseline_available=True)

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------
    def _execute_authorial_directives(
        self,
        directives: List[str],
        existing_ids: Set[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute authorial directives to pre-populate baseline context."""

        if not directives or not getattr(self.incremental, "memnon", None):
            return [], []

        memnon = self.incremental.memnon
        chunk_results: List[Dict[str, Any]] = []
        structured_results: List[Dict[str, Any]] = []
        seen: Set[int] = set(existing_ids)

        for directive in directives:
            directive_text = directive.strip()
            if not directive_text:
                continue

            if self.query_memory.has_run(directive_text):
                logger.debug("Skipping duplicate authorial directive: %s", directive_text)
                continue

            try:
                payload = memnon.query_memory(query=directive_text, k=6, use_hybrid=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Authorial directive query failed for '%s': %s", directive_text, exc)
                continue

            for result in payload.get("results", []):
                annotated = dict(result)
                annotated.setdefault("source", "authorial_directive")
                annotated.setdefault("query_source", "authorial_directive")
                annotated["directive"] = directive_text

                chunk_id = self._coerce_chunk_id(annotated)
                if chunk_id is None:
                    structured_results.append(annotated)
                    continue

                if chunk_id in seen:
                    continue

                seen.add(chunk_id)
                annotated.setdefault("chunk_id", chunk_id)
                chunk_results.append(annotated)

        return chunk_results, structured_results

    def _coerce_chunk_id(self, chunk: Dict[str, Any]) -> Optional[int]:
        """Attempt to coerce a chunk identifier without logging noise."""

        raw_id = chunk.get("chunk_id", chunk.get("id"))
        if raw_id is None:
            return None
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None

    def augment_warm_slice(self, warm_slice: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge existing warm slice chunks with any incremental additions."""

        if not warm_slice:
            warm_slice = []

        # Register baseline warm slice for deduplication in future passes
        self.context_state.register_chunks(warm_slice)

        additions = self.context_state.get_additional_chunk_details()
        if not additions:
            return warm_slice

        known_ids = {
            chunk_id
            for chunk in warm_slice
            for chunk_id in [self._coerce_chunk_id(chunk)]
            if chunk_id is not None
        }
        for chunk in additions:
            chunk_id = self._coerce_chunk_id(chunk)
            if chunk_id is None or chunk_id in known_ids:
                continue
            warm_slice.append(chunk)
            known_ids.add(chunk_id)

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

        if not memnon or not load_aliases_from_db:  # pragma: no cover - defensive
            return

        engine = getattr(getattr(memnon, "db_manager", None), "engine", None)
        if engine is None:
            return

        try:
            with engine.connect() as conn:
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

                result = conn.execute(
                    text("SELECT user_character FROM global_variables WHERE id = true")
                ).fetchone()
                if result and result[0]:
                    user_row = conn.execute(
                        text("SELECT name FROM characters WHERE id = :id"),
                        {"id": result[0]},
                    ).fetchone()
                    if user_row and user_row[0]:
                        self.user_character_name = user_row[0]
                        canonical = self.user_character_name.lower()
                        if canonical not in self.alias_lookup:
                            self.alias_lookup[canonical] = [self.user_character_name]
                            self.canonical_name_map[canonical] = self.user_character_name
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
            return {"characters": [], "locations": [], "keywords": [], "themes": [], "expected": []}

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

            # Fallback: treat standalone capitalised tokens as provisional character names
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


    

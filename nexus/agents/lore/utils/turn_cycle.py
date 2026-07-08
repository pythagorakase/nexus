"""
Turn Cycle Phase Implementations for LORE

Handles the execution of individual turn cycle phases.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Union, Iterable
from datetime import datetime

logger = logging.getLogger("nexus.lore.turn_cycle")

try:
    from .turn_context import TurnContext, TurnPhase
    from .entity_queries import (
        fetch_all_characters_with_references,
        fetch_all_places_with_references,
        fetch_all_factions_with_references,
    )
    from nexus.agents.logon.apex_schema import (
        StoryTurnResponse,
        StorytellerResponseExtended,
        StorytellerResponseMinimal,
        StorytellerResponseStandard,
        extract_narrative_text,
    )
    from nexus.agents.orrery.resolver import (
        _load_time_of_day,
        resolve_dry_run,
    )
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
    from nexus.agents.orrery.bleed import (
        record_bleed_offers,
        select_bleed_menu,
    )
    from nexus.config.settings_models import LORERetrievalSettings
except ImportError:
    # If relative import fails, try absolute
    from nexus.agents.lore.utils.turn_context import TurnContext, TurnPhase
    from nexus.agents.lore.utils.entity_queries import (
        fetch_all_characters_with_references,
        fetch_all_places_with_references,
        fetch_all_factions_with_references,
    )
    from nexus.agents.logon.apex_schema import (
        StoryTurnResponse,
        StorytellerResponseExtended,
        StorytellerResponseMinimal,
        StorytellerResponseStandard,
        extract_narrative_text,
    )
    from nexus.agents.orrery.resolver import (
        _load_time_of_day,
        resolve_dry_run,
    )
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
    from nexus.agents.orrery.bleed import (
        record_bleed_offers,
        select_bleed_menu,
    )
    from nexus.config.settings_models import LORERetrievalSettings

try:
    from nexus.agents.memnon.utils.query_analysis import QueryAnalyzer

    MEMNON_ANALYZER_AVAILABLE = True
except ImportError:
    MEMNON_ANALYZER_AVAILABLE = False
    logger.warning(
        "MEMNON QueryAnalyzer not available - using fallback query generation"
    )

STRUCTURED_RESPONSE_TYPES = (
    StorytellerResponseMinimal,
    StorytellerResponseStandard,
    StorytellerResponseExtended,
)


def _sorted_chunk_ids(chunk_ids: Iterable[Any]) -> List[Any]:
    """Sort chunk IDs deterministically even if old payloads mixed int/string IDs."""

    def sort_key(chunk_id: Any) -> tuple[int, Any]:
        try:
            return (0, int(chunk_id))
        except (TypeError, ValueError):
            return (1, str(chunk_id))

    return sorted(chunk_ids, key=sort_key)


def _chunk_text(chunk: Dict[str, Any]) -> str:
    """Return the best available narrative text from a warm-slice chunk."""

    text = chunk.get("text") or chunk.get("full_text") or ""
    return text.strip() if isinstance(text, str) else ""


class TurnCycleManager:
    """Manages the execution of turn cycle phases"""

    def __init__(self, lore_agent):
        """
        Initialize with reference to parent LORE agent.

        Args:
            lore_agent: Reference to the parent LORE instance
        """
        self.lore = lore_agent
        self.settings = lore_agent.settings

        # Initialize MEMNON's QueryAnalyzer if available
        self.query_analyzer = None
        if MEMNON_ANALYZER_AVAILABLE:
            memnon_settings = self.settings.get("Agent Settings", {}).get("MEMNON", {})
            self.query_analyzer = QueryAnalyzer(memnon_settings)

    def _max_deep_queries(self) -> int:
        """Resolve the configured deep-query budget for one turn."""

        retrieval_settings = self.settings.get("lore", {}).get("retrieval") or (
            self.settings.get("Agent Settings", {}).get("LORE", {}).get("retrieval", {})
        )
        default_budget = LORERetrievalSettings().max_deep_queries
        budget = retrieval_settings.get("max_deep_queries", default_budget)
        try:
            return max(1, int(budget))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid LORE retrieval max_deep_queries setting: {budget!r}"
            ) from exc

    def _raw_chunk_retrieval_query(self, turn_context: TurnContext) -> Optional[str]:
        """Resolve the current/parent chunk text to use as a baseline query."""

        for chunk in turn_context.warm_slice:
            if chunk.get("is_target"):
                text = _chunk_text(chunk)
                if text:
                    return text
        return None

    def _classify_query_type(self, query_text: str) -> str:
        """Classify a MEMNON query for phase-state accounting."""

        if not self.query_analyzer:
            return "general"

        query_info = self.query_analyzer.analyze_query(query_text)
        query_type = query_info.get("type", "general")
        logger.debug(f"Query '{query_text[:50]}...' classified as '{query_type}'")
        return query_type

    async def process_user_input(self, turn_context: TurnContext):
        """
        Phase 1: Process and validate user input.

        Args:
            turn_context: Current turn context
        """
        logger.debug("Processing user input...")

        # Calculate token budget
        if self.lore.token_manager:
            turn_context.token_counts = self.lore.token_manager.calculate_budget(
                turn_context.user_input
            )

        # Store processed input
        phase_state = {
            "processed": True,
            "token_count": turn_context.token_counts.get("user_input", 0),
        }
        if turn_context.target_chunk_id is not None:
            phase_state["target_chunk_id"] = turn_context.target_chunk_id
        turn_context.phase_states["user_input"] = phase_state

        memory_update = {}
        if getattr(self.lore, "memory_manager", None):
            try:
                pass2_update = self.lore.memory_manager.handle_user_input(
                    turn_context.user_input,
                    turn_context.token_counts,
                )
                memory_update = pass2_update.to_dict()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Pass 2 memory handling failed: %s", exc)
                memory_update = {"error": str(exc)}

        if memory_update:
            turn_context.memory_state["pass2"] = memory_update
        phase_state["memory_pass2"] = memory_update

    async def perform_warm_analysis(self, turn_context: TurnContext):
        """
        Phase 2: Prepare recent narrative context.

        Args:
            turn_context: Current turn context
        """
        logger.debug("Preparing warm context...")

        warm_slice_chunks: List[Dict[str, Any]] = []
        target_chunk_id = getattr(turn_context, "target_chunk_id", None)

        # Always try to include the requested continuation chunk first
        if self.lore.memnon and target_chunk_id is not None:
            try:
                target_chunk = self.lore.memnon.get_chunk_by_id(target_chunk_id)
                if target_chunk:
                    target_entry = dict(target_chunk)
                    if not target_entry.get("text") and target_entry.get("full_text"):
                        target_entry["text"] = target_entry["full_text"]
                    target_entry["is_target"] = True
                    warm_slice_chunks.append(target_entry)
                    logger.info(
                        f"Anchored warm slice to requested chunk {target_chunk_id}"
                    )
                else:
                    logger.warning(
                        f"Requested parent chunk {target_chunk_id} not found; using recent chunks instead"
                    )
            except Exception as exc:
                logger.error(f"Failed to load requested chunk {target_chunk_id}: {exc}")

        # Get recent narrative chunks from database if MEMNON available
        if self.lore.memnon:
            try:
                # Get chunk parameters from settings
                chunk_params = (
                    self.settings.get("Agent Settings", {})
                    .get("LORE", {})
                    .get("chunk_parameters", {})
                )
                initial_chunks = chunk_params.get("warm_slice_initial", 10)

                # Get most recent chunks directly
                recent_chunks = self.lore.memnon.get_recent_chunks(limit=initial_chunks)
                recent_list = recent_chunks.get("results", [])
                if target_chunk_id is None and recent_list:
                    recent_list[0]["is_target"] = True
                if target_chunk_id is not None:
                    recent_list = [
                        chunk
                        for chunk in recent_list
                        if chunk.get("id") != target_chunk_id
                    ]

                warm_slice_chunks.extend(recent_list)
                turn_context.warm_slice = warm_slice_chunks

                logger.info(
                    f"Retrieved {len(turn_context.warm_slice)} warm-slice chunks (including anchors)"
                )
            except Exception as e:
                logger.error(f"Failed to retrieve warm slice: {e}")
                turn_context.warm_slice = warm_slice_chunks
        else:
            turn_context.warm_slice = warm_slice_chunks

        if getattr(self.lore, "memory_manager", None):
            turn_context.warm_slice = self.lore.memory_manager.augment_warm_slice(
                turn_context.warm_slice
            )

        if not turn_context.warm_slice:
            raise RuntimeError(
                "FATAL: No warm slice chunks retrieved. "
                "Cannot assemble narrative context without recent chunks. "
                "Check database connection and chunk retrieval."
            )

        analysis = {
            "source": "programmatic_warm_slice",
            "chunk_count": len(turn_context.warm_slice),
            "target_chunk_id": target_chunk_id,
            "warm_chunk_ids": [
                chunk.get("id") or chunk.get("chunk_id")
                for chunk in turn_context.warm_slice
                if isinstance(chunk, dict)
                and (chunk.get("id") is not None or chunk.get("chunk_id") is not None)
            ],
        }

        turn_context.phase_states["warm_analysis"] = {
            "analysis": analysis,
            "chunk_count": len(turn_context.warm_slice),
        }

    async def query_entity_states(self, turn_context: TurnContext):
        """
        Phase 3: Query for entity states using hierarchical baseline + featured structure.

        Universal baseline: ALL entities with minimal tracking fields (always included)
        Featured entities: Referenced entities with full details

        This enables off-screen character tracking and more generous entity inclusion.

        Args:
            turn_context: Current turn context
        """
        logger.debug("Querying entity states with hierarchical structure...")

        if not self.lore.memnon:
            logger.warning("MEMNON not available for entity queries")
            turn_context.entity_data = {
                "characters": {"baseline": [], "featured": []},
                "locations": {"baseline": [], "featured": []},
                "factions": {"baseline": [], "featured": []},
                "relationships": [],
                "events": [],
                "threats": [],
            }
            return

        # Get entity_inclusion settings
        entity_settings = (
            self.settings.get("Agent Settings", {})
            .get("LORE", {})
            .get("entity_inclusion", {})
        )
        include_relationships = entity_settings.get("include_all_relationships", True)
        include_events = entity_settings.get("include_all_active_events", True)
        include_threats = entity_settings.get("include_all_active_threats", True)
        event_statuses = entity_settings.get(
            "active_event_statuses", ["active", "ongoing", "escalating"]
        )
        threat_statuses = entity_settings.get(
            "active_threat_statuses", ["active", "imminent"]
        )

        # Get chunk IDs from warm slice for featured entity queries
        warm_chunk_ids = [
            chunk.get("id") for chunk in turn_context.warm_slice if chunk.get("id")
        ]

        if not warm_chunk_ids:
            logger.warning("No chunk IDs in warm slice for entity queries")
            warm_chunk_ids = []

        # Query characters with baseline + featured structure
        characters_data = {"baseline": [], "featured": []}
        try:
            from sqlalchemy import text

            with self.lore.memnon.Session() as session:
                characters_data = fetch_all_characters_with_references(
                    session, warm_chunk_ids
                )
            logger.info(
                f"Characters: {len(characters_data['baseline'])} baseline, "
                f"{len(characters_data['featured'])} featured"
            )
        except Exception as e:
            logger.error(f"Failed to query characters: {e}")

        # Query places with baseline + featured structure
        # Include places that are current_location of featured characters
        featured_place_ids = set()
        for char in characters_data.get("featured", []):
            loc_name = char.get("current_location")
            if loc_name:
                # Get place ID from name (we'll query by name in the function)
                pass  # fetch_all_places_with_references handles this

        places_data = {"baseline": [], "featured": []}
        try:
            with self.lore.memnon.Session() as session:
                places_data = fetch_all_places_with_references(
                    session, warm_chunk_ids, featured_place_ids
                )
            logger.info(
                f"Places: {len(places_data['baseline'])} baseline, "
                f"{len(places_data['featured'])} featured"
            )
        except Exception as e:
            logger.error(f"Failed to query places: {e}")

        # Query factions with baseline + featured structure
        factions_data = {"baseline": [], "featured": []}
        try:
            with self.lore.memnon.Session() as session:
                factions_data = fetch_all_factions_with_references(
                    session, warm_chunk_ids
                )
            logger.info(
                f"Factions: {len(factions_data['baseline'])} baseline, "
                f"{len(factions_data['featured'])} featured"
            )
        except Exception as e:
            logger.error(f"Failed to query factions: {e}")

        # Query relationships between featured characters
        relationships = []
        if include_relationships and characters_data.get("featured"):
            try:
                char_ids = [
                    c.get("id") for c in characters_data["featured"] if c.get("id")
                ]
                if char_ids:
                    with self.lore.memnon.Session() as session:
                        rel_query = text(
                            """
                            SELECT *
                            FROM character_relationships
                            WHERE character1_id = ANY(:char_ids)
                              AND character2_id = ANY(:char_ids)
                        """
                        )
                        result = session.execute(rel_query, {"char_ids": char_ids})
                        for row in result:
                            relationships.append(dict(row._mapping))
                    logger.info(
                        f"Found {len(relationships)} relationships between featured characters"
                    )
            except Exception as e:
                logger.error(f"Failed to query relationships: {e}")

        # Query all active events
        events = []
        if include_events:
            try:
                max_events = entity_settings.get("max_total_events", 15)
                with self.lore.memnon.Session() as session:
                    event_query = text(
                        """
                        SELECT *
                        FROM events
                        WHERE status = ANY(:statuses)
                        ORDER BY id DESC
                        LIMIT :max_events
                    """
                    )
                    result = session.execute(
                        event_query,
                        {"statuses": event_statuses, "max_events": max_events},
                    )
                    for row in result:
                        events.append(dict(row._mapping))
                logger.info(f"Found {len(events)} active events")
            except Exception as e:
                # Events table doesn't exist yet - this is non-fatal
                if "does not exist" in str(e):
                    logger.debug(f"Events table not available: {e}")
                else:
                    logger.error(f"Failed to query active events: {e}")

        # Query all active threats
        threats = []
        if include_threats:
            try:
                max_threats = entity_settings.get("max_total_threats", 10)
                with self.lore.memnon.Session() as session:
                    # Note: threats table uses is_active boolean, not status enum
                    # Lifecycle stages: inception, developing, active, resolved, dormant
                    threat_query = text(
                        """
                        SELECT *
                        FROM threats
                        WHERE is_active = true
                        ORDER BY id DESC
                        LIMIT :max_threats
                    """
                    )
                    result = session.execute(threat_query, {"max_threats": max_threats})
                    for row in result:
                        threats.append(dict(row._mapping))
                logger.info(f"Found {len(threats)} active threats")
            except Exception as e:
                # Handle schema mismatches gracefully
                if "does not exist" in str(e):
                    logger.debug(f"Threats table or column not available: {e}")
                else:
                    logger.error(f"Failed to query active threats: {e}")

        # Store hierarchical entity data
        turn_context.entity_data = {
            "characters": characters_data,
            "locations": places_data,
            "factions": factions_data,
            "relationships": relationships,
            "events": events,
            "threats": threats,
        }

        turn_context.phase_states["entity_state"] = {
            "characters_baseline": len(characters_data.get("baseline", [])),
            "characters_featured": len(characters_data.get("featured", [])),
            "locations_baseline": len(places_data.get("baseline", [])),
            "locations_featured": len(places_data.get("featured", [])),
            "factions_baseline": len(factions_data.get("baseline", [])),
            "factions_featured": len(factions_data.get("featured", [])),
            "relationships_found": len(relationships),
            "events_found": len(events),
            "threats_found": len(threats),
            "method": "hierarchical_baseline_featured",
        }

        logger.info(
            f"Entity query complete (hierarchical): "
            f"chars {len(characters_data.get('baseline', []))}+{len(characters_data.get('featured', []))}, "
            f"places {len(places_data.get('baseline', []))}+{len(places_data.get('featured', []))}, "
            f"factions {len(factions_data.get('baseline', []))}+{len(factions_data.get('featured', []))}, "
            f"{len(relationships)} rels, {len(events)} events, {len(threats)} threats"
        )

    async def execute_deep_queries(self, turn_context: TurnContext):
        """
        Phase 4: Execute deep memory queries.

        Retrieval uses the full current/parent chunk as the baseline query.
        MEMNON's QueryAnalyzer classifies raw chunk text for optimal search.
        """
        logger.debug("Executing deep queries...")

        if not self.lore.memnon:
            logger.warning("MEMNON not available for deep queries")
            return

        if getattr(self.lore, "memory_manager", None):
            self.lore.memory_manager.reset_pass1_queries()

        # Full chunk text is the retrieval baseline.
        queries = []
        raw_chunk_query = self._raw_chunk_retrieval_query(turn_context)
        if raw_chunk_query:
            queries.append(
                {
                    "text": raw_chunk_query,
                    "type": self._classify_query_type(raw_chunk_query),
                    "source": "raw_chunk",
                }
            )

        if not queries:
            turn_context.retrieved_passages = []
            turn_context.phase_states["deep_queries"] = {
                "queries_executed": 0,
                "query_types": {},
                "query_sources": {
                    "raw_chunk": 0,
                    "llm_generated": 0,
                },
                "results_retrieved": 0,
            }
            logger.warning("No raw chunk text available for deep queries")
            return

        # Execute queries with proper SearchManager configuration
        all_results = []
        query_type_counts = {}
        max_deep_queries = self._max_deep_queries()

        for query_obj in queries[:max_deep_queries]:
            if getattr(self.lore, "memory_manager", None):
                self.lore.memory_manager.record_pass1_query(query_obj["text"])
            try:
                # MEMNON's SearchManager uses the query type internally
                # to adjust vector/text weights for optimal results
                results = self.lore.memnon.query_memory(
                    query=query_obj["text"],
                    k=15,  # Get more results since we'll deduplicate
                    use_hybrid=True,
                )

                # Track query types for logging
                query_type = query_obj["type"]
                query_type_counts[query_type] = query_type_counts.get(query_type, 0) + 1

                # Tag results with query metadata
                for result in results.get("results", []):
                    result["query_type"] = query_type
                    result["query_source"] = query_obj["source"]

                all_results.extend(results.get("results", []))

            except Exception as e:
                logger.error(f"Query failed for '{query_obj['text'][:50]}...': {e}")

        # Store unique results, preserving highest scores
        seen_ids = {}
        for result in all_results:
            chunk_id = result.get("id")
            if chunk_id:
                if chunk_id not in seen_ids or result.get("score", 0) > seen_ids[
                    chunk_id
                ].get("score", 0):
                    seen_ids[chunk_id] = result

        # Sort by score and take top results
        unique_results = sorted(
            seen_ids.values(), key=lambda x: x.get("score", 0), reverse=True
        )[
            :30
        ]  # Keep top 30 for augmentation

        turn_context.retrieved_passages = unique_results
        turn_context.phase_states["deep_queries"] = {
            "queries_executed": len(queries),
            "query_types": query_type_counts,
            "query_sources": {
                "raw_chunk": sum(
                    1 for query in queries if query.get("source") == "raw_chunk"
                ),
                "llm_generated": sum(
                    1 for query in queries if query.get("source") == "llm_generated"
                ),
            },
            "results_retrieved": len(unique_results),
        }

        logger.info(
            f"Deep queries complete: {len(queries)} queries executed "
            f"({query_type_counts}), {len(unique_results)} unique results retrieved"
        )

    # DEPRECATED: Cold Distillation phase removed - cross-encoders handle reranking

    async def resolve_orrery(self, turn_context: TurnContext):
        """
        Phase 4.5: Resolve Orrery behavior packages without canonical writes.

        The proposal is intentionally kept on TurnContext only. It is not injected
        into the storyteller payload until a later phase proves the no-write path.
        """
        orrery_settings = self.settings.get("orrery", {})
        if not orrery_settings.get("enabled", False):
            turn_context.phase_states["orrery_resolve"] = {
                "enabled": False,
                "skipped": True,
            }
            return

        if not self.lore.memnon:
            raise RuntimeError("Orrery resolve requires MEMNON database access")

        binding_settings = orrery_settings.get("binding", {})
        window_chunks = int(binding_settings.get("window_chunks", 30))
        with self.lore.memnon.Session() as session:
            anchor_chunk_id = self._orrery_anchor_chunk_id(session, turn_context)
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                sunhelm_settings=orrery_settings.get("sunhelm"),
                selection_settings=orrery_settings.get("selection"),
                habituation_settings=orrery_settings.get("habituation"),
                fanout_settings=orrery_settings.get("fanout"),
            )

        turn_context.orrery_proposal = proposal
        turn_context.phase_states["orrery_resolve"] = {
            "enabled": True,
            "anchor_chunk_id": proposal.anchor_chunk_id,
            "actor_count": proposal.actor_count,
            "resolution_count": proposal.resolution_count,
            "pressure_count": proposal.pressure_count,
            "template_ids": [
                resolution.template_id for resolution in proposal.resolutions
            ],
            "pressure_template_ids": [
                pressure.template_id for pressure in proposal.scene_pressures
            ],
        }
        logger.info(
            "Orrery dry-run resolved %d actors into %d draft resolutions "
            "and %d scene pressures",
            proposal.actor_count,
            proposal.resolution_count,
            proposal.pressure_count,
        )

    @staticmethod
    def _load_intertitle(
        session: Any, *, anchor_chunk_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Headline state at the anchor chunk: the runtime intertitle.

        Season/episode/scene/layer and the world clock come from the
        anchor's chunk_metadata; the location is the protagonist's current
        place (characters.id = 1 — the new-story mapper creates the
        protagonist first). Everything here is display-and-prompt state;
        nothing is baked into narrative text.
        """

        if anchor_chunk_id is None:
            return None
        from sqlalchemy import text as _text

        row = (
            session.execute(
                _text(
                    """
                    /* orrery:intertitle */
                    SELECT cm.season, cm.episode, cm.scene, cm.world_layer,
                           cm.world_time,
                           c.name AS protagonist_name,
                           p.name AS location_name
                    FROM chunk_metadata cm
                    LEFT JOIN characters c ON c.id = 1
                    LEFT JOIN places p ON p.id = c.current_location
                    WHERE cm.chunk_id = :anchor
                    """
                ),
                {"anchor": anchor_chunk_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        world_time = row["world_time"]
        return {
            "season": row["season"],
            "episode": row["episode"],
            "scene": row["scene"],
            "world_layer": row["world_layer"],
            "world_time": world_time.isoformat() if world_time else None,
            "time_of_day": (_load_time_of_day(world_time) if world_time else None),
            "protagonist_name": row["protagonist_name"],
            "location_name": row["location_name"],
        }

    def _orrery_anchor_chunk_id(
        self, session: Any, turn_context: TurnContext
    ) -> Optional[int]:
        """Choose the current read anchor for a no-write Orrery resolve."""

        if turn_context.target_chunk_id is not None:
            return turn_context.target_chunk_id

        warm_ids = [
            chunk.get("id")
            for chunk in turn_context.warm_slice
            if isinstance(chunk, dict) and chunk.get("id") is not None
        ]
        if warm_ids:
            try:
                return max(int(chunk_id) for chunk_id in warm_ids)
            except (TypeError, ValueError):
                logger.warning("Unable to infer Orrery anchor from warm-slice IDs")

        from sqlalchemy import text

        row = (
            session.execute(text("SELECT max(id) AS max_id FROM narrative_chunks"))
            .mappings()
            .first()
        )
        return row["max_id"] if row and row["max_id"] is not None else None

    async def stamp_intertitle(self, turn_context: TurnContext) -> None:
        """Phase 4.75: load the runtime intertitle for the anchor chunk.

        Deliberately independent of [orrery] enabled — Skald needs the
        headline state (clock, season/episode/scene, layer, protagonist
        location) on every turn, not only when the behavior engine runs.
        Bootstrap turns (no chunks yet) simply have no intertitle.
        """

        if not self.lore.memnon:
            raise RuntimeError("Intertitle stamping requires MEMNON database access")
        with self.lore.memnon.Session() as session:
            anchor_chunk_id = self._orrery_anchor_chunk_id(session, turn_context)
            turn_context.intertitle = self._load_intertitle(
                session, anchor_chunk_id=anchor_chunk_id
            )

    async def assemble_context_payload(self, turn_context: TurnContext):
        """
        Phase 5: Assemble final context payload.

        Args:
            turn_context: Current turn context
        """
        logger.debug("Assembling context payload...")

        await self.select_orrery_bleed(turn_context)

        # Build the context payload
        turn_context.context_payload = {
            "user_input": turn_context.user_input,
            "warm_slice": {
                "chunks": turn_context.warm_slice,
                "token_count": turn_context.token_counts.get("warm_slice", 0),
            },
            "entity_data": turn_context.entity_data,
            "retrieved_passages": {
                "results": turn_context.retrieved_passages,
                "token_count": turn_context.token_counts.get("augmentation", 0),
            },
            "metadata": {
                "turn_id": turn_context.turn_id,
                "timestamp": datetime.now().isoformat(),
            },
            "memory_state": turn_context.memory_state,
        }

        if turn_context.note:
            turn_context.context_payload["note"] = turn_context.note

        if turn_context.intertitle:
            turn_context.context_payload["intertitle"] = turn_context.intertitle

        proposal: Any = turn_context.orrery_proposal
        if proposal and getattr(proposal, "resolution_count", 0):
            turn_context.context_payload["orrery_imminent_activity"] = [
                draft.to_dict() for draft in proposal.resolutions
            ]

        if turn_context.orrery_proposal and turn_context.orrery_proposal.pressure_count:
            turn_context.context_payload["orrery_scene_pressures"] = [
                pressure.to_dict()
                for pressure in turn_context.orrery_proposal.scene_pressures
            ]

        if proposal and getattr(proposal, "joint_beats", ()):
            turn_context.context_payload["orrery_joint_beats"] = [
                beat.to_dict() for beat in proposal.joint_beats
            ]

        if turn_context.bleed_menu:
            turn_context.context_payload["orrery_bleed_menu"] = [
                candidate.to_prompt_dict() for candidate in turn_context.bleed_menu
            ]

        if turn_context.target_chunk_id is not None:
            turn_context.context_payload["metadata"][
                "target_chunk_id"
            ] = turn_context.target_chunk_id

        # Calculate utilization
        if self.lore.token_manager:
            utilization = self.lore.token_manager.calculate_utilization(
                turn_context.token_counts
            )
        else:
            utilization = 0

        turn_context.phase_states["payload_assembly"] = {
            "total_tokens_used": sum(
                [
                    turn_context.token_counts.get("user_input", 0),
                    turn_context.token_counts.get("warm_slice", 0),
                    turn_context.token_counts.get("structured", 0),
                    turn_context.token_counts.get("augmentation", 0),
                ]
            ),
            "utilization_percentage": utilization,
        }

        logger.info(f"Context payload assembled: {utilization:.1f}% budget utilization")

    async def select_orrery_bleed(self, turn_context: TurnContext) -> None:
        """Populate optional Orrery Bleed menu before payload assembly."""

        orrery_settings = self.settings.get("orrery", {})
        if not orrery_settings.get("enabled", False):
            return

        bleed_settings = orrery_settings.get("bleed", {})
        max_candidates = int(bleed_settings.get("max_candidates", 3))
        if max_candidates <= 0:
            turn_context.phase_states["orrery_bleed"] = {
                "enabled": True,
                "skipped": True,
                "reason": "max_candidates_zero",
            }
            return

        if not self.lore.memnon:
            raise RuntimeError("Orrery bleed requires MEMNON database access")

        with self.lore.memnon.Session() as session:
            if turn_context.orrery_proposal is not None:
                anchor_chunk_id = turn_context.orrery_proposal.anchor_chunk_id
            else:
                anchor_chunk_id = self._orrery_anchor_chunk_id(session, turn_context)
            if anchor_chunk_id is None:
                turn_context.phase_states["orrery_bleed"] = {
                    "enabled": True,
                    "skipped": True,
                    "reason": "no_anchor_chunk",
                }
                return

            result = select_bleed_menu(
                session,
                anchor_chunk_id=anchor_chunk_id,
                max_candidates=max_candidates,
            )

        turn_context.bleed_menu = result.selected
        turn_context.phase_states["orrery_bleed"] = {
            "enabled": True,
            "anchor_chunk_id": anchor_chunk_id,
            "candidate_count": result.candidates_considered,
            "selected_count": len(result.selected),
            "offers_recorded": 0,
        }

    def record_orrery_bleed_offers(self, turn_context: TurnContext) -> None:
        """Record Bleed offer bookkeeping after successful generation."""

        if not turn_context.bleed_menu:
            return

        phase_state = turn_context.phase_states.setdefault("orrery_bleed", {})
        if phase_state.get("offers_recorded"):
            return

        anchor_chunk_id = phase_state.get("anchor_chunk_id")
        if anchor_chunk_id is None:
            raise RuntimeError("Orrery bleed selected candidates without an anchor")
        if not self.lore.memnon:
            raise RuntimeError("Orrery bleed offer recording requires MEMNON")

        with self.lore.memnon.Session() as session:
            record_bleed_offers(
                session,
                turn_context.bleed_menu,
                anchor_chunk_id=int(anchor_chunk_id),
            )

        phase_state["offers_recorded"] = len(turn_context.bleed_menu)

    async def call_apex_ai(self, turn_context: TurnContext) -> str:
        """
        Phase 6: Call Apex AI for narrative generation.

        Args:
            turn_context: Current turn context

        Returns:
            Generated narrative response
        """
        logger.debug("Calling Apex AI...")

        if not self.lore.enable_logon:
            logger.info("LOGON disabled; skipping Apex AI call")
            turn_context.phase_states["apex_generation"] = {
                "success": False,
                "skipped": True,
                "reason": "logon_disabled",
            }
            return "LOGON disabled"

        try:
            self.lore.ensure_logon()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"LOGON initialization failed: {exc}")
            turn_context.phase_states["apex_generation"] = {
                "success": False,
                "error": str(exc),
            }
            return "Error: API communication unavailable"

        if not self.lore.logon:
            logger.error("LOGON not available for API calls")
            turn_context.phase_states["apex_generation"] = {
                "success": False,
                "error": "LOGON unavailable",
            }
            return "Error: API communication unavailable"

        try:
            # Generate narrative with structured output
            story_response = await self.lore.logon.generate_narrative_async(
                turn_context.context_payload
            )

            # Store the full structured response
            turn_context.apex_response = story_response

            # Extract narrative text for backward compatibility
            narrative_text = story_response.narrative

            chunk_metadata = getattr(story_response, "chunk_metadata", None)
            referenced_entities = getattr(story_response, "referenced_entities", None)
            state_updates = getattr(story_response, "state_updates", None)

            turn_context.phase_states["apex_generation"] = {
                "success": True,
                "has_metadata": chunk_metadata is not None,
                "has_entities": referenced_entities is not None,
                "has_state_updates": state_updates is not None,
                "narrative_length": len(narrative_text),
            }

            self.record_orrery_bleed_offers(turn_context)

            return story_response  # Return the full StoryTurnResponse

        except Exception as e:
            logger.error("Apex AI call failed: %s", e)
            turn_context.phase_states["apex_generation"] = {
                "success": False,
                "error": str(e),
            }
            raise

    async def integrate_response(
        self,
        turn_context: TurnContext,
        response: Union[str, StoryTurnResponse],
    ) -> None:
        """
        Phase 7: Integrate Apex response and update state.

        Args:
            turn_context: Current turn context
            response: Generated narrative response
        """
        logger.debug("Integrating response...")

        # In a full implementation, this would:
        # 1. Parse the response for state updates
        # 2. Update character states via PSYCHE
        # 3. Update world state via GAIA
        # 4. Store the new narrative chunk in database

        # For now, just log the completion
        if isinstance(response, STRUCTURED_RESPONSE_TYPES):
            narrative_text = extract_narrative_text(response)
            structured_response = response
        else:
            narrative_text = response if isinstance(response, str) else str(response)
            structured_response = None

        turn_context.phase_states["integration"] = {
            "response_length": len(narrative_text),
            "integration_complete": True,
        }

        if structured_response is not None:
            turn_context.phase_states["integration"][
                "structured_response"
            ] = structured_response.model_dump()

        if getattr(self.lore, "memory_manager", None):
            try:
                baseline = self.lore.memory_manager.handle_storyteller_response(
                    narrative=narrative_text,
                    warm_slice=turn_context.warm_slice,
                    retrieved_passages=turn_context.retrieved_passages,
                    token_usage=turn_context.token_counts,
                    assembled_context=turn_context.context_payload,
                )
                transition = self.lore.memory_manager.context_state.transition
                baseline_snapshot = {
                    "baseline_chunks": _sorted_chunk_ids(baseline.baseline_chunks),
                    "baseline_themes": baseline.baseline_themes,
                    "expected_user_themes": (
                        transition.expected_user_themes if transition else []
                    ),
                    "remaining_budget": self.lore.memory_manager.context_state.get_remaining_budget(),
                    "structured_passages": baseline.structured_passages,
                }
                turn_context.memory_state["pass1"] = baseline_snapshot
                turn_context.phase_states["integration"][
                    "memory_baseline"
                ] = baseline_snapshot
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Pass 1 baseline storage failed: %s", exc)
                turn_context.memory_state.setdefault("errors", []).append(str(exc))

        # Store narrative chunk if MEMNON available
        if self.lore.memnon and narrative_text:
            try:
                # This would normally use a proper method to store the chunk
                logger.info("Would store new narrative chunk to database")
            except Exception as e:
                logger.error(f"Failed to store narrative chunk: {e}")

"""Event producer-to-gate contracts on disposable PostgreSQL template clones.

Requires NEXUS_template with its current schema and vocabulary seeds. Exercises
Retrograde's canonical writer, world_events and participant provenance, and the
production resolver hydration. No native save slots or provider calls are used.
"""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine

from nexus.agents.orrery.audit import EXOGENOUS_EVENT_PRODUCERS, build_catalog
from nexus.agents.orrery.coverage import analyze_coverage
from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.retrograde_expansion import RetrogradeExpansionEventPlan
from nexus.agents.orrery.retrograde_graph import build_candidate_graph
from nexus.agents.orrery.retrograde_persistence import (
    _ensure_prologue_metadata,
    _insert_prologue_chunk,
    _load_entity_index,
    _load_event_types,
)
from nexus.agents.orrery.retrograde_vocabulary import enumerate_seed_eligible_vocabulary
from nexus.agents.orrery.substrate import Slot
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES, CONSULT_RIVAL
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.config import load_settings
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist
from tests.pg_fixtures import sqlalchemy_url

pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def event_source_db() -> Iterator[tuple[str, int, int, int]]:
    """Seed one real rival pair and a canonical Retrograde history anchor."""

    with disposable_slot_database("test_event_sources") as dbname:
        VALID_DBNAMES.add(dbname)
        try:
            actor_character, actor = seed_protagonist(dbname, name="Mara")
            with connect(dbname) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO entities (kind, is_active) "
                        "VALUES ('character', true) RETURNING id"
                    )
                    target = int(cur.fetchone()[0])
                    cur.execute(
                        "INSERT INTO characters (name, summary, entity_id) "
                        "VALUES ('Vale', 'A rival.', %s) RETURNING id",
                        (target,),
                    )
                    target_character = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        INSERT INTO character_relationships (
                            character1_id, character2_id, relationship_type,
                            emotional_valence, dynamic, recent_events, history
                        ) VALUES (%s, %s, 'rival', '+0|neutral',
                                  'Competing interests.', '', '')
                        """,
                        (actor_character, target_character),
                    )
                    anchor = _insert_prologue_chunk(cur)
                    _ensure_prologue_metadata(cur, prologue_chunk_id=anchor)
            yield dbname, anchor, actor, target
        finally:
            VALID_DBNAMES.discard(dbname)


def _history_event(event_type: str) -> RetrogradeExpansionEventPlan:
    return RetrogradeExpansionEventPlan(
        event_ref="realignment_contract",
        seed_ids=["realignment_seed"],
        event_type=event_type,
        summary="Their rival institutions have changed sides.",
        chronology="opening_pressure",
        participants=[
            {"entity_ref": "Mara", "entity_kind": "character", "role": "actor"},
            {"entity_ref": "Vale", "entity_kind": "character", "role": "target"},
        ],
        magnitude=0.4,
    )


@pytest.mark.parametrize("event_type", sorted(EXOGENOUS_EVENT_PRODUCERS))
def test_registered_retrograde_source_reaches_retained_gate(
    event_source_db: tuple[str, int, int, int], event_type: str
) -> None:
    """Registered history is authored, hydrated, and heard by the actual gate."""

    dbname, anchor, actor, target = event_source_db
    (contract,) = EXOGENOUS_EVENT_PRODUCERS[event_type]
    vocabulary = enumerate_seed_eligible_vocabulary(dbname=dbname)
    assert event_type in vocabulary["event_types"]

    # Isolate this registered type within the real R3 sampler and retain the
    # shipped exclusion policy: it must remain an eligible backstory source.
    vocabulary = {**vocabulary, "event_types": [event_type]}
    graph_settings = load_settings().orrery.retrograde.graph.model_copy(
        update={"edge_kind_weights": {"event": 1.0}}
    )
    graph = build_candidate_graph(
        candidate_scaffolds={"core_entities": [{"kind": "character", "name": "Mara"}]},
        vocabulary=vocabulary,
        weird={"raw": 0.0},
        generate_candidates=1,
        rng_seed_material="event-source-contract",
        graph_settings=graph_settings,
    )
    assert any(edge["edge_type"] == event_type for edge in graph["dangling_edges"])

    # Resolve the registered entrypoint itself so a renamed/deleted writer
    # cannot leave a passing audit with only a stale string as evidence.
    module_name, symbol = contract.entrypoint.rsplit(".", 1)
    write_event = getattr(import_module(module_name), symbol)
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            kwargs: dict[str, Any] = {
                "dry_run": False,
                "prologue_chunk_id": anchor,
                "entity_index": _load_entity_index(cur),
                "event_types": _load_event_types(cur),
                "event_source_available": True,
                "creatable_refs": frozenset(),
            }
            # A named writer is not permission to bypass the slot vocabulary.
            blocked = write_event(cur, _history_event("unregistered_event"), **kwargs)
            assert blocked["status"] == "blocked"
            event = write_event(cur, _history_event(event_type), **kwargs)
            assert event["status"] == "inserted"
            cur.execute(
                "SELECT source::text, payload->>'source' "
                "FROM world_events WHERE id = %s",
                (event["world_event_id"],),
            )
            assert cur.fetchone() == (contract.source_kind, contract.source_kind)
            cur.execute(
                "SELECT entity_id FROM world_event_entities WHERE event_id = %s",
                (event["world_event_id"],),
            )
            assert {row[0] for row in cur.fetchall()} == {actor, target}

    engine = create_engine(sqlalchemy_url(dbname))
    try:
        with engine.connect() as session:
            state = hydrate_world_state(
                session, anchor_chunk_id=anchor, window_chunks=30
            )
            bindings = {Slot.ACTOR: actor, Slot.TARGET: target}
            assert CONSULT_RIVAL.package_gate(state, bindings)
            assert not CONSULT_RIVAL.package_gate(
                replace(state, recent_events=()), bindings
            )
            assert not CONSULT_RIVAL.package_gate(
                replace(state, current_tick=anchor + 16), bindings
            )
            coverage = analyze_coverage(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_ids=[anchor],
                window_chunks=30,
                epoch_min_world_times=10,
            )
            assert event_type not in coverage["dead_gate_arms"]
    finally:
        engine.dispose()

    entry = build_catalog(BUILTIN_TEMPLATES)["event_map"][event_type]
    assert entry["consumed_by_gate"] == [CONSULT_RIVAL.id]
    assert entry["exogenous_producers"][0]["producer"] == contract.producer

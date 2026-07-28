"""Real-PostgreSQL regression for issue #601 materialization enforcement."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import uuid
from typing import Any, Iterator

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
    RetrogradeExpansionValidationError,
)
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_persistence import (
    build_retrograde_persistence_plan,
)
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)

pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def disposable_cursor() -> Iterator[Any]:
    """Yield a current-template clone and remove it after the regression."""

    dbname = f"nexus_test_issue_601_{uuid.uuid4().hex[:12]}"
    admin = None
    conn = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        conn = _connect(dbname)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            migration = (
                Path(__file__).parents[2]
                / "migrations"
                / "097_trait_cold_start_relationship_constraints.sql"
            )
            cur.execute(migration.read_text())
            cur.execute(
                "UPDATE global_variables SET base_timestamp = %s WHERE id = TRUE",
                ("2026-05-14T10:48:00+00:00",),
            )
            yield cur
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def test_persistence_keeps_dispute_event_without_enemy_row(
    disposable_cursor: Any,
) -> None:
    """The real persistence path retains Voss's event and mints no PC enemy row."""

    cur = disposable_cursor
    vocabulary = enumerate_seed_eligible_vocabulary()
    event_type = (
        "backstory_secret_authored"
        if "backstory_secret_authored" in vocabulary["event_types"]
        else vocabulary["event_types"][0]
    )
    packet = _packet(vocabulary)
    seed_response = _seed_response(vocabulary, event_type=event_type)
    violating = _expansion(vocabulary, event_type=event_type, include_enemy=True)

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="cold_start_relationships_forbidden.*enemy.*Jules Mercer.*enemies",
    ):
        build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=violating,
            slot=3,
            dbname="disposable_issue_601",
            dry_run=False,
            create_missing_entities=True,
            summaries_enabled=False,
        )

    repaired = copy.deepcopy(violating)
    repaired["relationship_plan"] = []
    manifest = build_retrograde_persistence_plan(
        cur,
        packet=packet,
        seed_candidate_response=seed_response,
        expansion_plan_payload=repaired,
        slot=3,
        dbname="disposable_issue_601",
        dry_run=False,
        create_missing_entities=True,
        summaries_enabled=False,
    )

    cur.execute(
        """
        SELECT count(*) AS count
        FROM character_relationships cr
        JOIN characters subject ON subject.id = cr.character1_id
        JOIN characters object_character ON object_character.id = cr.character2_id
        WHERE cr.relationship_type = 'enemy'
          AND (subject.name = 'Jules Mercer' OR object_character.name = 'Jules Mercer')
        """
    )
    assert cur.fetchone()["count"] == 0
    cur.execute(
        """
        SELECT payload ->> 'retrograde_event_ref' AS event_ref
        FROM world_events
        WHERE source = 'retrograde'
          AND payload ->> 'retrograde_event_ref' = 'e_voss_practice_dispute'
        """
    )
    assert cur.fetchone()["event_ref"] == "e_voss_practice_dispute"
    assert manifest["counters"]["events_inserted"] == 1
    assert manifest["counters"]["relationships_inserted"] == 0


def _packet(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    scaffolds = {
        "core_entities": [
            {
                "kind": "character",
                "role": "protagonist",
                "name": "Jules Mercer",
                "summary": "A court reporter who begins with no personal nemesis.",
            },
            {
                "kind": "character",
                "role": "seed_npc",
                "name": "Della Voss",
                "summary": "A deceased accessibility auditor with sealed records.",
            },
        ],
        "named_seed_npcs": [],
        "pressure_axes": [],
        "trait_hooks": {
            "selected_traits": ["status", "enemies", "obligations"],
            "rationales": {
                "enemies": "No preexisting personal nemesis; opposition arises in play."
            },
            "constraints": [
                {"trait": "enemies", "cold_start_relationships": "forbidden"}
            ],
        },
    }
    request = build_seed_generation_request(
        candidate_scaffolds=scaffolds,
        vocabulary=vocabulary,
        weird={"level": "low", "genre": "thriller", "raw_midpoint": 0.2},
    )
    request["candidate_graph"] = {}
    return {
        "candidate_scaffolds": scaffolds,
        "seed_generation_request": request,
        "seed_eligible_vocabulary": vocabulary,
    }


def _seed_response(
    vocabulary: SeedEligibleVocabulary, *, event_type: str
) -> dict[str, Any]:
    return {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "candidates": [
            {
                "seed_id": "seed_paper_enemy",
                "summary": "A sealed dispute survives Della Voss's death.",
                "origin_friction": "medium",
                "present_leaf_anchor": "The record may be discovered during play.",
                "coverage_functions": ["hidden_truth", "trait_bound_hook"],
                "mechanical_hints": {
                    "events": [
                        {
                            "event_ref": "e_voss_practice_dispute",
                            "event_type": event_type,
                            "summary": "Voss challenged a practice Jules later inherited.",
                            "participating_entities": ["Jules Mercer", "Della Voss"],
                        }
                    ],
                    "single_entity_tags": [],
                    "pair_tags": [],
                    "relationships": [],
                },
                "defer_or_reject_if": [],
                "claimed_edges": [],
            }
        ],
        "selected_seed_ids": ["seed_paper_enemy"],
        "rejected_seed_ids": [],
    }


def _expansion(
    vocabulary: SeedEligibleVocabulary,
    *,
    event_type: str,
    include_enemy: bool,
) -> dict[str, Any]:
    relationships = []
    if include_enemy:
        relationships.append(
            {
                "subject_ref": "Jules Mercer",
                "subject_kind": "character",
                "relationship_type": "enemy",
                "object_ref": "Della Voss",
                "object_kind": "character",
                "source_event_ref": "e_voss_practice_dispute",
                "rationale": "The sealed dispute leaves a paper trail.",
            }
        )
    return {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "selected_seed_ids": ["seed_paper_enemy"],
        "event_plan": [
            {
                "event_ref": "e_voss_practice_dispute",
                "seed_ids": ["seed_paper_enemy"],
                "event_type": event_type,
                "summary": (
                    "A sealed professional dispute states that Della Voss "
                    "challenged a transcript practice later inherited by Jules "
                    "Mercer without their knowledge."
                ),
                "chronology": "recent_past",
                "participants": [
                    {
                        "entity_ref": "Della Voss",
                        "entity_kind": "character",
                        "role": "actor",
                    },
                    {
                        "entity_ref": "Jules Mercer",
                        "entity_kind": "character",
                        "role": "target",
                    },
                ],
                "location_ref": None,
                "changed_fields": ["sealed_record"],
                "magnitude": 0.2,
                "payload": {
                    "record_status": (
                        "Paper-trail conflict only, not a present adversary."
                    )
                },
            }
        ],
        "entity_tag_plan": [],
        "pair_tag_plan": [],
        "relationship_plan": relationships,
        "death_plan": [],
        "project_plan": [],
        "thread_plan": [
            {
                "seed_id": "seed_paper_enemy",
                "status": "woven",
                "event_refs": ["e_voss_practice_dispute"],
                "present_leaf_anchor": "The sealed record may surface during play.",
            }
        ],
        "coverage_notes": ["The event preserves texture without an enemy row."],
        "commit_readiness": {
            "writes": "none",
            "planned_source": "retrograde",
            "blocked_by": [
                "pre_game_tick_chunk_id",
                "event_source_kind_retrograde",
            ],
            "explanation": "Runtime fills the canonical anchor.",
        },
    }

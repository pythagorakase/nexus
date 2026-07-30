"""Real cache-to-transition PostgreSQL regressions for issue #601."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional
import uuid

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
    RetrogradeExpansionValidationError,
    validate_expansion_plan,
)
from nexus.agents.orrery.retrograde_packet import build_retrograde_dry_run_packet
from nexus.agents.orrery.retrograde_persistence import (
    build_retrograde_persistence_plan,
)
from nexus.agents.orrery.retrograde_project_dependencies import (
    load_project_start_relationships,
)
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)
from nexus.api.new_story_cache import read_cache, write_cache
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_flow import build_transition_data_from_cache
from nexus.api.db_pool import close_all_pools
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.api.trait_compiler_schemas import TraitCompileInputs
from nexus.api.trait_input_derivation import ensure_trait_compile_inputs
from nexus.config import load_settings

pytestmark = pytest.mark.requires_postgres

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "slot3_midnight_qa_wizard_cache.json"
)


def _connect(dbname: str, *, dict_cursor: bool = False) -> Any:
    kwargs: dict[str, Any] = {
        "dbname": dbname,
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }
    if dict_cursor:
        kwargs["cursor_factory"] = RealDictCursor
    return psycopg2.connect(**kwargs)


@pytest.fixture()
def disposable_dbname() -> Iterator[str]:
    """Yield a current-template clone and remove it after the regression."""

    dbname = f"qa640_issue601_{uuid.uuid4().hex[:12]}"
    admin: Any = None
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
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                migration = (
                    Path(__file__).parents[2]
                    / "migrations"
                    / "097_trait_cold_start_relationship_constraints.sql"
                )
                cur.execute(migration.read_text())
                # Fixture invariant: production persists the canonical clock
                # before any character INSERT fires need-state initialization.
                cur.execute(
                    """
                    INSERT INTO global_variables (
                        id, new_story, base_timestamp
                    ) VALUES (
                        true, true, '2026-05-14T10:48:00+00:00'::timestamptz
                    )
                    ON CONFLICT (id) DO UPDATE
                    SET base_timestamp = EXCLUDED.base_timestamp
                    """
                )
        VALID_DBNAMES.add(dbname)
        yield dbname
    finally:
        close_all_pools()
        VALID_DBNAMES.discard(dbname)
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


def _fixture_payload() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


def _hydrate_fixture(
    dbname: str,
    *,
    fixture: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Write the checked-in artifact through normalized cache persistence."""

    payload = copy.deepcopy(dict(fixture or _fixture_payload()))
    character = payload["character"]
    seed = payload["seed"]
    write_cache(
        thread_id="issue_601_postgres_regression",
        setting_draft=payload["setting"],
        character_draft=character,
        selected_seed=seed["story_seed"],
        layer_draft=seed["layer"],
        zone_draft=seed["zone"],
        initial_location=seed["initial_location"],
        base_timestamp="2026-05-14T10:48:00+00:00",
        target_slot=3,
        dbname=dbname,
    )
    cache = read_cache(dbname)
    assert cache is not None
    assert cache.current_phase() == "ready"
    return cache


def _build_transition_and_packet(
    dbname: str,
    cache: Any,
    *,
    trait_inputs: TraitCompileInputs,
) -> tuple[Any, dict[str, Any], SeedEligibleVocabulary]:
    """Use production hydration, typed-input gating, and packet construction."""

    transition = build_transition_data_from_cache(cache)
    transition.character.trait_compile_inputs = trait_inputs
    ensure_trait_compile_inputs(
        transition,
        slot=3,
        model_name="@provider.unused_existing_input",
        max_tokens=1,
        retries=1,
    )
    vocabulary = enumerate_seed_eligible_vocabulary(dbname=dbname)
    constrained_inputs = transition.character.trait_compile_inputs
    assert constrained_inputs is not None
    packet = build_retrograde_dry_run_packet(
        slot=3,
        dbname=dbname,
        cache=cache,
        vocabulary=vocabulary,
        settings=load_settings(),
        weird_level="low",
        trait_compile_inputs=constrained_inputs.model_dump(
            mode="json",
            exclude_none=True,
        ),
    )
    return transition, packet, vocabulary


def _event_type(vocabulary: SeedEligibleVocabulary) -> str:
    preferred = "backstory_secret_authored"
    return (
        preferred
        if preferred in vocabulary["event_types"]
        else vocabulary["event_types"][0]
    )


def _seed_response(
    packet: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
) -> dict[str, Any]:
    request = packet["seed_generation_request"]
    dangling_edges = request["candidate_graph"]["dangling_edges"]
    claimed_edges: list[dict[str, Any]] = []
    if dangling_edges:
        edge = dangling_edges[0]
        endpoint_name = {
            "character": "Della Voss",
            "faction": "Dunlow Court Registry",
            "place": "Courthouse Archive Annex",
        }[edge["open_endpoint_kind"]]
        claimed_edges.append(
            {
                "edge_id": edge["edge_id"],
                "open_endpoint_name": endpoint_name,
                "open_endpoint_kind": edge["open_endpoint_kind"],
            }
        )
    event_type = _event_type(vocabulary)
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
                            "summary": "Voss challenged a practice Jules inherited.",
                            "participating_entities": [
                                "Jules Mercer",
                                "Della Voss",
                            ],
                        }
                    ],
                    "single_entity_tags": [],
                    "pair_tags": [],
                    "relationships": [],
                },
                "defer_or_reject_if": [],
                "claimed_edges": claimed_edges,
            }
        ],
        "selected_seed_ids": ["seed_paper_enemy"],
        "rejected_seed_ids": [],
    }


def _expansion(
    vocabulary: SeedEligibleVocabulary,
    *,
    relationship_type: Optional[str] = None,
    pair_tag: Optional[str] = None,
    protagonist_ref: str = "Jules Mercer",
) -> dict[str, Any]:
    event_type = _event_type(vocabulary)
    relationship_plan: list[dict[str, Any]] = []
    if relationship_type is not None:
        relationship_plan.append(
            {
                "subject_ref": protagonist_ref,
                "subject_kind": "character",
                "relationship_type": relationship_type,
                "object_ref": "Della Voss",
                "object_kind": "character",
                "source_event_ref": "e_voss_practice_dispute",
                "rationale": "The sealed dispute leaves a paper trail.",
            }
        )
    pair_tag_plan: list[dict[str, Any]] = []
    if pair_tag is not None:
        pair_tag_plan.append(
            {
                "subject_ref": "Della Voss",
                "subject_kind": "character",
                "tag": pair_tag,
                "object_ref": protagonist_ref,
                "object_kind": "character",
                "source_event_ref": "e_voss_practice_dispute",
                "rationale": "The mechanical edge would predate play.",
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
                        "entity_ref": protagonist_ref,
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
        "pair_tag_plan": pair_tag_plan,
        "relationship_plan": relationship_plan,
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


def test_real_cache_packet_and_transition_keep_event_without_adversarial_rows(
    disposable_dbname: str,
) -> None:
    """The live QA event persists while all enemy-class mechanics are refused."""

    cache = _hydrate_fixture(disposable_dbname)
    transition, packet, vocabulary = _build_transition_and_packet(
        disposable_dbname,
        cache,
        trait_inputs=TraitCompileInputs.model_validate(
            {"enemies": {"targets": [{"name": "Della Voss"}]}}
        ),
    )
    constraints = packet["seed_generation_request"]["trait_constraints"]
    enemy_constraint = next(row for row in constraints if row["trait"] == "enemies")
    assert enemy_constraint["blocked_relationship_types"] == [
        "captor",
        "enemy",
        "rival",
    ]
    assert enemy_constraint["blocked_pair_tags"] == ["hunting"]
    assert (
        transition.character.trait_compile_inputs.enemies is None
        if transition.character.trait_compile_inputs is not None
        else False
    )

    seed_response = _seed_response(packet, vocabulary)
    for relationship_type in ("enemy", "rival", "captor"):
        with pytest.raises(
            RetrogradeExpansionValidationError,
            match=(
                "cold_start_relationships_forbidden.*" f"{relationship_type}.*enemies"
            ),
        ):
            validate_expansion_plan(
                payload=_expansion(
                    vocabulary,
                    relationship_type=relationship_type,
                ),
                packet=packet,
                seed_candidate_response=seed_response,
            )
    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="cold_start_relationships_forbidden.*hunting.*enemies",
    ):
        validate_expansion_plan(
            payload=_expansion(vocabulary, pair_tag="hunting"),
            packet=packet,
            seed_candidate_response=seed_response,
        )
    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="protagonist_duplicate_stub_forbidden.*jules",
    ):
        validate_expansion_plan(
            payload=_expansion(
                vocabulary,
                relationship_type="rival",
                protagonist_ref="Jules",
            ),
            packet=packet,
            seed_candidate_response=seed_response,
        )

    repaired = _expansion(vocabulary)
    validated = validate_expansion_plan(
        payload=repaired,
        packet=packet,
        seed_candidate_response=seed_response,
    )
    assert validated.event_plan[0].event_ref == "e_voss_practice_dispute"
    assert validated.relationship_plan == []
    assert validated.pair_tag_plan == []

    manifest_holder: dict[str, Any] = {}

    def persist(cur: Any) -> None:
        manifest_holder["manifest"] = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=repaired,
            slot=3,
            dbname=disposable_dbname,
            dry_run=False,
            create_missing_entities=True,
            summaries_enabled=False,
        )

    NewStoryDatabaseMapper(dbname=disposable_dbname).perform_transition(
        transition,
        in_transaction=persist,
    )
    manifest = manifest_holder["manifest"]

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_id
                FROM characters
                WHERE name = 'Jules Mercer'
                """
            )
            protagonist = cur.fetchone()
            assert protagonist is not None
            cur.execute(
                """
                SELECT count(*) AS count
                FROM character_relationships cr
                WHERE (cr.character1_id = %s OR cr.character2_id = %s)
                  AND cr.relationship_type IN ('enemy', 'rival', 'captor')
                """,
                (protagonist["id"], protagonist["id"]),
            )
            assert cur.fetchone()["count"] == 0
            cur.execute(
                """
                SELECT count(*) AS count
                FROM entity_pair_tags ept
                JOIN pair_tags pt ON pt.id = ept.pair_tag_id
                WHERE pt.tag = 'hunting'
                  AND (
                      ept.subject_entity_id = %s
                      OR ept.object_entity_id = %s
                  )
                  AND ept.cleared_at IS NULL
                """,
                (protagonist["entity_id"], protagonist["entity_id"]),
            )
            assert cur.fetchone()["count"] == 0
            cur.execute(
                """
                SELECT payload ->> 'retrograde_event_ref' AS event_ref
                FROM world_events
                WHERE source = 'retrograde'
                  AND payload ->> 'retrograde_event_ref'
                      = 'e_voss_practice_dispute'
                """
            )
            assert cur.fetchone()["event_ref"] == "e_voss_practice_dispute"
            cur.execute(
                """
                SELECT extra_data -> 'trait_compile_result'
                       -> 'prose_only_remainders' AS remainders
                FROM characters
                WHERE id = %s
                """,
                (protagonist["id"],),
            )
            remainders = cur.fetchone()["remainders"]
            enemy_remainder = next(
                row for row in remainders if row["trait"] == "enemies"
            )
            assert (
                enemy_remainder["reason_code"] == "cold_start_relationships_forbidden"
            )

    assert manifest["counters"]["events_inserted"] == 1
    assert manifest["counters"]["relationships_inserted"] == 0
    assert manifest["counters"]["pair_tags_inserted"] == 0


def test_real_cache_compiler_gate_suppresses_all_named_target_materialization(
    disposable_dbname: str,
) -> None:
    """Forbidden typed inputs create only #605-style structured remainders."""

    fixture = _fixture_payload()
    selected = ["patron", "dependents", "obligations"]
    rationales = {
        "patron": "No patron relationship may predate the opening scene.",
        "dependents": "No dependent relationship may predate the opening scene.",
        "obligations": "No obligation relationship may predate the opening scene.",
    }
    fixture["character"]["concept"]["suggested_traits"] = selected
    fixture["character"]["concept"]["trait_rationales"] = rationales
    fixture["character"]["trait_selection"] = {
        "selected_traits": selected,
        "trait_rationales": rationales,
        "suggested_by_llm": selected,
        "trait_constraints": [
            {"trait": trait, "cold_start_relationships": "forbidden"}
            for trait in selected
        ],
    }
    cache = _hydrate_fixture(disposable_dbname, fixture=fixture)
    transition, packet, _vocabulary = _build_transition_and_packet(
        disposable_dbname,
        cache,
        trait_inputs=TraitCompileInputs.model_validate(
            {
                "patron": {
                    "name": "Doctor Voss",
                    "functions": ["mentors", "protects"],
                },
                "dependents": {"targets": [{"name": "Juno Reyes"}]},
                "obligations": {
                    "targets": [
                        {
                            "counterparty_kind": "character",
                            "name": "Magistrate Hale",
                        }
                    ]
                },
            }
        ),
    )
    assert {
        row["trait"] for row in packet["seed_generation_request"]["trait_constraints"]
    } == set(selected)
    constrained_inputs = transition.character.trait_compile_inputs
    assert constrained_inputs is not None
    assert constrained_inputs.patron is None
    assert constrained_inputs.dependents is None
    assert constrained_inputs.obligations is None
    assert constrained_inputs.suppressed_cold_start_relationship_traits == sorted(
        selected
    )

    NewStoryDatabaseMapper(dbname=disposable_dbname).perform_transition(transition)

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS count
                FROM characters
                WHERE name IN ('Doctor Voss', 'Juno Reyes', 'Magistrate Hale')
                """
            )
            assert cur.fetchone()["count"] == 0
            cur.execute("SELECT count(*) AS count FROM character_relationships")
            assert cur.fetchone()["count"] == 0
            cur.execute("SELECT count(*) AS count FROM entity_pair_tags")
            assert cur.fetchone()["count"] == 0
            cur.execute(
                """
                SELECT extra_data -> 'trait_compile_result'
                       -> 'prose_only_remainders' AS remainders
                FROM characters
                WHERE name = 'Jules Mercer'
                """
            )
            remainders = cur.fetchone()["remainders"]
            assert {(row["trait"], row["reason_code"]) for row in remainders} == {
                ("patron", "cold_start_relationships_forbidden"),
                ("dependents", "cold_start_relationships_forbidden"),
                ("obligations", "cold_start_relationships_forbidden"),
            }


def test_persistence_refuses_database_alias_stub_even_without_packet_alias(
    disposable_dbname: str,
) -> None:
    """The persistence wall reads character_aliases before staging stubs."""

    cache = _hydrate_fixture(disposable_dbname)
    transition, packet, vocabulary = _build_transition_and_packet(
        disposable_dbname,
        cache,
        trait_inputs=TraitCompileInputs.model_validate(
            {
                "enemies": {"targets": [{"name": "Della Voss"}]},
                "status": {
                    "level": "junior",
                    "scope_faction_name": "Dunlow County Circuit Court",
                },
            }
        ),
    )
    seed_response = _seed_response(packet, vocabulary)
    alias_expansion = _expansion(vocabulary, protagonist_ref="J.M.")
    validate_expansion_plan(
        payload=alias_expansion,
        packet=packet,
        seed_candidate_response=seed_response,
    )

    def persist(cur: Any) -> None:
        cur.execute("SELECT user_character FROM global_variables WHERE id = TRUE")
        protagonist_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO character_aliases (character_id, alias) VALUES (%s, %s)",
            (protagonist_id, "J.M."),
        )
        build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=alias_expansion,
            slot=3,
            dbname=disposable_dbname,
            dry_run=False,
            create_missing_entities=True,
            summaries_enabled=False,
        )

    with pytest.raises(ValueError, match="protagonist_duplicate_stub_forbidden"):
        NewStoryDatabaseMapper(dbname=disposable_dbname).perform_transition(
            transition,
            in_transaction=persist,
        )

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS count FROM characters WHERE name = 'J.M.'")
            assert cur.fetchone()["count"] == 0


def test_seek_redemption_dependency_is_repaired_before_mapper_transaction(
    disposable_dbname: str,
) -> None:
    """A real cache path enforces direction/threshold, then persists atomically."""

    cache = _hydrate_fixture(disposable_dbname)
    transition, packet, vocabulary = _build_transition_and_packet(
        disposable_dbname,
        cache,
        trait_inputs=TraitCompileInputs.model_validate({}),
    )

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO characters (name, summary)
                VALUES
                    ('Existing Actor', 'A preexisting runtime character.'),
                    ('Existing Target', 'A preexisting wronged character.')
                RETURNING entity_id, id, name
                """
            )
            actor, target = cur.fetchall()
            cur.execute(
                """
                DELETE FROM character_relationships
                WHERE character1_id IN (%s, %s)
                  AND character2_id IN (%s, %s)
                """,
                (actor["id"], target["id"], actor["id"], target["id"]),
            )
            cur.execute(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history
                ) VALUES (%s, %s, 'rival', '-1|wary', '', '', '')
                """,
                (target["id"], actor["id"]),
            )
            packet["project_start_relationships"] = load_project_start_relationships(
                cur,
                object_entity_id=int(actor["entity_id"]),
            )

    seed_response, expansion = _redemption_contract(
        packet,
        vocabulary,
        actor_ref=str(actor["name"]),
        target_ref=str(target["name"]),
    )
    validated = validate_expansion_plan(
        payload=expansion,
        packet=packet,
        seed_candidate_response=seed_response,
    )
    assert validated.project_plan[0].project_type == "seek_redemption"

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE character_relationships
                SET emotional_valence = '0|neutral'
                WHERE character1_id = %s AND character2_id = %s
                """,
                (target["id"], actor["id"]),
            )
            packet["project_start_relationships"] = load_project_start_relationships(
                cur,
                object_entity_id=int(actor["entity_id"]),
            )
    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="seed 'seed_01' seek_redemption.*TARGET->ACTOR wary-or-worse",
    ):
        validate_expansion_plan(
            payload=expansion,
            packet=packet,
            seed_candidate_response=seed_response,
        )

    packet["project_start_relationships"] = [
        {
            "subject_ref": str(actor["name"]),
            "object_ref": str(target["name"]),
            "emotional_valence": "-1|wary",
        }
    ]
    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="seed 'seed_01' seek_redemption.*TARGET->ACTOR wary-or-worse",
    ):
        validate_expansion_plan(
            payload=expansion,
            packet=packet,
            seed_candidate_response=seed_response,
        )

    unchanged_cache = read_cache(disposable_dbname)
    assert unchanged_cache is not None
    assert unchanged_cache.current_phase() == "ready"

    packet["project_start_relationships"] = []
    seed_response, expansion = _redemption_contract(
        packet,
        vocabulary,
        actor_ref="Redemption Actor",
        target_ref="Wronged Target",
        planned_wrong=True,
    )
    validate_expansion_plan(
        payload=expansion,
        packet=packet,
        seed_candidate_response=seed_response,
    )

    manifest_holder: dict[str, Any] = {}

    def persist(cur: Any) -> None:
        manifest_holder["manifest"] = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=3,
            dbname=disposable_dbname,
            dry_run=False,
            create_missing_entities=True,
            summaries_enabled=False,
            project_seeding_enabled=True,
            project_settings=load_settings().orrery.projects,
        )

    NewStoryDatabaseMapper(dbname=disposable_dbname).perform_transition(
        transition,
        in_transaction=persist,
    )

    with _connect(disposable_dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source.name AS subject_ref,
                       target.name AS object_ref,
                       relationship.emotional_valence::text AS emotional_valence
                FROM character_relationships relationship
                JOIN characters source ON source.id = relationship.character1_id
                JOIN characters target ON target.id = relationship.character2_id
                WHERE source.name = 'Wronged Target'
                  AND target.name = 'Redemption Actor'
                """
            )
            assert cur.fetchone() == {
                "subject_ref": "Wronged Target",
                "object_ref": "Redemption Actor",
                "emotional_valence": "-3|resentful",
            }
            cur.execute(
                """
                SELECT project_type, status, stage
                FROM character_project_states project
                JOIN characters actor ON actor.entity_id = project.character_entity_id
                WHERE actor.name = 'Redemption Actor'
                """
            )
            assert cur.fetchone() == {
                "project_type": "seek_redemption",
                "status": "active",
                "stage": "owning_the_wrong",
            }

    manifest = manifest_holder["manifest"]
    assert manifest["counters"]["relationships_inserted"] == 1
    assert manifest["counters"]["projects_inserted"] == 1


def _redemption_contract(
    packet: Mapping[str, Any],
    vocabulary: SeedEligibleVocabulary,
    *,
    actor_ref: str,
    target_ref: str,
    planned_wrong: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build model outputs around the production-generated packet."""

    seed_response = _seed_response(packet, vocabulary)
    old_seed_id = seed_response["candidates"][0]["seed_id"]
    candidate = seed_response["candidates"][0]
    candidate["seed_id"] = "seed_01"
    candidate["coverage_functions"] = ["unresolved_ledger"]
    candidate["project_intent"] = {
        "project_type": "seek_redemption",
        "target_ref": target_ref,
        "rationale": "The actor must answer for an old wrong.",
    }
    seed_response["selected_seed_ids"] = ["seed_01"]

    expansion = _expansion(vocabulary)
    expansion["selected_seed_ids"] = ["seed_01"]
    expansion["event_plan"][0]["seed_ids"] = ["seed_01"]
    expansion["thread_plan"][0]["seed_id"] = "seed_01"
    expansion["project_plan"] = [
        {
            "seed_id": "seed_01",
            "project_type": "seek_redemption",
            "actor_ref": actor_ref,
            "target_ref": target_ref,
            "rationale": "Begin by owning the wrong.",
        }
    ]
    if planned_wrong:
        expansion["relationship_plan"] = [
            {
                "subject_ref": target_ref,
                "subject_kind": "character",
                "relationship_type": "enemy",
                "object_ref": actor_ref,
                "object_kind": "character",
                "source_event_ref": "e_voss_practice_dispute",
                "rationale": "The target remains resentful over the old wrong.",
            }
        ]
    assert old_seed_id != candidate["seed_id"]
    return seed_response, expansion

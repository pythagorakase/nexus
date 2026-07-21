"""Real-PostgreSQL contract coverage for migration 088."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest

from nexus.api.new_story_schemas import CharacterSheet, CharacterTrait
from nexus.api.slot_utils import get_slot_db_url
from nexus.api.trait_compiler import (
    apply_character_trait_compilation,
    compile_character_traits,
)
from nexus.api.trait_compiler_schemas import (
    RelationshipTargetInput,
    RelationshipTraitInput,
    TraitCompileInputs,
)


pytestmark = pytest.mark.requires_postgres

MIGRATION_SQL = (
    Path(__file__).parents[2] / "migrations" / "088_valence_float_canonical.sql"
).read_text()

CANONICAL_LITERALS = {
    "+5|devoted": 5,
    "+4|admiring": 4,
    "+3|trusting": 3,
    "+2|friendly": 2,
    "+1|favorable": 1,
    "0|neutral": 0,
    "-1|wary": -1,
    "-2|disapproving": -2,
    "-3|resentful": -3,
    "-4|hostile": -4,
    "-5|hateful": -5,
}
RETIRED_LITERALS = {
    "+2|deferential": (2, "+2|friendly"),
    "+3|devoted": (3, "+3|trusting"),
    "-1|beholden": (-1, "-1|wary"),
}


def _schema_setup_sql() -> str:
    """Return the migration-087 relationship surface needed by migration 088."""

    return """
        CREATE TABLE characters (
            id bigint PRIMARY KEY,
            entity_id bigint UNIQUE NOT NULL
        );
        CREATE TABLE factions (
            id bigint PRIMARY KEY,
            entity_id bigint UNIQUE NOT NULL
        );
        CREATE TABLE character_relationships (
            character1_id bigint NOT NULL REFERENCES characters(id),
            character2_id bigint NOT NULL REFERENCES characters(id),
            relationship_type varchar(50) NOT NULL,
            emotional_valence varchar(50) NOT NULL,
            dynamic text NOT NULL,
            recent_events text NOT NULL,
            history text NOT NULL,
            extra_data jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (character1_id, character2_id)
        );
        CREATE TABLE faction_relationships (
            faction1_id bigint NOT NULL REFERENCES factions(id),
            faction2_id bigint NOT NULL REFERENCES factions(id),
            relationship_type varchar(50) NOT NULL,
            current_status text NOT NULL,
            history text NOT NULL,
            extra_data jsonb,
            PRIMARY KEY (faction1_id, faction2_id)
        );
        CREATE TABLE faction_character_relationships (
            faction_id bigint NOT NULL REFERENCES factions(id),
            character_id bigint NOT NULL REFERENCES characters(id),
            role varchar(50) NOT NULL,
            current_status text NOT NULL,
            history text NOT NULL,
            extra_data jsonb,
            PRIMARY KEY (faction_id, character_id)
        );
        CREATE TABLE relationship_versions (
            id bigserial PRIMARY KEY,
            relationship_table text NOT NULL,
            operation text NOT NULL,
            old_row jsonb NOT NULL,
            source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE FUNCTION fn_version_relationship_row()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO relationship_versions (
                relationship_table, operation, old_row
            ) VALUES (TG_TABLE_NAME, lower(TG_OP), to_jsonb(OLD));
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_version_character_relationships
            BEFORE UPDATE OR DELETE ON character_relationships
            FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();

        CREATE VIEW entity_relationships_v AS
            SELECT
                c1.entity_id AS source_entity_id,
                c2.entity_id AS target_entity_id,
                'character'::text AS relationship_scope,
                cr.relationship_type::text AS relationship_type,
                cr.emotional_valence::text AS valence,
                cr.dynamic,
                cr.recent_events,
                cr.history,
                cr.extra_data,
                CASE cr.emotional_valence::text
                    WHEN '+5|devoted' THEN 5
                    WHEN '+4|admiring' THEN 4
                    WHEN '+3|trusting' THEN 3
                    WHEN '+2|friendly' THEN 2
                    WHEN '+1|favorable' THEN 1
                    WHEN '0|neutral' THEN 0
                    WHEN '-1|wary' THEN -1
                    WHEN '-2|disapproving' THEN -2
                    WHEN '-3|resentful' THEN -3
                    WHEN '-4|hostile' THEN -4
                    WHEN '-5|hateful' THEN -5
                    ELSE NULL
                END::integer AS valence_magnitude
            FROM character_relationships cr
            JOIN characters c1 ON c1.id = cr.character1_id
            JOIN characters c2 ON c2.id = cr.character2_id
        UNION ALL
            SELECT
                f1.entity_id, f2.entity_id, 'faction'::text,
                fr.relationship_type::text, NULL::text, fr.current_status,
                NULL::text, fr.history, fr.extra_data, NULL::integer
            FROM faction_relationships fr
            JOIN factions f1 ON f1.id = fr.faction1_id
            JOIN factions f2 ON f2.id = fr.faction2_id
        UNION ALL
            SELECT
                f.entity_id, c.entity_id, 'faction_character'::text,
                fcr.role::text, NULL::text, fcr.current_status,
                NULL::text, fcr.history, fcr.extra_data, NULL::integer
            FROM faction_character_relationships fcr
            JOIN factions f ON f.id = fcr.faction_id
            JOIN characters c ON c.id = fcr.character_id;
    """


@contextmanager
def _migration_087_schema(*, include_retired: bool) -> Iterator[Any]:
    """Build a rollback-only migration-087-shaped schema."""

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            schema = f"migration_088_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(_schema_setup_sql())
            cur.execute(
                "INSERT INTO characters (id, entity_id) "
                "SELECT value, value + 1000 FROM generate_series(1, 40) value"
            )
            cur.execute(
                "INSERT INTO factions (id, entity_id) VALUES (1, 2001), (2, 2002)"
            )
            literals = list(CANONICAL_LITERALS)
            if include_retired:
                literals.extend(RETIRED_LITERALS)
            for index, literal in enumerate(literals, start=1):
                cur.execute(
                    """
                    INSERT INTO character_relationships (
                        character1_id, character2_id, relationship_type,
                        emotional_valence, dynamic, recent_events, history,
                        extra_data
                    ) VALUES (%s, %s, 'fixture', %s, %s, 'none', 'fixture', '{}')
                    """,
                    (index * 2 - 1, index * 2, literal, literal),
                )
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture()
def migration_087_schema() -> Iterator[Any]:
    """Include canonical and retired literals for migration/trigger tests."""

    with _migration_087_schema(include_retired=True) as conn:
        yield conn


@pytest.fixture()
def canonical_parity_schema() -> Iterator[Any]:
    """Include exactly the eleven rows accepted by the pre-088 CASE view."""

    with _migration_087_schema(include_retired=False) as conn:
        yield conn


def _apply_migration(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(MIGRATION_SQL)


def _expected_float(rung: int) -> float:
    return float(Decimal(rung) / Decimal("5.5"))


def _legacy_valence_sheet(inputs: TraitCompileInputs) -> CharacterSheet:
    traits = [
        CharacterTrait(name=name, description=f"{name} test trait")
        for name in ("allies", "resources", "fame")
    ]
    return CharacterSheet(
        name="Migration 088 Trait Compiler",
        summary="Rollback-only test character.",
        appearance="Defined only for migration contract coverage.",
        background="Exercises the typed relationship writer in an isolated schema.",
        personality="Exacting about canonical response values.",
        wildcard_name="Boundary Witness",
        wildcard_description="Sees both sides of a trigger boundary.",
        trait_1=traits[0],
        trait_2=traits[1],
        trait_3=traits[2],
        trait_compile_inputs=inputs,
    )


def test_migration_088_backfills_and_canonicalizes_existing_rows(
    migration_087_schema: Any,
) -> None:
    """Canonical and retired labels enter through the amended 5.5 scale."""

    _apply_migration(migration_087_schema)
    expected = {
        **{literal: (rung, literal) for literal, rung in CANONICAL_LITERALS.items()},
        **RETIRED_LITERALS,
    }
    with migration_087_schema.cursor() as cur:
        cur.execute(
            "SELECT dynamic, emotional_valence, valence_current "
            "FROM character_relationships ORDER BY character1_id"
        )
        rows = cur.fetchall()
        assert len(rows) == len(expected)
        for authored, projected, current in rows:
            rung, canonical = expected[authored]
            assert projected == canonical
            assert float(current) == pytest.approx(_expected_float(rung))
            assert Decimal("-1") < current < Decimal("1")

        cur.execute(
            """
            SELECT count(*),
                   bool_and(old_row ? 'valence_current'),
                   bool_and(old_row -> 'valence_current' = 'null'::jsonb)
            FROM relationship_versions
            """
        )
        assert cur.fetchone() == (len(expected), True, True)

        cur.execute(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE tgrelid = 'character_relationships'::regclass
              AND NOT tgisinternal
            ORDER BY tgname
            """
        )
        assert [row[0] for row in cur] == [
            "trg_character_relationships_valence_boundary",
            "trg_version_character_relationships",
        ]


def test_migration_088_insert_without_float_derives_canonical_state(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history
            ) VALUES (31, 32, 'legacy', '+3|devoted', 'insert', 'none', 'test')
            RETURNING emotional_valence, valence_current
            """
        )
        literal, current = cur.fetchone()
        assert literal == "+3|trusting"
        assert float(current) == pytest.approx(_expected_float(3))


def test_trait_compiler_reports_trigger_canonicalized_valence(
    migration_087_schema: Any,
) -> None:
    """Typed legacy input reports the exact literal persisted by migration 088."""

    _apply_migration(migration_087_schema)
    inputs = TraitCompileInputs(
        allies=RelationshipTraitInput(
            targets=[
                RelationshipTargetInput(
                    character_id=32,
                    emotional_valence="+2|deferential",
                    dynamic="Legacy authored label.",
                )
            ]
        )
    )
    sheet = _legacy_valence_sheet(inputs)
    with migration_087_schema.cursor() as cur:
        audit = compile_character_traits(
            cur,
            character=sheet,
            character_id=31,
            character_entity_id=1031,
            dry_run=True,
        )
        result = apply_character_trait_compilation(
            cur,
            character=sheet,
            character_id=31,
            character_entity_id=1031,
        )
        cur.execute(
            "SELECT emotional_valence, valence_current "
            "FROM character_relationships "
            "WHERE character1_id = 31 AND character2_id = 32"
        )
        stored_literal, stored_current = cur.fetchone()

    assert audit.created_relationships[0].emotional_valence == "+2|friendly"
    assert result.created_relationships[0].emotional_valence == stored_literal
    assert stored_literal == "+2|friendly"
    assert float(stored_current) == pytest.approx(_expected_float(2))


def test_migration_088_authored_literal_update_rederives_float(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            """
            UPDATE character_relationships
            SET emotional_valence = '-1|beholden'
            WHERE character1_id = 1
            RETURNING emotional_valence, valence_current
            """
        )
        literal, current = cur.fetchone()
        assert literal == "-1|wary"
        assert float(current) == pytest.approx(_expected_float(-1))


def test_migration_088_float_update_reprojects_literal(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            """
            UPDATE character_relationships
            SET valence_current = 0.84
            WHERE character1_id = 1
            RETURNING emotional_valence, valence_current
            """
        )
        assert cur.fetchone() == ("+5|devoted", Decimal("0.84"))


def test_migration_088_same_literal_reassertion_preserves_intra_rung_float(
    migration_087_schema: Any,
) -> None:
    """Reasserting the projected literal must not re-center off-center drift."""

    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            "UPDATE character_relationships "
            "SET valence_current = 0.4 "
            "WHERE character1_id = 1"
        )
        cur.execute(
            """
            UPDATE character_relationships
            SET emotional_valence = '+2|friendly'
            WHERE character1_id = 1
            RETURNING emotional_valence, valence_current
            """
        )
        assert cur.fetchone() == ("+2|friendly", Decimal("0.4"))


def test_migration_088_float_wins_when_both_representations_change(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            """
            UPDATE character_relationships
            SET emotional_valence = '-5|hateful', valence_current = 0.4
            WHERE character1_id = 1
            RETURNING emotional_valence, valence_current
            """
        )
        assert cur.fetchone() == ("+2|friendly", Decimal("0.4"))


def test_migration_088_unparseable_literal_raises(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute("SAVEPOINT invalid_literal")
        with pytest.raises(
            psycopg2.errors.InvalidParameterValue,
            match="Unparseable emotional_valence",
        ):
            cur.execute(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history
                ) VALUES (31, 32, 'legacy', 'friendly', 'bad', 'none', 'test')
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_literal")


@pytest.mark.parametrize("endpoint", [Decimal("-1"), Decimal("1")])
def test_migration_088_check_rejects_open_interval_endpoints(
    migration_087_schema: Any, endpoint: Decimal
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute("SAVEPOINT invalid_endpoint")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, valence_current, dynamic,
                    recent_events, history
                ) VALUES (31, 32, 'float', '0|neutral', %s, 'bad', 'none', 'test')
                """,
                (endpoint,),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_endpoint")


def test_migration_088_round_trip_preserves_all_eleven_rungs(
    migration_087_schema: Any,
) -> None:
    _apply_migration(migration_087_schema)
    with migration_087_schema.cursor() as cur:
        cur.execute(
            """
            SELECT rung, round((rung::numeric / 5.5) * 5.5)::integer
            FROM generate_series(-5, 5) rung
            ORDER BY rung
            """
        )
        assert cur.fetchall() == [(rung, rung) for rung in range(-5, 6)]


def test_migration_088_preserves_trust_hydration_for_canonical_rows(
    canonical_parity_schema: Any,
) -> None:
    """Every row in this fixture has identical pre/post ladder magnitude."""

    with canonical_parity_schema.cursor() as cur:
        cur.execute(
            """
            SELECT source_entity_id, target_entity_id, valence_magnitude
            FROM entity_relationships_v
            ORDER BY source_entity_id, target_entity_id
            """
        )
        pre_088 = cur.fetchall()
        assert [row[2] for row in pre_088] == list(CANONICAL_LITERALS.values())

    _apply_migration(canonical_parity_schema)
    with canonical_parity_schema.cursor() as cur:
        cur.execute(
            """
            SELECT source_entity_id, target_entity_id, valence_magnitude
            FROM entity_relationships_v
            ORDER BY source_entity_id, target_entity_id
            """
        )
        assert cur.fetchall() == pre_088

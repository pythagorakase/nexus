"""Disposable PostgreSQL proofs for trait reuse and shared identity normalization."""

import asyncio
from pathlib import Path

import asyncpg
import pytest

from nexus.agents.orrery.retrograde_maturation import _resolve_pair_hint_entity
from nexus.api.trait_compiler import (
    apply_character_trait_compilation,
    compile_character_traits,
    persist_trait_compile_result,
)
from nexus.api.trait_compiler_schemas import (
    DependentTargetInput,
    DependentsTraitInput,
    SingleEntityTraitInput,
    TraitCompileInputs,
)
from nexus.cli import _print_trait_audit
from nexus.config.loader import settings_path_scope
from nexus.presence.identity import (
    CharacterIdentityAmbiguity,
    read_identity_index,
    require_character_identity,
)
from nexus.presence.roster import (
    RosterEntry,
    resolve_reference,
    resolve_reference_async,
)
from tests.pg_fixtures import asyncpg_kwargs, connect
from tests.test_presence_roster_pg import roster_database
from tests.test_trait_compiler_integration import _character_sheet

pytestmark = pytest.mark.requires_postgres


@pytest.mark.parametrize(
    "name", ["Remote Friend", "Fox", "REMOTE FRIEND", "Juniper Moss"]
)
def test_trait_identity_created_and_reused_audit(roster_database, capsys, name):
    """The real compiler, persisted audit and CLI distinguish reuse from insertion."""
    dbname, ids, _ = roster_database
    novel = name == "Juniper Moss"
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Fox')",
            (ids["Remote Friend"],),
        )
        cur.execute(
            "INSERT INTO assets.new_story_creator (id) VALUES (true) ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "SELECT entity_id FROM characters WHERE id = %s", (ids["Test Protagonist"],)
        )
        entity_id = cur.fetchone()[0]
        sheet = _character_sheet(
            "dependents",
            "resources",
            "fame",
            inputs=TraitCompileInputs(
                dependents=DependentsTraitInput(
                    targets=[DependentTargetInput(name=name)]
                ),
                resources=SingleEntityTraitInput(level="wealthy"),
                fame=SingleEntityTraitInput(level="known"),
            ),
        )
        cur.execute("SELECT count(*) FROM characters")
        before = cur.fetchone()[0]
        for dry_run in (True, False):
            kwargs = dict(
                character=sheet,
                character_id=ids["Test Protagonist"],
                character_entity_id=entity_id,
            )
            result = (
                compile_character_traits(cur, **kwargs, dry_run=True)
                if dry_run
                else apply_character_trait_compilation(cur, **kwargs)
            )
            assert not result.prose_only_remainders
            assert result.counters.created_entities == int(novel)
            assert result.counters.reused_entities == int(not novel)
            if not novel:
                assert result.reused_entities[0].row_id == ids["Remote Friend"]
                assert result.reused_entities[0].name == "Remote Friend"
            persist_trait_compile_result(
                cur, character_id=ids["Test Protagonist"], result=result
            )
            cur.execute(
                "SELECT trait_compile_result FROM assets.new_story_creator WHERE id"
            )
            payload = cur.fetchone()[0]
            assert payload == result.model_dump(mode="json")
            cur.execute(
                "SELECT extra_data->'trait_compile_result' FROM characters WHERE id = %s",
                (ids["Test Protagonist"],),
            )
            assert cur.fetchone()[0] == payload
            _print_trait_audit({"trait_audit": payload})
            output = capsys.readouterr().out
            assert f"  created_entities: {int(novel)}" in output
            assert f"  reused_entities: {int(not novel)}" in output
            assert ("Created Entities:" if novel else "Reused Entities:") in output
            cur.execute("SELECT count(*) FROM characters")
            assert cur.fetchone()[0] == before + int(novel and not dry_run)
        repeat = apply_character_trait_compilation(cur, **kwargs)
        assert repeat.counters.created_entities == 0
        assert repeat.counters.reused_entities == 1
        cur.execute("SELECT count(*) FROM characters")
        assert cur.fetchone()[0] == before + int(novel)


@pytest.mark.parametrize(
    "option,value,canonical,reference,alias,alias_reference,other",
    [
        ("case_folding", False, "ADA", "ADA", "FOX", "FOX", "ada"),
        ("strip_diacritics", True, "José", "Jose", "René", "Rene", None),
        ("strip_titles", False, "Lady Ada", "Lady Ada", "Lady Fox", "Lady Fox", None),
    ],
)
def test_identity_policy_reference_and_pair_hint(
    roster_database,
    tmp_path,
    option,
    value,
    canonical,
    reference,
    alias,
    alias_reference,
    other,
):
    """Minting, catalog resolution, sync/async references and pair hints agree."""
    dbname, ids, _ = roster_database
    config = Path("nexus.toml").read_text()
    config = config.replace(
        f"{option} = {str(not value).lower()}", f"{option} = {str(value).lower()}"
    )
    path = tmp_path / "identity.toml"
    path.write_text(config)
    with settings_path_scope(path):
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET name = %s WHERE id = %s",
                (canonical, ids["Remote Friend"]),
            )
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, %s)",
                (ids["Remote Friend"], alias),
            )
            if other:
                assert require_character_identity(cur, other) is None
                cur.execute(
                    "INSERT INTO characters (name) VALUES (%s) RETURNING id", (other,)
                )
                other_id = cur.fetchone()[0]
            if option == "strip_titles":
                with pytest.raises(CharacterIdentityAmbiguity):
                    require_character_identity(cur, "Ada")
                with pytest.raises(ValueError, match="Unresolved"):
                    resolve_reference(cur, kind="character", id=None, name="Ada")
                with pytest.raises(ValueError, match="does not resolve"):
                    _resolve_pair_hint_entity(cur, "Ada")
            expected = [
                (reference, ids["Remote Friend"]),
                (alias_reference, ids["Remote Friend"]),
            ]
            if other:
                expected.append((other, other_id))
            for label, expected_id in expected:
                assert require_character_identity(cur, label).id == expected_id
                assert (
                    resolve_reference(cur, kind="character", id=None, name=label).id
                    == expected_id
                )
                assert _resolve_pair_hint_entity(cur, label).subtype_id == expected_id
                index = read_identity_index(cur)
                assert (
                    index.resolve(RosterEntry(kind="character", name=label)).id
                    == expected_id
                )

        async def exercise():
            conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
            try:
                for label, expected_id in expected:
                    entry = await resolve_reference_async(
                        conn, kind="character", id=None, name=label
                    )
                    assert entry.id == expected_id
            finally:
                await conn.close()

        asyncio.run(exercise())


def test_identity_consumers_alias_collision_is_loud(roster_database):
    """Normalized alias/name collisions never pick the first catalog identity."""
    dbname, ids, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'TEST PROTAGONIST')",
            (ids["Remote Friend"],),
        )
        with pytest.raises(CharacterIdentityAmbiguity):
            require_character_identity(cur, "Test Protagonist")
        with pytest.raises(ValueError, match="Ambiguous"):
            resolve_reference(cur, kind="character", id=None, name="Test Protagonist")
        with pytest.raises(ValueError, match="ambiguous"):
            _resolve_pair_hint_entity(cur, "Test Protagonist")


def test_identity_missing_reference_never_binds_title_only_name(roster_database):
    """An absent name cannot bind a title-only label normalized to an empty key."""
    dbname, _, _ = roster_database
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO characters (name) VALUES ('Lady')")
        for name in (None, "", "   "):
            with pytest.raises(ValueError, match="Unresolved"):
                resolve_reference(cur, kind="character", id=None, name=name)

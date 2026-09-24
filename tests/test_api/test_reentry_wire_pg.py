"""Issue 918 fixtures exercise real parsing, registry validation, and staging.

Requires template entities, tags, entity_tags, narrative metadata and incubator;
all writes use the acceptance fixture's disposable database.
"""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.orrery_tag_validation import build_storyteller_tag_validator
from nexus.agents.logon.skald_wire import (
    PresenceBaseline,
    SkaldGaiaWire,
    SkaldWriterWire,
    combine_two_pass,
    finalize_scene_reset_repair,
    hydrate_skald_turn,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal
from nexus.agents.orrery.tag_library import (
    EntityRowReference,
    TagLibraryContext,
    format_contextual_tag_library,
)
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.narrative_generation import write_to_incubator
from nexus.api.presence_reconciliation import read_character_roster_from_connection
from nexus.memory.manager import empty_pass2_baseline
from nexus.presence.roster import character_identity_index
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import (
    read_prompt_windows,
    record_prompt_window,
    validation_attempt,
)
from tests.pg_fixtures import connect
from tests.test_api.test_acceptance_staging_pg import acceptance_slot, own_draft

pytestmark = pytest.mark.requires_postgres
FIXTURES = Path(__file__).parents[2] / "docs/qa/918-reentry-wire/fixtures"


def fixture(name: str) -> dict[str, Any]:
    """Read a minimal wire shaped like one recorded failure."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def writer() -> SkaldWriterWire:
    """Build the unchanged writer companion for Gaia fixtures."""
    return SkaldWriterWire(
        narrative="Rain falls.", choices=["Wait.", "Continue."], letter="Continue."
    )


def staged(
    writer_wire: SkaldWriterWire, gaia: SkaldGaiaWire, parent: int, session: str
) -> dict[str, Any]:
    """Hydrate both real wires and adapt the result to staging."""
    response = hydrate_skald_turn(
        combine_two_pass(writer_wire, gaia), presence_baseline=PresenceBaseline()
    )
    response.generation_model = "TEST"
    return response_to_incubator(
        response, parent, "Return.", session, empty_pass2_baseline({})
    )


def record(seat: str = "gaia") -> PromptWindowRecord:
    """Create an isolated ledger row for one validation attempt."""
    row = PromptWindowRecord(
        generation_session=str(uuid4()),
        seat=seat,
        attempt=1,
        model="TEST",
        block_tokens={},
        input_tokens=0,
        effective_ceiling=1,
        policy_headroom=0,
        headroom=1,
    )
    record_prompt_window(row)
    return row


def notes(row: PromptWindowRecord) -> list[dict[str, Any]]:
    """Read back durable repair notes without duplicating attempt rows."""
    result = read_prompt_windows(
        row.generation_session, datetime.now(timezone.utc).date().isoformat()
    )
    assert len(result) == 1
    assert result[0].validation_notes == row.validation_notes
    print(json.dumps(result[0].validation_notes, sort_keys=True))
    return result[0].validation_notes


@pytest.mark.asyncio
async def test_place_fixture_rejects_before_staging(
    acceptance_slot: tuple[str, int, int],
) -> None:
    """The Gaia boundary rejects the recorded place before staging is invoked."""
    dbname, parent, _ = acceptance_slot
    gaia = SkaldGaiaWire.model_validate(fixture("place"))
    validator = build_storyteller_tag_validator(dbname)
    with pytest.raises(ValueError) as error:
        await validator(SimpleNamespace(retry=0), gaia)
    assert str(error.value) == (
        "Unresolved place state update name 'Loading Arcade'; new places must be "
        "declared through new_entities in the same turn."
    )
    print(str(error.value))
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM incubator")
        assert cur.fetchone() == (0,)
        cur.execute("SELECT count(*) FROM places WHERE name='Loading Arcade'")
        assert cur.fetchone() == (0,)
        session = own_draft(conn, parent)
        with pytest.raises(ValueError, match="Unresolved place state update"):
            await write_to_incubator(conn, staged(writer(), gaia, parent, session))


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["canonical", "alias", "declaration"])
async def test_place_resolution_stages(
    acceptance_slot: tuple[str, int, int], identity: str
) -> None:
    """Catalog identities, optional aliases, and declarations all stage."""
    dbname, parent, _ = acceptance_slot
    gaia = SkaldGaiaWire.model_validate(fixture("place"))
    with connect(dbname) as conn, conn.cursor() as cur:
        if identity != "declaration":
            name = "Loading Arcade" if identity == "canonical" else "Hall"
            cur.execute(
                "INSERT INTO places(name,type) VALUES (%s,'fixed_location') RETURNING id",
                (name,),
            )
            place_id = cur.fetchone()[0]
            if identity == "alias":
                cur.execute(
                    "CREATE TABLE place_aliases (place_id bigint REFERENCES places(id), alias text)"
                )
                cur.execute(
                    "COMMENT ON TABLE place_aliases IS 'Disposable QA alias catalog'"
                )
                cur.execute(
                    "COMMENT ON COLUMN place_aliases.place_id IS 'Canonical place row'"
                )
                cur.execute(
                    "COMMENT ON COLUMN place_aliases.alias IS 'Alternative place name'"
                )
                cur.execute(
                    "INSERT INTO place_aliases VALUES (%s,'Loading Arcade')",
                    (place_id,),
                )
        else:
            from nexus.agents.logon.apex_schema import NewEntityDeclaration

            gaia.new_entities = [
                NewEntityDeclaration(
                    kind="place", name="Loading Arcade", summary="An arcade."
                )
            ]
    validator = build_storyteller_tag_validator(
        dbname, allow_same_turn_faction_declarations=True
    )
    await validator(SimpleNamespace(retry=0), gaia)
    if identity != "declaration":
        assert gaia.updates.places[0].id == place_id
    with connect(dbname) as conn:
        session = own_draft(conn, parent)
        # Also exercise staging's alias resolver without the canonicalized Gaia ID.
        if identity == "alias":
            gaia = SkaldGaiaWire.model_validate(fixture("place"))
        await write_to_incubator(conn, staged(writer(), gaia, parent, session))
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (1,)


@pytest.mark.asyncio
async def test_presence_fixture_repairs_alias_and_stages(
    acceptance_slot: tuple[str, int, int], caplog: pytest.LogCaptureFixture
) -> None:
    """Resolve a moved alias to the roster identity and retain one staged entry."""
    dbname, parent, _ = acceptance_slot
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO places(name,type) VALUES ('Hall','fixed_location')")
        cur.execute("SELECT id FROM characters WHERE name='Fixture Player'")
        actor = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO character_aliases(character_id,alias) VALUES (%s,'Player Alias')",
            (actor,),
        )
        rows = read_character_roster_from_connection(conn)
    response = SkaldWriterWire.model_validate(fixture("presence"))
    row = record("skald_writer")
    with validation_attempt(row):
        finalize_scene_reset_repair(
            response, character_identity_index(rows.characters, rows.aliases)
        )
    assert response.presence.enter == response.presence.exit == []
    assert [(ref.id, ref.name) for ref in response.presence.scene_reset.present] == [
        (actor, "Fixture Player")
    ]
    assert notes(row) == [
        {
            "repair": "scene-reset-crossings",
            "moved": ["Player Alias"],
            "dropped": ["Fixture Player"],
        }
    ]
    assert row.generation_session in caplog.text
    with connect(dbname) as conn:
        session = own_draft(conn, parent)
        await write_to_incubator(
            conn, staged(response, SkaldGaiaWire(letter="Continue."), parent, session)
        )
        with conn.cursor() as cur:
            cur.execute("SELECT reference_updates FROM incubator")
            assert len(cur.fetchone()[0]["characters"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("site", ["actor", "target", "update"])
async def test_tag_fixture_repairs_active_or_applies_inactive(
    acceptance_slot: tuple[str, int, int],
    active: bool,
    site: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Active reassertions are audited no-ops; inactive tags survive real commit."""
    dbname, parent, resolution = acceptance_slot
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, entity_id FROM characters WHERE name='Fixture Player'")
        character_id, actor = cur.fetchone()
        if active:
            cur.execute(
                "INSERT INTO entity_tags(entity_id,tag_id,source_kind) SELECT %s,id,'llm_generated' FROM tags WHERE tag='forewarned'",
                (actor,),
            )
        cur.execute(
            "SELECT id,tag_id,expires_at_world_time FROM entity_tags WHERE entity_id=%s",
            (actor,),
        )
        before = cur.fetchall()
    proposal = OrreryResolutionDraft(
        template_id="sleep",
        priority=25,
        binding_hash="reentry",
        bindings={"actor": actor, "target": actor},
        branch_label="return",
        narrative_stub="{actor} returns.",
        magnitude=0.2,
    )
    payload = fixture("tag")
    payload["orrery_adjudications"][0]["proposal_id"] = proposal.proposal_id
    if site == "target":
        payload["orrery_adjudications"][0]["replacement_state_delta"] = {
            "entity_tags_target_add": ["forewarned"]
        }
    elif site == "update":
        payload.pop("orrery_adjudications")
        payload["updates"] = {
            "characters": [
                {
                    "name": "Fixture Player",
                    "id": character_id,
                    "tags_add": ["forewarned"],
                }
            ],
            "places": [],
            "factions": [],
            "relationships": [],
        }
    gaia = SkaldGaiaWire.model_validate(payload)
    validator = build_storyteller_tag_validator(
        dbname,
        proposal_bindings_provider=lambda: {proposal.proposal_id: proposal.bindings},
        anchor_chunk_id_provider=lambda: parent,
    )
    row = record()
    with validation_attempt(row):
        await validator(SimpleNamespace(retry=0), gaia)
    repairs = notes(row)
    assert len(repairs) == int(active)
    if active:
        assert repairs[0]["tag"] == "forewarned"
        assert row.generation_session in caplog.text
    if site == "update":
        assert bool(gaia.updates.characters) is not active
    else:
        field = "entity_tags_add" if site == "actor" else "entity_tags_target_add"
        assert getattr(gaia.orrery_adjudications[0].replacement_state_delta, field) == (
            [] if active else ["forewarned"]
        )
    with connect(dbname) as conn:
        session = own_draft(conn, parent)
        data = staged(writer(), gaia, parent, session)
        if site != "update":
            data["orrery_proposal"] = OrreryTickProposal(
                anchor_chunk_id=parent, actor_count=1, resolutions=(proposal,)
            ).to_dict()
        await write_to_incubator(conn, data)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,tag_id,expires_at_world_time FROM entity_tags WHERE entity_id=%s",
                (actor,),
            )
            assert cur.fetchall() == before
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (1,)
    library = format_contextual_tag_library(
        dbname,
        context=TagLibraryContext(
            present_entity_refs=[EntityRowReference("character", character_id)],
            proposal_tag_names={"forewarned"},
            has_pending_proposals=True,
            anchor_chunk_id=parent,
        ),
    )
    assert ("`forewarned` is active in this context" in library) is active
    assert "replacement-state entity tag additions" in library
    if not active:
        assert "When `forewarned` is already active" in library
    with closing(connect(dbname)) as conn:
        committed = commit_incubator_to_database_sync(conn, session, slot=5)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT et.id, et.tag_id, et.expires_at_world_time, et.source_chunk_id "
                "FROM entity_tags et JOIN tags t ON t.id=et.tag_id "
                "WHERE et.entity_id=%s AND t.tag='forewarned' AND et.cleared_at IS NULL",
                (actor,),
            )
            applied = cur.fetchall()
            assert len(applied) == 1
            if active:
                assert applied[0][:3] == before[0]
            else:
                assert applied[0][3] == committed


@pytest.mark.asyncio
async def test_place_tag_registry_retry_uses_real_catalog(
    acceptance_slot: tuple[str, int, int],
) -> None:
    """Retain the place-tag retry proof using the live registry and resolver."""
    dbname, _, _ = acceptance_slot
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO places(name,type) VALUES ('Loading Arcade','fixed_location')"
        )
    gaia = SkaldGaiaWire.model_validate(fixture("place"))
    gaia.updates.places[0].tags_clear = ["human"]
    validator = build_storyteller_tag_validator(dbname)
    with pytest.raises(ModelRetry, match="updates.places"):
        await validator(SimpleNamespace(retry=0), gaia)
    gaia.updates.places[0].tags_clear = ["haven"]
    assert await validator(SimpleNamespace(retry=1), gaia) is gaia

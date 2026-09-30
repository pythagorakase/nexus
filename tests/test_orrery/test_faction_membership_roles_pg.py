"""Faction membership follows the configured roles (issue #1033).

One disposable clone holds one faction and one character per
``faction_member_role`` label. Hydration must make ``faction_member`` true for
exactly the roles in ``[orrery.resolver] membership_roles``: a character the
faction hunts (``target``) or expelled (``exile``) is not one of its members.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import nexus.config
from nexus.agents.logon.apex_enums import FactionMemberRole
from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.substrate import Slot, WorldState, faction_member
from nexus.config import load_settings
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_character,
    seed_faction,
    seed_faction_membership,
    seed_story_clock,
    sqlalchemy_url,
)
from tests.settings_helpers import settings_with

pytestmark = pytest.mark.requires_postgres

STORY_WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def membership_clone() -> Iterator[dict[str, Any]]:
    """Seed one faction and one member row per ``faction_member_role`` label."""

    with disposable_slot_database("qa640_membership_roles") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT enum_range(NULL::faction_member_role)::text[]")
            labels = list(cur.fetchone()[0])
        seed_story_clock(dbname, world_time=STORY_WORLD_TIME)
        faction_id, faction_entity_id = seed_faction(dbname, name="Membership Guild")
        member_entities: dict[str, int] = {}
        for label in labels:
            character_id, entity_id = seed_character(dbname, name=f"Membership {label}")
            seed_faction_membership(
                dbname,
                character_id=character_id,
                faction_id=faction_id,
                role=label,
            )
            member_entities[label] = entity_id
        yield {
            "dbname": dbname,
            "labels": labels,
            "faction_entity_id": faction_entity_id,
            "member_entities": member_entities,
        }


@pytest.fixture()
def membership_session(membership_clone: dict[str, Any]) -> Iterator[Session]:
    """Open one read session over the seeded clone."""

    engine = create_engine(sqlalchemy_url(membership_clone["dbname"]), future=True)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _member_roles(state: WorldState, clone: Mapping[str, Any]) -> set[str]:
    """Return the roles whose seeded character passes ``faction_member``."""

    condition = faction_member()
    return {
        role
        for role, entity_id in clone["member_entities"].items()
        if condition(
            state,
            {Slot.ACTOR: entity_id, Slot.FACTION: clone["faction_entity_id"]},
        )
    }


def test_clone_seeds_every_faction_member_role_label(
    membership_clone: dict[str, Any],
) -> None:
    """The fixture covers the live enum, which the settings validator mirrors."""

    labels = membership_clone["labels"]
    assert sorted(labels) == sorted(role.value for role in FactionMemberRole)
    dbname = membership_clone["dbname"]
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT role::text, count(*) FROM faction_character_relationships "
            "GROUP BY role"
        )
        assert dict(cur.fetchall()) == {label: 1 for label in labels}


def test_faction_member_is_true_for_exactly_the_configured_roles(
    membership_clone: dict[str, Any],
    membership_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hydration reads the loaded settings' membership roles and filters by them.

    The shipped list equals the model default, so the second hydration swaps
    the loaded settings for a list no default carries: only a ``None`` branch
    that reads ``load_settings()`` yields it.
    """

    orrery = load_settings().orrery
    assert orrery is not None
    configured = set(orrery.resolver.membership_roles)
    assert configured < set(membership_clone["labels"])

    state = hydrate_world_state(
        membership_session,
        anchor_chunk_id=None,
        window_chunks=30,
    )

    assert _member_roles(state, membership_clone) == configured
    faction = membership_clone["faction_entity_id"]
    for role in set(membership_clone["labels"]) - configured:
        entity_id = membership_clone["member_entities"][role]
        assert faction not in state.faction_memberships.get(entity_id, frozenset())

    loaded = settings_with({"orrery.resolver.membership_roles": ["leader", "exile"]})
    monkeypatch.setattr(nexus.config, "load_settings", lambda *_a, **_k: loaded)
    swapped = hydrate_world_state(
        membership_session,
        anchor_chunk_id=None,
        window_chunks=30,
    )

    assert _member_roles(swapped, membership_clone) == {"leader", "exile"}


def test_narrowed_membership_roles_change_hydrated_membership(
    membership_clone: dict[str, Any],
    membership_session: Session,
) -> None:
    """A settings change to ``["leader"]`` leaves only the leader a member."""

    settings = settings_with({"orrery.resolver.membership_roles": ["leader"]})
    assert settings.orrery is not None

    typed = hydrate_world_state(
        membership_session,
        anchor_chunk_id=None,
        window_chunks=30,
        resolver_settings=settings.orrery.resolver,
    )
    # The resolve phase hands the resolver the dumped Orrery section.
    dumped = hydrate_world_state(
        membership_session,
        anchor_chunk_id=None,
        window_chunks=30,
        resolver_settings=settings.orrery.model_dump(by_alias=True)["resolver"],
    )

    assert _member_roles(typed, membership_clone) == {"leader"}
    assert _member_roles(dumped, membership_clone) == {"leader"}
    assert typed.faction_memberships == {
        membership_clone["member_entities"]["leader"]: frozenset(
            {membership_clone["faction_entity_id"]}
        )
    }

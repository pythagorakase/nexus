"""Card ranking and real PostgreSQL prompt/exposure/Backstage parity."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import Iterator

import asyncpg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.logon_utility import LogonUtility, _orrery_card_identity
from nexus.agents.orrery.audit import cognition_trace
from nexus.agents.orrery.backstage import _orrery
from nexus.agents.orrery.events import commit_orrery_tick_async, commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    rank_proposals,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import HabituationPolicy, WorldState
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.config import load_settings_as_dict
from tests.pg_fixtures import asyncpg_kwargs, disposable_slot_database, sqlalchemy_url


def test_rank_retains_distinct_templates_and_habituation() -> None:
    """Equal binding hashes are distinct cards; dampening changes their rank."""
    templates = [
        replace(template, priority=40)
        for template in BUILTIN_TEMPLATES
        if template.id in {"stroll", "upkeep"}
    ]
    assert len(templates) == 2
    drafts = [
        OrreryResolutionDraft(
            template_id=template.id,
            priority=template.priority,
            binding_hash="same-binding",
            bindings={"actor": 1},
            branch_label="routine",
            narrative_stub="Routine activity.",
        )
        for template in templates
    ]
    policy = HabituationPolicy(enabled=True, penalty_per_win=10, max_penalty=20)
    state = WorldState(win_history={(1, drafts[0].template_id): 1})
    ranked = rank_proposals(drafts, templates, state, policy)
    assert [card.proposal_id for card in ranked] == [
        drafts[1].proposal_id,
        drafts[0].proposal_id,
    ]
    assert [card.effective_priority for card in ranked] == [40, 30]
    assert [card.position for card in ranked] == [0, 1]
    proposal = OrreryTickProposal(
        anchor_chunk_id=1, actor_count=1, resolutions=tuple(ranked)
    )
    assert (
        OrreryTickProposal.from_dict(json.loads(json.dumps(proposal.to_dict())))
        == proposal
    )
    tied = rank_proposals(drafts, templates, WorldState(), policy)
    assert [card.proposal_id for card in tied] == [card.proposal_id for card in drafts]


@pytest.fixture()
def card_database() -> Iterator[str]:
    """Migrate a disposable corpus; never mutate the source save or template."""
    with disposable_slot_database(
        "qa640_781_cards", source_db="save_04", include_data=True
    ) as dbname:
        yield dbname


@pytest.mark.requires_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_card_exposure_rank_joint_and_backstage_parity(
    card_database: str, asynchronous: bool
) -> None:
    """Both real commit paths retain ranked, named cards even when deferred."""
    settings = load_settings_as_dict()
    config = settings["orrery"]
    engine = create_engine(sqlalchemy_url(card_database))
    try:
        with Session(engine) as session:
            assert (
                session.execute(text("SELECT current_database()")).scalar_one()
                == card_database
            )
            anchor = session.execute(
                text("SELECT max(id) FROM narrative_chunks")
            ).scalar_one()
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor,
                window_chunks=config["binding"]["window_chunks"],
                **{
                    key + "_settings": config[value]
                    for key, value in {
                        "sunhelm": "sunhelm",
                        "selection": "selection",
                        "habituation": "habituation",
                        "package_selection": "package_selection",
                        "project": "projects",
                        "epistemics": "epistemics",
                        "fanout": "fanout",
                        "contagion": "contagion",
                        "weather": "weather",
                        "mood": "mood",
                        "composition": "composition",
                    }.items()
                },
            )
            assert (
                proposal.resolutions
                and proposal.scene_pressures
                and proposal.joint_beats
            )
            assert [card.position for card in proposal.resolutions] == list(
                range(proposal.resolution_count)
            )
            assert [card.effective_priority for card in proposal.resolutions] == sorted(
                [card.effective_priority for card in proposal.resolutions], reverse=True
            )
            places = dict(
                session.execute(
                    text(
                        "SELECT c.entity_id, p.name FROM characters c "
                        "LEFT JOIN places p ON p.id=c.current_location"
                    )
                ).all()
            )
            for card in (*proposal.resolutions, *proposal.scene_pressures):
                assert card.binding_names["actor"]
                assert card.binding_names["place"] == (
                    places[card.bindings["actor"]] or "unknown"
                )
                assert card.evaluated_at
            payload = {
                "user_input": "Continue.",
                "orrery_imminent_activity": [
                    card.to_dict() for card in proposal.resolutions
                ],
                "orrery_scene_pressures": [
                    card.to_dict() for card in proposal.scene_pressures
                ],
                "orrery_joint_beats": [beat.to_dict() for beat in proposal.joint_beats],
            }
            # Exercise the real shared formatter in both seat modes. The paid
            # before/after proof covers complete seat requests and adjudications.
            prompt_config = {"max_rendered_proposals": 1, "max_rendered_pressures": 1}
            utility = LogonUtility({"orrery": {"prompt": prompt_config}})
            writer = utility._format_context_prompt(payload)
            gaia = utility._format_context_prompt(
                payload, include_ambient_scene_seeds=False
            )
            for prompt in (writer, gaia):
                assert (
                    _orrery_card_identity(proposal.resolutions[0].to_dict()) in prompt
                )
                assert (
                    _orrery_card_identity(proposal.scene_pressures[0].to_dict())
                    in prompt
                )
                joint_ids = {
                    proposal.joint_beats[0].forward_proposal_id,
                    proposal.joint_beats[0].reverse_proposal_id,
                }
                for parent in (
                    card.to_dict()
                    for card in proposal.resolutions
                    if card.proposal_id in joint_ids
                ):
                    assert _orrery_card_identity(parent) in prompt
            chunk = session.execute(
                text(
                    "INSERT INTO narrative_chunks (raw_text, storyteller_text, state) "
                    "VALUES ('Card identity QA', 'Card identity QA', 'accepted') RETURNING id"
                )
            ).scalar_one()
            session.execute(
                text(
                    "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, world_layer, time_delta) "
                    "SELECT :chunk, season, episode, scene+1, world_layer, interval '1 minute' "
                    "FROM chunk_metadata WHERE chunk_id=:anchor"
                ),
                {"chunk": chunk, "anchor": anchor},
            )
            session.commit()
            kwargs = {
                "tick_chunk_id": chunk,
                "prompt_settings": prompt_config,
                "adjudications": [
                    {
                        "proposal_id": card.proposal_id,
                        "action": "defer",
                        "note": "QA deferral",
                    }
                    for card in proposal.resolutions
                ],
            }
            if asynchronous:
                conn = await asyncpg.connect(**asyncpg_kwargs(card_database))
                try:
                    async with conn.transaction():
                        result = await commit_orrery_tick_async(
                            conn, proposal, **kwargs
                        )
                finally:
                    await conn.close()
            else:
                result = commit_orrery_tick_sync(
                    session.connection().connection.driver_connection,
                    proposal,
                    **kwargs,
                )
                session.commit()
            assert result.resolution_count == 0
            exposures = (
                session.execute(
                    text(
                        "SELECT kind, proposal_id, position, card FROM orrery_prompt_exposures "
                        "WHERE tick_chunk_id=:chunk ORDER BY position, kind"
                    ),
                    {"chunk": chunk},
                )
                .mappings()
                .all()
            )
            assert len(exposures) == result.prompt_exposure_count == 4
            cards = {card.proposal_id: card.to_dict() for card in proposal.resolutions}
            for row in exposures:
                if row["kind"] == "scene_pressure":
                    assert row["card"] == proposal.scene_pressures[0].to_dict()
                    continue
                assert row["position"] == cards[row["proposal_id"]]["position"]
                assert (
                    row["card"]["binding_names"]
                    == cards[row["proposal_id"]]["binding_names"]
                )
                assert _orrery_card_identity(row["card"]) in writer
            backstage = _orrery(session, chunk_id=chunk, prior_chunks=[])
            assert [row.proposal_id for row in backstage.rows] == [
                card.proposal_id for card in proposal.resolutions
            ]
            assert [row.position for row in backstage.rows] == list(
                range(proposal.resolution_count)
            )
            for beat in proposal.joint_beats[:1]:
                for actor in (beat.entity_a, beat.entity_b):
                    trace = cognition_trace(
                        session, actor, anchor_chunk_id=chunk, orrery_settings=config
                    )
                    shown = trace["actor_facing"]["prompt_exposure"]["orrery_proposals"]
                    joints = [row for row in shown if row["kind"] == "joint_beat"]
                    assert len(joints) == 2
                    assert all(row["payload"]["binding_names"] for row in joints)
    finally:
        engine.dispose()

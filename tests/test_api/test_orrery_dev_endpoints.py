"""Live tests for the /api/dev/orrery/* audit endpoints.

These exercise the real router over HTTP through a TestClient against real
slot databases — no mocks (see CLAUDE.md testing philosophy). The central
contract is parity: for the same anchor, the explained payload must name
exactly the winners the production ``resolve_dry_run`` selects, stack by
stack, including branch, magnitude, event type, binding hash, and the
rendered narrative stub.

save_02 is the dense retrograde-backfilled audit target; save_05 is the
small live-runtime slot exhibiting the NULL-world-time bestowal pathology —
running parity on both catches data-shape assumptions the other slot would
hide, and a joint non-vacuity test guards against both slots drifting into
a state where a parity block silently runs zero iterations. All endpoints
are read-only, so no cleanup is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.needs import NEED_SEVERITY_PREFIX
from nexus.agents.orrery.resolver import OrreryTickProposal, resolve_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.orrery_dev_endpoints import router as orrery_dev_router
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings, load_settings_as_dict

AUDIT_SLOTS = (2, 5)

TWO_PARTY_TEMPLATE_IDS = {t.id for t in BUILTIN_TEMPLATES if len(t.required_slots) == 2}
ACTOR_ONLY_TEMPLATE_IDS = {
    t.id for t in BUILTIN_TEMPLATES if len(t.required_slots) == 1
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(orrery_dev_router)
    return TestClient(app)


def _production_proposal(slot: int) -> tuple[Optional[int], OrreryTickProposal]:
    """Run the production resolver directly — the parity oracle."""

    orrery = load_settings_as_dict()["orrery"]
    engine = create_engine(get_slot_db_url(slot=slot))
    try:
        with Session(engine) as session:
            anchor_chunk_id = session.execute(
                text("SELECT max(id) FROM narrative_chunks")
            ).scalar()
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=int(orrery["binding"]["window_chunks"]),
                sunhelm_settings=orrery.get("sunhelm"),
            )
    finally:
        engine.dispose()
    return anchor_chunk_id, proposal


@pytest.fixture(scope="module")
def production_proposals() -> dict[int, tuple[Optional[int], OrreryTickProposal]]:
    return {slot: _production_proposal(slot) for slot in AUDIT_SLOTS}


def _all_stacks(payload: dict) -> Iterator[tuple[dict, dict]]:
    for group in payload["actors"]:
        yield group, group["actor_stack"]
        for stack in group["two_party_stacks"]:
            yield group, stack
        for stack in group["scene_pressure_stacks"]:
            yield group, stack


def _winner(stack: dict) -> dict:
    return next(t for t in stack["templates"] if t["is_winner"])


@pytest.mark.requires_postgres
def test_slots_jointly_exercise_both_parity_contracts(
    production_proposals: dict[int, tuple[Optional[int], OrreryTickProposal]],
) -> None:
    """Guard against the parity test going vacuous as slot data drifts.

    Each parity block below iterates over whatever the production resolver
    yields; if every audited slot stopped producing resolutions (or scene
    pressures), that block would silently pass with zero iterations. This
    test fails loudly instead, telling us to repoint AUDIT_SLOTS.
    """

    total_resolutions = sum(
        len(proposal.resolutions) for _, proposal in production_proposals.values()
    )
    total_pressures = sum(
        len(proposal.scene_pressures) for _, proposal in production_proposals.values()
    )
    assert total_resolutions > 0, (
        "no audited slot produces resolutions — winner parity is vacuous; "
        "repoint AUDIT_SLOTS at a slot with Orrery activity"
    )
    assert total_pressures > 0, (
        "no audited slot produces scene pressures — pressure parity is "
        "vacuous; repoint AUDIT_SLOTS at a slot with on-screen targets"
    )


@pytest.mark.requires_postgres
@pytest.mark.parametrize("slot", AUDIT_SLOTS)
def test_resolve_parity_with_production_resolver(
    client: TestClient,
    production_proposals: dict[int, tuple[Optional[int], OrreryTickProposal]],
    slot: int,
) -> None:
    anchor_chunk_id, proposal = production_proposals[slot]

    response = client.post(
        "/api/dev/orrery/resolve",
        json={"slot": slot, "anchor_chunk_id": anchor_chunk_id},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["anchor_chunk_id"] == anchor_chunk_id
    assert payload["mode"] == "current"
    assert payload["actor_count"] == proposal.actor_count
    assert len(payload["actors"]) == proposal.actor_count

    # --- Resolution parity: actor-only + off-screen two-party stacks -------
    endpoint_winners: dict[tuple[str, str], dict] = {}
    for group in payload["actors"]:
        for stack in [group["actor_stack"], *group["two_party_stacks"]]:
            if stack["winner_id"] is None:
                continue
            winner = _winner(stack)
            key = (winner["template_id"], winner["binding_hash"])
            assert key not in endpoint_winners, "duplicate winner stack"
            endpoint_winners[key] = winner

    production = {
        (draft.template_id, draft.binding_hash): draft for draft in proposal.resolutions
    }
    assert set(endpoint_winners) == set(production)
    for key, draft in production.items():
        winner = endpoint_winners[key]
        assert winner["chosen_branch"] == draft.branch_label
        assert winner["magnitude"] == pytest.approx(draft.magnitude)
        assert winner["event_type"] == draft.event_type
        assert winner["changed_fields"] == list(draft.changed_fields)
        assert winner["state_delta"] == dict(draft.state_delta)
        # Production renders the stub through the entity-name table; the
        # audit payload must reproduce it verbatim.
        assert winner["narrative_stub_rendered"] == draft.narrative_stub

    # --- Scene-pressure parity: template pressures + need pseudo-drafts ----
    production_pressures = {
        (draft.template_id, draft.binding_hash): draft
        for draft in proposal.scene_pressures
    }
    endpoint_pressures: dict[tuple[str, str], dict] = {}
    for group in payload["actors"]:
        for stack in group["scene_pressure_stacks"]:
            if stack["winner_id"] is None:
                continue
            winner = _winner(stack)
            endpoint_pressures[(winner["template_id"], winner["binding_hash"])] = {
                "magnitude": winner["magnitude"],
                "prompt_text": winner["scene_pressure_prompt_rendered"],
            }
    for pressure in payload["need_pressures"]:
        endpoint_pressures[(pressure["template_id"], pressure["binding_hash"])] = {
            "magnitude": pressure["magnitude"],
            "prompt_text": pressure["prompt_text"],
        }

    assert set(endpoint_pressures) == set(production_pressures)
    for key, draft in production_pressures.items():
        assert endpoint_pressures[key]["magnitude"] == pytest.approx(draft.magnitude)
        assert endpoint_pressures[key]["prompt_text"] == draft.prompt_text


@pytest.mark.requires_postgres
def test_resolve_four_template_states_are_distinguishable(
    client: TestClient,
) -> None:
    """Winner / shadowed / gate-failed / not-applicable must never blur."""

    response = client.post("/api/dev/orrery/resolve", json={"slot": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["actors"], "save_02 is expected to bind off-screen actors"

    for group in payload["actors"]:
        # Stack composition respects arity — the stack-split trap guard.
        actor_stack_ids = {t["template_id"] for t in group["actor_stack"]["templates"]}
        assert actor_stack_ids == ACTOR_ONLY_TEMPLATE_IDS
        assert "target" not in group["actor_stack"]["bindings"]
        for stack in group["two_party_stacks"] + group["scene_pressure_stacks"]:
            stack_ids = {t["template_id"] for t in stack["templates"]}
            assert stack_ids <= TWO_PARTY_TEMPLATE_IDS
            assert stack["bindings"].get("target") is not None

        # Not-applicable is exactly "no two-party binding composed", and is
        # never conflated with an evaluated-and-refused gate.
        if group["two_party_stacks"]:
            assert group["not_applicable"] == []
        else:
            marked = {item["template_id"] for item in group["not_applicable"]}
            assert marked == TWO_PARTY_TEMPLATE_IDS
            assert all(
                item["reason"] == "no_target_bound" for item in group["not_applicable"]
            )

    for _, stack in _all_stacks(payload):
        shadowed = set(stack["shadowed_ids"])
        for template in stack["templates"]:
            # Payload hygiene: defaults on non-fired templates are nulled.
            if not template["fired"]:
                assert template["magnitude"] is None
                assert template["event_type"] is None
                assert template["chosen_branch"] is None
            if not template["gate_passed"]:
                assert template["fired"] is False
            if template["is_winner"]:
                assert template["template_id"] == stack["winner_id"]
                assert template["fired"] is True
            if template["template_id"] in shadowed:
                assert template["fired"] is True
                assert not template["is_winner"]


@pytest.mark.requires_postgres
def test_entity_context_hover_payload(client: TestClient) -> None:
    resolve = client.post("/api/dev/orrery/resolve", json={"slot": 2})
    assert resolve.status_code == 200
    groups = resolve.json()["actors"]
    assert groups
    entity_ids = [groups[0]["actor_entity_id"], groups[1]["actor_entity_id"]]

    response = client.post(
        "/api/dev/orrery/context/entities",
        json={"slot": 2, "entity_ids": entity_ids, "recent_events_limit": 3},
    )
    assert response.status_code == 200
    payload = response.json()

    assert [e["entity_id"] for e in payload["entities"]] == sorted(entity_ids)
    for entity in payload["entities"]:
        assert entity["name"]
        assert entity["kind"] == "character"
        for bucket in ("durable", "ephemeral"):
            for tag_row in entity["tags"][bucket]:
                assert tag_row["provenance"] in {"approximate", "unknowable"}
                assert (tag_row["provenance"] == "approximate") == (
                    tag_row["applied_at_world_time"] is not None
                )
                assert isinstance(tag_row["families"], list)
        for relationship in entity["relationships"]:
            assert relationship["versioned"] is False
            assert relationship["direction"] in {"outbound", "inbound"}
            assert relationship["other_name"]
        for need in entity["needs"]:
            assert need["need_type"] in set(NEED_SEVERITY_PREFIX)
        assert len(entity["recent_events"]) <= 3
        if entity["place"] is not None:
            assert isinstance(entity["place"]["classes"], list)


@pytest.mark.requires_postgres
def test_entity_context_recent_events_respect_anchor(client: TestClient) -> None:
    """A historical anchor must not surface events from its own future."""

    resolve = client.post("/api/dev/orrery/resolve", json={"slot": 2})
    assert resolve.status_code == 200
    resolved = resolve.json()
    head_anchor = resolved["anchor_chunk_id"]
    entity_ids = [group["actor_entity_id"] for group in resolved["actors"][:3]]

    at_head = client.post(
        "/api/dev/orrery/context/entities",
        json={"slot": 2, "entity_ids": entity_ids, "anchor_chunk_id": head_anchor},
    )
    assert at_head.status_code == 200
    for entity in at_head.json()["entities"]:
        for event in entity["recent_events"]:
            assert event["tick_chunk_id"] <= head_anchor

    # Anchor 0 predates every event; the honest answer is "none yet".
    at_genesis = client.post(
        "/api/dev/orrery/context/entities",
        json={"slot": 2, "entity_ids": entity_ids, "anchor_chunk_id": 0},
    )
    assert at_genesis.status_code == 200
    for entity in at_genesis.json()["entities"]:
        assert entity["recent_events"] == []


def test_catalog_endpoint_over_http(client: TestClient) -> None:
    """Route wiring for GET /catalog; payload content is covered offline."""

    response = client.get("/api/dev/orrery/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert {band["band"] for band in payload["drive_bands"]} == {
        "crisis_constraint",
        "embodied_maintenance",
        "anchored_routine",
        "affiliation",
        "project_identity",
    }
    assert len(payload["pseudo_templates"]) == len(NEED_SEVERITY_PREFIX)
    assert payload["promotion"] is not None


def test_resolve_rejects_invalid_slot(client: TestClient) -> None:
    # Slot validation fails inside get_slot_db_url before any engine or
    # database connection exists, so no postgres marker is needed.
    response = client.post("/api/dev/orrery/resolve", json={"slot": 9})
    assert response.status_code == 400


def test_dashboard_flag_gates_router_registration(tmp_path: Path) -> None:
    """Both arms of the server-side gate, exercised on real parsed config."""

    import tomlkit

    import nexus.api.narrative as narrative

    document = tomlkit.parse(Path("nexus.toml").read_text())

    document["orrery"]["dashboard"]["enabled"] = False  # type: ignore[index]
    off_path = tmp_path / "nexus_dashboard_off.toml"
    off_path.write_text(tomlkit.dumps(document))
    app_off = FastAPI()
    narrative._include_orrery_dev_router(app_off, load_settings(str(off_path)))
    assert not [
        route
        for route in app_off.routes
        if str(getattr(route, "path", "")).startswith("/api/dev/orrery")
    ]

    document["orrery"]["dashboard"]["enabled"] = True  # type: ignore[index]
    on_path = tmp_path / "nexus_dashboard_on.toml"
    on_path.write_text(tomlkit.dumps(document))
    app_on = FastAPI()
    narrative._include_orrery_dev_router(app_on, load_settings(str(on_path)))
    registered = {
        str(getattr(route, "path", ""))
        for route in app_on.routes
        if str(getattr(route, "path", "")).startswith("/api/dev/orrery")
    }
    assert registered == {
        "/api/dev/orrery/catalog",
        "/api/dev/orrery/resolve",
        "/api/dev/orrery/context/entities",
    }

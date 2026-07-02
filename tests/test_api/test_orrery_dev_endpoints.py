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
from nexus.agents.orrery.resolver import (
    OrreryTickProposal,
    _present_actor_ids_at_anchor,
    resolve_dry_run,
)
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


# ---------------------------------------------------------------------------
# What-if (override/sandbox) mode
# ---------------------------------------------------------------------------


def _resolve(client: TestClient, slot: int, **extra) -> dict:
    response = client.post("/api/dev/orrery/resolve", json={"slot": slot, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def _not_hunted_winners(payload: dict) -> Iterator[tuple[int, dict]]:
    """Actor-only winners whose gate passed through a top-level
    NOT(has_inbound_pair_tag(hunting)) leg — the injection kill switch."""

    for group in payload["actors"]:
        stack = group["actor_stack"]
        if stack["winner_id"] is None:
            continue
        winner = _winner(stack)
        root = winner["gate_trace"]
        if root.get("op") != "AND":
            continue
        for child in root["children"]:
            if (
                child.get("op") == "NOT"
                and child["result"] is True
                and child["children"][0]["raw"].startswith(
                    "has_inbound_pair_tag(hunting"
                )
            ):
                yield group["actor_entity_id"], winner
                break


@pytest.mark.requires_postgres
def test_current_mode_carries_no_what_if_payload(client: TestClient) -> None:
    payload = _resolve(client, 2)
    assert payload["mode"] == "current"
    assert payload["overrides"] is None
    assert payload["need_pressures_diff"] is None
    for _, stack in _all_stacks(payload):
        assert stack["diff"] is None

    # An explicitly empty override set is still current mode.
    empty = _resolve(client, 2, overrides={})
    assert empty["mode"] == "current"
    assert empty["overrides"] is None


@pytest.mark.requires_postgres
def test_what_if_pair_tag_injection_kills_a_winner(client: TestClient) -> None:
    """The guaranteed flip: a winner that required NOT(inbound hunting) at the
    top of its AND gate cannot survive the tag's injection, so the diff must
    record both the fired flip and the winner change."""

    candidates: list[tuple[int, int, int, str]] = []
    for slot in AUDIT_SLOTS:
        payload = _resolve(client, slot)
        actor_ids = [group["actor_entity_id"] for group in payload["actors"]]
        for actor_id, winner in _not_hunted_winners(payload):
            subjects = [other for other in actor_ids if other != actor_id]
            if subjects:
                candidates.append((slot, actor_id, subjects[0], winner["template_id"]))
                break
    assert candidates, (
        "no audited slot yields an actor-only winner gated on "
        "NOT(has_inbound_pair_tag(hunting)) — the what-if kill test is "
        "vacuous; repoint AUDIT_SLOTS at a slot with routine/concealment "
        "winners"
    )

    for slot, actor_id, subject_id, winner_id in candidates:
        payload = _resolve(
            client,
            slot,
            overrides={
                "pair_tags": [
                    {
                        "subject_entity_id": subject_id,
                        "object_entity_id": actor_id,
                        "tag": "hunting",
                        "op": "add",
                    }
                ]
            },
        )
        assert payload["mode"] == "what_if"
        assert payload["overrides"]["scope"] == "world_state_only"
        group = next(g for g in payload["actors"] if g["actor_entity_id"] == actor_id)
        stack = group["actor_stack"]
        diff = stack["diff"]
        assert diff is not None
        assert diff["baseline_winner_id"] == winner_id
        assert winner_id in diff["changed_template_ids"]
        assert diff["changed"] is True
        assert stack["winner_id"] != winner_id
        killed = next(t for t in stack["templates"] if t["template_id"] == winner_id)
        assert killed["fired"] is False


@pytest.mark.requires_postgres
def test_what_if_need_override_reaches_stacks_and_pressures(
    client: TestClient,
) -> None:
    """Setting sleep debt sky-high must surface both in off-screen stacks
    (the sleep template firing somewhere) and, for present actors, in the
    need-pressure diff."""

    flipped_stacks = 0
    pressure_changes = 0
    for slot in AUDIT_SLOTS:
        baseline = _resolve(client, slot)
        offscreen_ids = [group["actor_entity_id"] for group in baseline["actors"]]

        engine = create_engine(get_slot_db_url(slot=slot))
        try:
            with Session(engine) as session:
                present_ids = _present_actor_ids_at_anchor(
                    session, anchor_chunk_id=baseline["anchor_chunk_id"]
                )
        finally:
            engine.dispose()

        overrides = {
            "needs": [
                {"entity_id": entity_id, "need_type": "sleep", "debt_score": 500.0}
                for entity_id in sorted(set(offscreen_ids) | set(present_ids))
            ]
        }
        if not overrides["needs"]:
            continue
        payload = _resolve(client, slot, overrides=overrides)
        assert payload["mode"] == "what_if"
        for group in payload["actors"]:
            diff = group["actor_stack"]["diff"]
            if "sleep" in diff["changed_template_ids"]:
                flipped_stacks += 1
        pressures_diff = payload["need_pressures_diff"]
        assert pressures_diff is not None
        pressure_changes += len(pressures_diff["added"]) + len(
            pressures_diff["changed"]
        )
        for draft in pressures_diff["added"]:
            assert draft["template_id"] == "sleep_need_pressure"

    assert flipped_stacks > 0, (
        "sleep debt 500 flipped no off-screen actor's sleep template on any "
        "audited slot — the stack-side what-if assertion is vacuous; repoint "
        "AUDIT_SLOTS"
    )
    assert pressure_changes > 0, (
        "sleep debt 500 changed no present actor's need pressure on any "
        "audited slot — the pressure-side what-if assertion is vacuous; "
        "repoint AUDIT_SLOTS at a slot with on-screen characters"
    )


@pytest.mark.requires_postgres
def test_what_if_validation_rejections(client: TestClient) -> None:
    payload = _resolve(client, 2)
    actor_id = payload["actors"][0]["actor_entity_id"]

    def _post(overrides: dict) -> tuple[int, str]:
        response = client.post(
            "/api/dev/orrery/resolve", json={"slot": 2, "overrides": overrides}
        )
        return response.status_code, response.json().get("detail", "")

    status, detail = _post(
        {"tags": [{"entity_id": actor_id, "tag": "definitely_not_a_tag", "op": "add"}]}
    )
    assert status == 400 and "unknown or deprecated tags" in detail

    status, detail = _post(
        {
            "pair_tags": [
                {
                    "subject_entity_id": actor_id,
                    "object_entity_id": actor_id,
                    "tag": "definitely_not_a_pair_tag",
                    "op": "add",
                }
            ]
        }
    )
    assert status == 400 and "unknown or deprecated pair tags" in detail

    status, detail = _post({"events": [{"event_type": "definitely_not_an_event"}]})
    assert status == 400 and "unknown or deprecated event types" in detail

    status, detail = _post(
        {"needs": [{"entity_id": 999_999_999, "need_type": "sleep", "debt_score": 1.0}]}
    )
    assert status == 400 and "unknown entity ids" in detail

    status, detail = _post(
        {"locations": [{"entity_id": actor_id, "place_id": 999_999_999}]}
    )
    assert status == 400 and "unknown place ids" in detail

    # Layer mismatch and no-op toggles need a real tag the actor carries.
    context = client.post(
        "/api/dev/orrery/context/entities",
        json={
            "slot": 2,
            "entity_ids": [g["actor_entity_id"] for g in payload["actors"]],
        },
    ).json()
    carried = next(
        (
            (entity["entity_id"], row["tag"])
            for entity in context["entities"]
            for row in entity["tags"]["durable"]
        ),
        None,
    )
    assert carried is not None, (
        "no audited actor on save_02 carries a durable tag — layer-mismatch "
        "and no-op rejection checks are vacuous; repoint the test"
    )
    tagged_entity, durable_tag = carried

    status, detail = _post(
        {
            "tags": [
                {
                    "entity_id": tagged_entity,
                    "tag": durable_tag,
                    "op": "add",
                    "ephemeral": True,
                }
            ]
        }
    )
    assert status == 400 and "layer" in detail

    status, detail = _post(
        {"tags": [{"entity_id": tagged_entity, "tag": durable_tag, "op": "add"}]}
    )
    assert status == 400 and "already carries it" in detail

    # Shape errors (unknown op) are Pydantic's to reject, before any DB work.
    response = client.post(
        "/api/dev/orrery/resolve",
        json={
            "slot": 2,
            "overrides": {
                "tags": [{"entity_id": actor_id, "tag": "x", "op": "toggle"}]
            },
        },
    )
    assert response.status_code == 422


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

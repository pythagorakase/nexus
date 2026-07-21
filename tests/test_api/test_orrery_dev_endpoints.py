"""Live tests for the /api/dev/orrery/* audit endpoints.

These exercise the real router over HTTP through a TestClient against real
slot databases — no mocks (see CLAUDE.md testing philosophy). The central
contract is parity: for the same anchor, the explained payload must name
exactly the winners the production ``resolve_dry_run`` selects, stack by
stack, including branch, magnitude, event type, binding hash, and the
rendered narrative stub.

save_05 is the Orrery-native live-runtime audit target. A module-wide
non-vacuity test guards against it drifting into a state where a parity block
silently runs zero iterations. All endpoints are read-only, so no cleanup is
needed.
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
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.agents.orrery.resolver import (
    OrreryTickProposal,
    _present_actor_ids_at_anchor,
    resolve_dry_run,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.orrery_dev_endpoints import router as orrery_dev_router
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings, load_settings_as_dict

LIVE_SLOT = 5
AUDIT_SLOTS = (LIVE_SLOT,)

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
                text(
                    "SELECT max(nc.id) FROM narrative_chunks nc WHERE "
                    + playable_narrative_predicate("nc")
                )
            ).scalar()
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=int(orrery["binding"]["window_chunks"]),
                sunhelm_settings=orrery.get("sunhelm"),
                selection_settings=orrery.get("selection"),
                habituation_settings=orrery.get("habituation"),
                package_selection_settings=orrery.get("package_selection"),
                project_settings=orrery.get("projects"),
                epistemics_settings=orrery.get("epistemics"),
                fanout_settings=orrery.get("fanout"),
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
    # Production drops drafts via the fan-out quota AND the project-start
    # arbitration; the endpoint reports both trim lists, and parity holds
    # only after excluding both.
    trimmed = {
        (
            item["actor_entity_id"],
            item["target_entity_id"],
            item["template_id"],
        )
        for item in payload["fanout_trimmed"]
    } | {
        (
            item["actor_entity_id"],
            item.get("target_entity_id"),
            item["template_id"],
        )
        for item in payload["project_start_arbitration_trimmed"]
    }
    endpoint_winners: dict[tuple[str, str], dict] = {}
    for group in payload["actors"]:
        for stack in [group["actor_stack"], *group["two_party_stacks"]]:
            if stack["winner_id"] is None:
                continue
            winner = _winner(stack)
            if (
                group["actor_entity_id"],
                stack["bindings"].get("target"),
                winner["template_id"],
            ) in trimmed:
                continue
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

    response = client.post("/api/dev/orrery/resolve", json={"slot": LIVE_SLOT})
    assert response.status_code == 200
    payload = response.json()
    assert payload["actors"], "save_05 is expected to bind off-screen actors"

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
    resolve = client.post("/api/dev/orrery/resolve", json={"slot": LIVE_SLOT})
    assert resolve.status_code == 200
    groups = resolve.json()["actors"]
    assert groups
    entity_ids = [groups[0]["actor_entity_id"], groups[1]["actor_entity_id"]]

    response = client.post(
        "/api/dev/orrery/context/entities",
        json={
            "slot": LIVE_SLOT,
            "entity_ids": entity_ids,
            "recent_events_limit": 3,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert [e["entity_id"] for e in payload["entities"]] == sorted(entity_ids)
    for entity in payload["entities"]:
        assert entity["name"]
        assert entity["kind"] == "character"
        for bucket in ("durable", "ephemeral"):
            for tag_row in entity["tags"][bucket]:
                # Three-tier provenance since migration 064: exact rows carry
                # the chunk bestowal key, approximate rows only a world time.
                assert tag_row["provenance"] in {
                    "exact",
                    "approximate",
                    "unknowable",
                }
                if tag_row["source_chunk_id"] is not None:
                    assert tag_row["provenance"] == "exact"
                else:
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
        assert [claim["claim_id"] for claim in entity["knowledge"]] == sorted(
            claim["claim_id"] for claim in entity["knowledge"]
        )
        for claim in entity["knowledge"]:
            assert claim["tier"] in {
                "common",
                "participant",
                "witness",
                "told",
                "granted",
            }
            for source_key in ("immediate_source", "root_source"):
                source = claim[source_key]
                if source is not None:
                    assert source["entity_id"] > 0
                    assert source["name"]
        assert len(entity["recent_events"]) <= 3
        if entity["place"] is not None:
            assert isinstance(entity["place"]["classes"], list)


@pytest.mark.requires_postgres
def test_entity_context_recent_events_respect_anchor(client: TestClient) -> None:
    """A historical anchor must not surface events from its own future."""

    resolve = client.post("/api/dev/orrery/resolve", json={"slot": LIVE_SLOT})
    assert resolve.status_code == 200
    resolved = resolve.json()
    head_anchor = resolved["anchor_chunk_id"]
    entity_ids = [group["actor_entity_id"] for group in resolved["actors"][:3]]

    at_head = client.post(
        "/api/dev/orrery/context/entities",
        json={
            "slot": LIVE_SLOT,
            "entity_ids": entity_ids,
            "anchor_chunk_id": head_anchor,
        },
    )
    assert at_head.status_code == 200
    for entity in at_head.json()["entities"]:
        for event in entity["recent_events"]:
            assert event["tick_chunk_id"] <= head_anchor

    # Anchor 0 predates every event; the honest answer is "none yet".
    at_genesis = client.post(
        "/api/dev/orrery/context/entities",
        json={"slot": LIVE_SLOT, "entity_ids": entity_ids, "anchor_chunk_id": 0},
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
    payload = _resolve(client, LIVE_SLOT)
    assert payload["mode"] == "current"
    assert payload["overrides"] is None
    assert payload["need_pressures_diff"] is None
    for _, stack in _all_stacks(payload):
        assert stack["diff"] is None

    # An explicitly empty override set is still current mode.
    empty = _resolve(client, LIVE_SLOT, overrides={})
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
    payload = _resolve(client, LIVE_SLOT)
    actor_id = payload["actors"][0]["actor_entity_id"]

    def _post(overrides: dict) -> tuple[int, str]:
        response = client.post(
            "/api/dev/orrery/resolve",
            json={"slot": LIVE_SLOT, "overrides": overrides},
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
            "slot": LIVE_SLOT,
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
        "no audited actor on save_05 carries a durable tag — layer-mismatch "
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
            "slot": LIVE_SLOT,
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
    assert set(payload["event_map"]) >= {
        "pursue_romance_started",
        "pursue_romance_progressed",
        "pursue_romance_milestone",
        "pursue_romance_stalled",
        "pursue_romance_abandoned",
        "pursue_romance_completed",
        "court_patron_started",
        "court_patron_progressed",
        "court_patron_milestone",
        "court_patron_stalled",
        "court_patron_abandoned",
        "court_patron_completed",
    }
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
        "/api/dev/orrery/coverage",
        "/api/dev/orrery/history/adjudications",
        "/api/dev/orrery/vocab",
    }


# ---------------------------------------------------------------------------
# Coverage analyzer
# ---------------------------------------------------------------------------


@pytest.mark.requires_postgres
@pytest.mark.parametrize("slot", AUDIT_SLOTS)
def test_coverage_report_is_internally_consistent(
    client: TestClient, slot: int
) -> None:
    response = client.post(
        "/api/dev/orrery/coverage", json={"slot": slot, "count": 3, "stride": 5}
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["anchor_chunk_ids"] == sorted(payload["anchor_chunk_ids"])
    assert 1 <= len(payload["anchor_chunk_ids"]) <= 3
    assert [a["anchor_chunk_id"] for a in payload["anchors"]] == payload[
        "anchor_chunk_ids"
    ]

    templates_by_id = {t.id: t for t in BUILTIN_TEMPLATES}
    assert set(payload["templates"]) == set(templates_by_id)
    total_won = 0
    for template_id, stats in payload["templates"].items():
        assert (
            stats["won"] <= stats["fired"] <= stats["gate_passed"] <= stats["evaluated"]
        ), template_id
        authored_labels = [b.label for b in templates_by_id[template_id].branches]
        assert sorted(stats["branch_chosen"]) == sorted(authored_labels)
        assert sum(stats["branch_chosen"].values()) == stats["fired"]
        assert stats["pressure_won"] <= stats["pressure_fired"], template_id
        assert stats["pressure_fired"] <= stats["pressure_evaluated"], template_id
        total_won += stats["won"]

    # Winner counts per anchor band tally must reconcile with template wins.
    band_total = sum(
        count
        for anchor in payload["anchors"]
        for count in anchor["winners_by_band"].values()
    )
    assert band_total == total_won

    # Derived lists partition consistently.
    assert not set(payload["never_fired"]) & set(payload["fired_never_won"])
    for template_id in payload["never_fired"]:
        # never_fired means no resolution-stack AND no pressure-stack firing.
        assert payload["templates"][template_id]["fired"] == 0
        assert payload["templates"][template_id]["pressure_fired"] == 0
    for template_id in payload["fired_never_won"]:
        stats = payload["templates"][template_id]
        assert stats["fired"] > 0 and stats["won"] == 0

    for gap in payload["gap_actors"]:
        assert 0 < gap["gapped_anchors"] <= gap["seen_anchors"]

    # Post-signal-emissions, only faction_realignment lacks an emitter.
    assert set(payload["dead_gate_arms"]) == {"faction_realignment"}
    assert set(payload["hydration_honesty"]) == {
        "rewound_to_anchor",
        "current_projection",
    }


@pytest.mark.requires_postgres
def test_coverage_head_anchor_reconciles_with_production(
    client: TestClient,
    production_proposals: dict[int, tuple[Optional[int], OrreryTickProposal]],
) -> None:
    """Per-anchor band tallies must equal the production resolution count."""

    for slot in AUDIT_SLOTS:
        anchor_chunk_id, proposal = production_proposals[slot]
        if anchor_chunk_id is None:
            continue
        response = client.post(
            "/api/dev/orrery/coverage",
            json={"slot": slot, "anchor_chunk_ids": [anchor_chunk_id]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        (anchor,) = payload["anchors"]
        assert anchor["anchor_chunk_id"] == anchor_chunk_id
        assert sum(anchor["winners_by_band"].values()) == len(proposal.resolutions)


@pytest.mark.requires_postgres
def test_coverage_data_quality_matches_sql_oracle(client: TestClient) -> None:
    """save_05 exhibits the NULL-world-time bestowal pathology; the health
    strip must report exactly what SQL reports."""

    response = client.post("/api/dev/orrery/coverage", json={"slot": 5, "count": 1})
    assert response.status_code == 200, response.text
    findings = response.json()["data_quality"]["null_world_time_bestowals"]

    engine = create_engine(get_slot_db_url(slot=5))
    try:
        with Session(engine) as session:
            oracle_nulls, oracle_active = session.execute(
                text(
                    """
                    SELECT count(*) FILTER (WHERE applied_at_world_time IS NULL),
                           count(*)
                    FROM entity_tags WHERE cleared_at IS NULL
                    """
                )
            ).one()
    finally:
        engine.dispose()

    tag_rows = [f for f in findings if f["bestowal_table"] == "entity_tags"]
    assert sum(f["null_world_time_rows"] for f in tag_rows) == oracle_nulls
    assert sum(f["active_rows"] for f in tag_rows) == oracle_active
    assert oracle_nulls > 0, (
        "save_05 no longer exhibits the NULL-world-time pathology — the "
        "data-quality assertion is vacuous; repoint at a slot that does"
    )


@pytest.mark.requires_postgres
def test_coverage_anchor_cap_and_sampling(client: TestClient) -> None:
    from nexus.config import load_settings_as_dict

    max_anchors = load_settings_as_dict()["orrery"]["dashboard"]["coverage_max_anchors"]

    over = client.post(
        "/api/dev/orrery/coverage",
        json={"slot": LIVE_SLOT, "count": max_anchors + 1},
    )
    assert over.status_code == 400
    assert "coverage_max_anchors" in over.json()["detail"]

    over_explicit = client.post(
        "/api/dev/orrery/coverage",
        json={
            "slot": LIVE_SLOT,
            "anchor_chunk_ids": list(range(1, max_anchors + 2)),
        },
    )
    assert over_explicit.status_code == 400

    # Stride sampling walks real chunk ids backward from the head.
    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    try:
        with Session(engine) as session:
            ids_desc = list(
                session.execute(
                    text(
                        "SELECT nc.id FROM narrative_chunks nc WHERE "
                        + playable_narrative_predicate("nc")
                        + " ORDER BY nc.id DESC LIMIT 9"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()
    expected = sorted(ids_desc[::3][:3])

    response = client.post(
        "/api/dev/orrery/coverage",
        json={"slot": LIVE_SLOT, "count": 3, "stride": 3},
    )
    assert response.status_code == 200
    assert response.json()["anchor_chunk_ids"] == expected


@pytest.mark.requires_postgres
def test_adjudication_history_endpoint_over_http(client: TestClient) -> None:
    response = client.get("/api/dev/orrery/history/adjudications?slot=5")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["totals"]["actions"]) == {"defer", "replace", "void"}
    assert (
        payload["epoch"]["log_rows_total"] >= payload["epoch"]["log_rows_with_subject"]
    )
    for streak in payload["defer_streaks"]:
        assert streak["outcome"] in {"ratified", "replace", "void", "open"}

    filtered = client.get(
        "/api/dev/orrery/history/adjudications?slot=5&template_id=surveil"
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert set(filtered_payload["templates"]) <= {"surveil"}


@pytest.mark.requires_postgres
@pytest.mark.parametrize("slot", AUDIT_SLOTS)
def test_joint_beats_parity_with_production(
    client: TestClient,
    production_proposals: dict[int, tuple[Optional[int], OrreryTickProposal]],
    slot: int,
) -> None:
    """The audit payload's joint beats must match the production post-pass."""

    anchor_chunk_id, proposal = production_proposals[slot]
    response = client.post(
        "/api/dev/orrery/resolve",
        json={"slot": slot, "anchor_chunk_id": anchor_chunk_id},
    )
    assert response.status_code == 200
    payload = response.json()
    endpoint_beats = {
        (beat["forward_proposal_id"], beat["reverse_proposal_id"])
        for beat in payload["joint_beats"]
    }
    production_beats = {
        (beat.forward_proposal_id, beat.reverse_proposal_id)
        for beat in proposal.joint_beats
    }
    assert endpoint_beats == production_beats
    for beat in payload["joint_beats"]:
        assert beat["kind"] in {"reciprocal", "crossed"}


@pytest.mark.requires_postgres
def test_vocab_endpoint_serves_picker_vocabularies(client: TestClient) -> None:
    """The what-if drawer's pickers read slot-scoped vocab from one call."""

    response = client.get(f"/api/dev/orrery/vocab?slot={LIVE_SLOT}")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"tags", "pair_tags", "event_types", "places"}
    assert payload["tags"], "tag vocabulary must be non-empty"
    tag_row = payload["tags"][0]
    assert set(tag_row) == {"tag", "category", "is_ephemeral"}
    assert {"hunting"} <= {row["tag"] for row in payload["pair_tags"]}
    assert {"threat_issued", "compliance_alert"} <= {
        row["type"] for row in payload["event_types"]
    }
    assert all(row["name"] for row in payload["places"])

"""Real TEST wizard design proofs on disposable assets.new_story_creator rows.

All services, configuration, usage, and database writes belong to this
fixture, never to an owner's slot.
"""

import ast
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import socket
import threading
import time
from typing import Any

import pytest
import requests  # type: ignore[import-untyped]
import uvicorn

from nexus.api import mock_openai
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import (
    init_cache,
    read_cache,
    read_cache_raw,
    write_cache,
)
from nexus.api.new_story_schemas import (
    Genre,
    LayerDefinition,
    LayerType,
    PlaceProfile,
    SettingCard,
    StorySeed,
    StorySeedType,
    StoryTimestamp,
    TechLevel,
    ZoneDefinition,
)
from nexus.api.wizard_confirmation import confirm_artifact
from nexus.config import load_settings
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)
from tests.scheduler_helpers import gateway_lane
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_api.test_wizard_confirmation import character_cache


@dataclass
class DesignGateway:
    """The fixture-owned endpoint and its persisted source of design data."""

    dbname: str
    source: str
    thread_id: str
    design: dict[str, Any]
    evidence_path: Path

    def post(self, endpoint: str) -> requests.Response:
        """Send the real seed-phase request and retain its exact response."""
        before = read_cache_raw(self.dbname)
        response = requests.post(
            f"http://127.0.0.1:8024{endpoint}",
            json={
                "slot": 4,
                "thread_id": self.thread_id,
                "current_phase": "seed",
                "message": "Begin at the harbor.",
            },
            timeout=90,
        )
        evidence = {
            "target": self.dbname,
            "source": self.source,
            "endpoint": endpoint,
            "status": response.status_code,
            "response": response.text,
            "before": before,
            "after": read_cache_raw(self.dbname),
        }
        self.evidence_path.write_text(json.dumps(evidence, indent=2, default=str))
        print(json.dumps(evidence, default=str), flush=True)
        return response


def _seed_source(dbname: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write validated real-Earth inputs through the production cache writer."""
    setting = SettingCard(
        genre=Genre.CONTEMPORARY,
        secondary_genres=[],
        world_name="Earth",
        time_period="June 15, 2024",
        tech_level=TechLevel.MODERN,
        magic_exists=False,
        magic_description=None,
        language_notes=None,
        political_structure="Municipal government",
        major_conflict="Harbor workers face the closure of their repair yard.",
        tone="balanced",
        themes=["duty", "community"],
        cultural_notes="Baltimore dockworkers keep their neighborhood connected.",
        geographic_scope="regional",
        diegetic_artifact=(
            "Baltimore Harbor Notice, June 15, 2024: The repair yard opens at dawn. "
            "Workers must report damaged equipment before the next ship arrives."
        ),
    ).model_dump(mode="json")
    seed = StorySeed(
        seed_type=StorySeedType.DISCOVERY,
        title="The Harbor Bell",
        situation="Mara finds a damaged harbor crane before the morning shift.",
        hook="An unsigned warning links the damage to the planned yard closure.",
        immediate_goal="Inspect the crane before the workers arrive.",
        stakes="The workers' safety and the future of the repair yard.",
        tension_source="The foreman wants the dock reopened immediately.",
        base_timestamp=StoryTimestamp(
            year=2024, month=6, day=15, hour=8, minute=0, second=0
        ),
        weather="Clear morning",
        key_npcs=["The harbor foreman"],
        secrets="The crane was disabled by someone trying to delay the closure.",
    )
    design = {
        "layer": LayerDefinition(
            name="Earth",
            type=LayerType.PLANET,
            description="The real Earth in the year 2024.",
        ).model_dump(mode="json"),
        "zone": ZoneDefinition(
            name="Baltimore Harbor",
            summary="Baltimore's working waterfront in Maryland.",
        ).model_dump(mode="json"),
        "location": PlaceProfile(
            name="Baltimore Inner Harbor",
            place_type="fixed_location",
            extra_data=None,
            summary=(
                "A busy waterfront where harbor workers gather beside the repair dock."
            ),
            history="The waterfront has supported generations of Baltimore workers.",
            current_status="The morning shift is gathering beside the damaged crane.",
            secrets="A warning note is tucked behind the crane's control panel.",
            inhabitants=["Harbor workers"],
            latitude=39.285,
            longitude=-76.61,
        ).model_dump(mode="json"),
    }
    write_cache(
        dbname=dbname,
        setting_draft=setting,
        character_draft=character_cache().get_character_state_dict(),
        selected_seed=seed.model_dump(mode="json"),
        base_timestamp=seed.get_base_datetime().isoformat(),
        layer_draft=design["layer"],
        zone_draft=design["zone"],
        initial_location=design["location"],
    )
    return setting, design


@pytest.fixture
def design_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[DesignGateway]:
    """Serve the registered TEST app and gateway on separately owned sockets."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        assert port > 8013 and port != 8024
        listener.listen()
        configure_test(tmp_path, f"http://127.0.0.1:{port}/v1", monkeypatch)
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8024")
        monkeypatch.setenv("NEXUS_API_URL", "http://127.0.0.1:8024")
        with (
            disposable_slot_database("qa640_840s3a_slot") as dbname,
            disposable_slot_database("qa640_840s3a_source") as source,
        ):
            with monkeypatch.context() as source_route:
                route_slot_to_disposable(source_route.setattr, slot=4, dbname=source)
                setting, design = _seed_source(source)
            route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
            monkeypatch.setenv("NEXUS_SLOT", "4")
            monkeypatch.setattr(mock_openai, "MOCK_DB", source)
            model = load_settings().wizard.default_model
            assert load_settings().is_test_model(model)
            client = ConversationsClient(model=model)
            thread_id = client.create_thread()
            try:
                init_cache(dbname, thread_id, 4)
                write_cache(
                    dbname=dbname,
                    setting_draft=setting,
                    character_draft=character_cache().get_character_state_dict(),
                )
                for phase in ("setting", "character"):
                    cache = read_cache(dbname)
                    assert cache is not None
                    token = cache.artifact_token(phase)
                    assert token is not None
                    confirm_artifact(
                        dbname, thread_id=thread_id, phase=phase, artifact_token=token
                    )
                cache = read_cache(dbname)
                assert cache is not None and cache.current_phase() == "seed"
                assert cache.phase_untouched()
                server = uvicorn.Server(
                    uvicorn.Config(mock_openai.app, log_level="warning")
                )
                thread = threading.Thread(
                    target=server.run, kwargs={"sockets": [listener]}
                )
                thread.start()
                try:
                    deadline = time.monotonic() + 15
                    while (
                        not server.started
                        and thread.is_alive()
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    assert server.started, "Fixture TEST server failed to start"
                    with gateway_lane(monkeypatch):
                        yield DesignGateway(
                            dbname,
                            source,
                            thread_id,
                            design,
                            tmp_path / "response.json",
                        )
                finally:
                    server.should_exit = True
                    thread.join(timeout=30)
                    assert not thread.is_alive(), "Fixture TEST server did not stop"
            finally:
                client.delete_thread(thread_id)


@pytest.mark.requires_postgres
@pytest.mark.parametrize("endpoint", ["/api/story/new/chat"])
def test_successful_set_design_still_persists_and_returns_artifact(
    design_gateway: DesignGateway, endpoint: str
) -> None:
    """The real seed tool and set designer return the committed artifact."""
    response = design_gateway.post(endpoint)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase_complete"] is True, response.text
    assert body["artifact_type"] == "submit_starting_scenario"
    assert body["set_design"] == design_gateway.design
    assert "error" not in body and "set_design_error" not in response.text
    cache = read_cache(design_gateway.dbname)
    assert cache is not None and cache.seed_complete()
    raw = read_cache_raw(design_gateway.dbname)
    assert raw is not None
    for field in ("name", "type", "description"):
        assert raw[f"layer_{field}"] == design_gateway.design["layer"][field]
    for field in ("name", "summary"):
        assert raw[f"zone_{field}"] == design_gateway.design["zone"][field]
    assert raw["initial_location"] == design_gateway.design["location"]
    for key, value in cache.confirmation_metadata().items():
        assert body[key] == value


@pytest.mark.requires_postgres
def test_chat_set_design_write_failure_returns_500_without_design_draft(
    design_gateway: DesignGateway,
) -> None:
    """A rejected design UPDATE leaves the seed but none of the design draft."""
    with closing(connect(design_gateway.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE assets.new_story_creator ADD CONSTRAINT "
            "qa840_reject_set_design CHECK (layer_name IS NULL)"
        )
        cur.execute(
            "COMMENT ON CONSTRAINT qa840_reject_set_design "
            "ON assets.new_story_creator IS "
            "'Test fault: reject the complete set-design UPDATE atomically.'"
        )
    response = design_gateway.post("/api/story/new/chat")
    assert response.status_code == 500, response.text
    assert "qa840_reject_set_design" in response.json()["detail"]
    assert "set_design_error" not in response.text
    raw = read_cache_raw(design_gateway.dbname)
    assert raw is not None
    design_fields = {
        key: value
        for key, value in raw.items()
        if key.startswith(("layer_", "zone_")) or key == "initial_location"
    }
    assert len(design_fields) == 8, design_fields
    assert all(value is None for value in design_fields.values()), design_fields
    cache = read_cache(design_gateway.dbname)
    assert cache is not None
    assert cache.seed.title == "The Harbor Bell"
    assert cache.seed.seed_type == "discovery"
    assert cache.base_timestamp is not None
    assert not cache.seed_complete()
    assert cache.current_phase() == "seed"


def test_neither_provider_branch_swallows_set_design_errors() -> None:
    """Both branches reach the boundary, including unexercised production."""
    path = Path(__file__).resolve().parents[2] / "nexus/api/wizard_chat.py"
    source = path.read_text()
    assert "set_design_error" not in source
    tree = ast.parse(source)
    expected = {
        "query_wizard_cache": 1,
        "generate_set_design": 1,
        "_record_set_design": 2,
    }
    found = dict.fromkeys(expected, 0)
    for endpoint_name in ("new_story_chat_endpoint",):
        endpoint = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == endpoint_name
        )
        parents = {
            child: parent
            for parent in ast.walk(endpoint)
            for child in ast.iter_child_nodes(parent)
        }
        outer_boundary = next(
            (node for node in endpoint.body if isinstance(node, ast.Try)), None
        )
        for node in ast.walk(endpoint):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in expected
            ):
                continue
            found[node.func.id] += 1
            ancestor = parents.get(node)
            while ancestor is not None:
                if isinstance(ancestor, (ast.Try, ast.TryStar)):
                    assert (
                        endpoint_name == "new_story_chat_endpoint"
                        and ancestor is outer_boundary
                    ), f"{node.func.id}:{node.lineno} is inside an inner Try"
                ancestor = parents.get(ancestor)
    assert found == expected

"""Offline place-reference proofs through the production two-pass boundary.

The archived Machine-Shop failure has no retained model payload. These are
explicit regression fixtures for the independently reproduced validation gap.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

import httpx
import pytest
from openai import OpenAI
from pydantic_ai import ModelRetry

from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldWriterWire,
    combine_two_pass,
    hydrate_skald_turn,
)
from nexus.api.native_structured_output import WireContractViolation
from nexus.presence.roster import resolve_place_update
from scripts import api_openai
from tests.test_lore.test_two_pass_pipeline import (
    BASELINE,
    GAIA_PAYLOAD,
    WRITER_PAYLOAD,
    _context,
    _utility,
)


class PlaceCatalog:
    """Read-only SQL seam; production name, alias, and ID resolution runs intact."""

    def __init__(self, places=None, aliases=None):
        self.places = places or {9: "The Lower Sluice"}
        self.aliases = aliases or {"sluice": 9}
        self.rows: list[tuple[Any, ...]] = []
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self

    def execute(self, query, params=()):
        self.queries.append(query)
        if "to_regclass" in query:
            self.rows = [("place_aliases",)]
        elif "FROM places WHERE id" in query:
            self.rows = [
                (key, name) for key, name in self.places.items() if key == params[0]
            ]
        elif "FROM places p WHERE" in query:
            name = params[0].lower()
            self.rows = [
                (key, canonical)
                for key, canonical in self.places.items()
                if canonical.lower() == name or self.aliases.get(name) == key
            ]
        else:
            raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def writer_payload(site="mentions", *, name="Machine-Shop", identifier=None):
    """Place the same new identity in each writer-owned reference surface."""
    payload = deepcopy(WRITER_PAYLOAD)
    ref = {"kind": "place", "name": name, "id": identifier}
    payload["narrative"] = "The Machine-Shop stands beyond the gate."
    payload["presence"] = (
        {"scene_reset": {"place": ref, "present": []}}
        if site == "scene_reset"
        else {site: [ref]}
    )
    return payload


def gaia_payload(*, declared=False):
    """Gaia can repair the declaration without changing the finished writer."""
    return {
        "new_entities": (
            [
                {
                    "kind": "place",
                    "name": "Machine-Shop",
                    "summary": "The workshop beyond the gate.",
                }
            ]
            if declared
            else []
        ),
        "letter": GAIA_PAYLOAD["letter"],
    }


@pytest.fixture
def catalog(monkeypatch):
    """Block every database connection behind one deterministic catalog."""
    from nexus.api import db_pool
    from nexus.agents.lore.logon_utility import LogonUtility

    catalog = PlaceCatalog()
    monkeypatch.setattr(db_pool, "get_connection", lambda _dbname: catalog)
    monkeypatch.setattr(LogonUtility, "_load_setting_context", lambda self: None)
    return catalog


def configure_utility(monkeypatch, outputs, *, retries=1):
    """Use real pass composition and native-validator retry semantics offline."""
    utility, provider = _utility("openai", outputs, structured_output_retries=retries)
    utility._validation_dbname = "private_fixture"
    monkeypatch.setattr(
        utility, "_read_presence_baseline_for_context", lambda *args: BASELINE
    )

    async def baseline(*args):
        return BASELINE

    monkeypatch.setattr(utility, "_read_presence_baseline_for_context_async", baseline)
    return utility, provider


@pytest.mark.parametrize("site", ["mentions", "transit", "scene_reset"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_two_pass_repairs_missing_writer_place_before_hydration(
    monkeypatch, catalog, site, asynchronous
):
    """A reference-only new place must reach Gaia repair before accepted output."""
    original = writer_payload(site)
    utility, provider = configure_utility(
        monkeypatch, [original, gaia_payload(), gaia_payload(declared=True)]
    )
    response = (
        asyncio.run(
            utility.generate_narrative_async(
                _context(), effective_context_window=75_000
            )
        )
        if asynchronous
        else utility.generate_narrative(_context(), effective_context_window=75_000)
    )
    assert len(provider.calls) == 3
    assert provider.outputs == []
    assert "Machine-Shop" in provider.calls[-1]["prompt"]
    assert "new_entities" in provider.calls[-1]["prompt"]
    assert "Do not fabricate an ID" in provider.calls[-1]["prompt"]
    assert response.narrative == original["narrative"]
    assert any(
        ref.place_name == "Machine-Shop" and ref.place_id is None
        for ref in response.referenced_entities.places
    )
    assert [declaration.name for declaration in response.new_entities] == [
        "Machine-Shop"
    ]
    assert response.state_updates.locations == []


def test_missing_writer_place_exhausts_repair_without_hydration(monkeypatch, catalog):
    utility, provider = configure_utility(
        monkeypatch, [writer_payload(), gaia_payload(), gaia_payload()]
    )
    monkeypatch.setattr(
        utility,
        "_hydrate_provider_response",
        lambda *args, **kwargs: pytest.fail("Must not hydrate rejected Gaia"),
    )
    with pytest.raises(ModelRetry, match="Machine-Shop"):
        utility.generate_narrative(_context(), effective_context_window=75_000)
    assert len(provider.calls) == 3


@pytest.mark.parametrize(
    "name,identifier",
    [("The Lower Sluice", None), ("Sluice", None), ("Writer display label", 10)],
)
def test_existing_place_and_alias_or_authoritative_id_need_no_declaration(
    monkeypatch, catalog, name, identifier
):
    catalog.places[10] = "Known Workshop"
    utility, provider = configure_utility(
        monkeypatch, [writer_payload(name=name, identifier=identifier), gaia_payload()]
    )
    response = utility.generate_narrative(_context(), effective_context_window=75_000)
    assert len(provider.calls) == 2
    assert response.new_entities == []
    # Validation does not rewrite the finished writer's reference or prose.
    assert any(
        ref.place_name == name and ref.place_id == identifier
        for ref in response.referenced_entities.places
    )


@pytest.mark.parametrize("case", ["invalid_id", "ambiguous", "disabled"])
def test_unrepairable_writer_identity_fails_closed(monkeypatch, catalog, case):
    payload = writer_payload(identifier=987 if case == "invalid_id" else None)
    if case == "ambiguous":
        catalog.places = {1: "Machine-Shop", 2: "MACHINE-SHOP"}
    utility, provider = configure_utility(
        monkeypatch, [payload, gaia_payload(declared=True)]
    )
    if case == "disabled":
        utility.settings["orrery"] = {"retrograde": {"maturation": {"enabled": False}}}
    with pytest.raises(WireContractViolation):
        utility.generate_narrative(_context(), effective_context_window=75_000)
    assert len(provider.calls) == 2


def test_combined_reference_reproduces_the_staging_resolver_failure():
    """The previous combination succeeds although the reference cannot stage."""
    combined = combine_two_pass(
        SkaldWriterWire.model_validate(writer_payload()),
        SkaldGaiaWire.model_validate(gaia_payload()),
    )
    hydrated = hydrate_skald_turn(combined, presence_baseline=BASELINE)
    missing = next(
        ref
        for ref in hydrated.referenced_entities.places
        if ref.place_name == "Machine-Shop"
    )
    with pytest.raises(
        WireContractViolation, match="Unresolved place state update name 'Machine-Shop'"
    ):
        resolve_place_update(
            PlaceCatalog(), identifier=missing.place_id, name=missing.place_name
        )


def test_single_pass_validator_also_requires_place_declarations(monkeypatch, catalog):
    """The combined wire is checked at its native boundary, not just two-pass."""
    from nexus.agents.logon import orrery_tag_validation

    monkeypatch.setattr(
        orrery_tag_validation,
        "read_storyteller_vocabulary",
        lambda _dbname: orrery_tag_validation.StorytellerVocabulary(
            tag_names_by_kind={}, pair_tag_names=frozenset(), event_types=frozenset()
        ),
    )
    validator = orrery_tag_validation.build_storyteller_tag_validator(
        "private_fixture", allow_same_turn_faction_declarations=True
    )
    writer = SkaldWriterWire.model_validate(writer_payload())
    missing = combine_two_pass(writer, SkaldGaiaWire.model_validate(gaia_payload()))
    with pytest.raises(ModelRetry, match="Machine-Shop"):
        asyncio.run(validator(None, missing))
    declared = combine_two_pass(
        writer, SkaldGaiaWire.model_validate(gaia_payload(declared=True))
    )
    assert asyncio.run(validator(None, declared)) is declared


@pytest.mark.parametrize("repair", [False, True])
def test_real_openai_transport_accounts_rejected_reference_before_acceptance(
    monkeypatch, catalog, repair
):
    """Exercise SDK parsing, native validation, and accounting without a network."""
    payloads = [gaia_payload(), gaia_payload(declared=repair)]
    requests = []
    outcomes = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": f"resp_fixture_{len(requests)}",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "TEST",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fixture",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(payloads.pop(0)),
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    utility, _ = configure_utility(monkeypatch, [])
    provider = api_openai.OpenAIProvider(
        model="TEST", api_key="offline-fixture", structured_output_retries=1
    )
    provider.client = OpenAI(
        api_key="offline-fixture",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    provider.output_validator = utility._build_gaia_place_validator(
        SkaldWriterWire.model_validate(writer_payload())
    )
    monkeypatch.setattr(
        api_openai,
        "record_openai_response",
        lambda *args, **kwargs: outcomes.append(kwargs["outcome"]),
    )
    try:
        if repair:
            parsed, _ = provider.get_structured_completion(
                "Gaia fixture", SkaldGaiaWire
            )
            assert parsed.new_entities[0].name == "Machine-Shop"
            assert outcomes == ["rejected_validation", "accepted"]
        else:
            with pytest.raises(ModelRetry, match="Machine-Shop"):
                provider.get_structured_completion("Gaia fixture", SkaldGaiaWire)
            assert outcomes == ["rejected_validation", "rejected_validation"]
        assert len(requests) == 2
        assert "Machine-Shop" in json.dumps(requests[1])
    finally:
        provider.client.close()

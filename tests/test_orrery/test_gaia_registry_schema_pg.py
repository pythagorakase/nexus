"""Registry-backed Gaia grammar integration and live OpenAI gate.

PostgreSQL checks use a disposable ``qa638_*`` clone of ``NEXUS_template``.
The real inference gate additionally requires ``NEXUS_RUN_LIVE_LLM=1`` and
``NEXUS_638_ENUM_E2E=1``.
"""

from __future__ import annotations


import json
import os
from typing import Any, Iterator
import uuid

import pytest
from psycopg2 import sql
from pydantic import ValidationError

from nexus.agents.logon.gaia_registry_schema import (
    coerce_gaia_registry_wire,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    PlaceRef,
    PresenceBaseline,
    SkaldGaiaWire,
    skald_gaia_strict_text_format,
)
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api import slot_utils
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.config import load_settings
from nexus.config.story_model import StorySettings
from scripts.api_openai import OpenAIProvider
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_zone,
)


# Measured against the shipped NEXUS_template registry on 2026-07-30:
# 24,321 bytes / 5,982 o200k tokens. The byte and token ceilings retain
# ~10% headroom. The post-#916 registry has 625 enum values. #811 slice B
# removes the 97 live tags under deprecated registry categories from the
# add/hint enums; a scene's clear-only enums carry only the ones its present
# entities still hold, and a fresh clone has none, so the count is 528
# (23,846 bytes / 5,806 tokens on 2026-09-30).
GAIA_REGISTRY_STRICT_MAX_BYTES = 26_800
GAIA_REGISTRY_STRICT_MAX_TOKENS = 6_600
GAIA_REGISTRY_STRICT_ENUM_VALUE_COUNT = 528

# Current OpenAI Structured Outputs documentation:
# https://developers.openai.com/api/docs/guides/structured-outputs
OPENAI_SCHEMA_ENUM_VALUE_LIMIT = 1_000
OPENAI_LARGE_ENUM_VALUE_THRESHOLD = 250
OPENAI_LARGE_ENUM_STRING_LENGTH_LIMIT = 15_000


def _connect(dbname: str) -> Any:
    return connect(dbname)


@pytest.fixture(scope="module")
def qa638_registry_db() -> Iterator[str]:
    """Create and drop one isolated clone carrying the shipped registries."""

    dbname = f"qa638_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        VALID_DBNAMES.add(dbname)
        yield dbname
    finally:
        VALID_DBNAMES.discard(dbname)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
            )
        admin.close()


def _enum_values(definition: dict[str, Any]) -> set[str]:
    values = definition.get("enum")
    if isinstance(values, list):
        return {str(value) for value in values}
    if "const" in definition:
        return {str(definition["const"])}
    raise AssertionError(f"Definition is not an enum: {definition!r}")


def _array_item_refs(property_schema: dict[str, Any]) -> list[str]:
    candidates = property_schema.get("anyOf") or [property_schema]
    array_schema = next(
        candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("type") == "array"
    )
    items = array_schema["items"]
    return [str(item["$ref"]) for item in items.get("anyOf") or [items]]


def _all_enum_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("enum"), list):
            nodes.append(value)
        for nested in value.values():
            nodes.extend(_all_enum_nodes(nested))
    elif isinstance(value, list):
        for nested in value:
            nodes.extend(_all_enum_nodes(nested))
    return nodes


@pytest.mark.requires_postgres
def test_gaia_grammar_exactly_matches_clone_validator_partitions(
    qa638_registry_db: str,
) -> None:
    spec = load_gaia_registry_wire_spec(qa638_registry_db)
    repeated = load_gaia_registry_wire_spec(qa638_registry_db)
    schema = skald_gaia_strict_text_format(spec.model)["schema"]
    definitions = schema["$defs"]
    vocabulary = spec.vocabulary

    assert repeated.model is spec.model
    assert issubclass(spec.model, SkaldGaiaWire)
    expected = {
        "CharacterTagName": set(vocabulary.tag_names_by_kind["character"]),
        "PlaceTagName": set(vocabulary.tag_names_by_kind["place"]),
        "FactionTagName": set(vocabulary.tag_names_by_kind["faction"]),
        "PairTagName": set(vocabulary.pair_tag_names),
        "EventTypeName": set(vocabulary.event_types),
    }
    for definition_name, values in expected.items():
        assert _enum_values(definitions[definition_name]) == values
    # No scene, so no clear-only enum: the fresh clone's deprecated-category
    # tags are active nowhere, and the grammar offers only what a scene shows.
    assert not [name for name in definitions if "ClearOnly" in name]

    for model_name, definition_name in (
        ("CharacterUpdateDeltaRegistry", "CharacterTagName"),
        ("PlaceUpdateDeltaRegistry", "PlaceTagName"),
        ("FactionUpdateDeltaRegistry", "FactionTagName"),
    ):
        properties = definitions[model_name]["properties"]
        for field_name in ("tags_add", "tags_clear"):
            assert _array_item_refs(properties[field_name]) == [
                f"#/$defs/{definition_name}"
            ]

    for model_name, kind, definition_name in (
        (
            "CharacterNewEntityDeclarationRegistry",
            "character",
            "CharacterTagName",
        ),
        ("PlaceNewEntityDeclarationRegistry", "place", "PlaceTagName"),
        (
            "FactionNewEntityDeclarationRegistry",
            "faction",
            "FactionTagName",
        ),
    ):
        declaration = definitions[model_name]["properties"]
        assert declaration["kind"]["const"] == kind
        assert declaration["tag_hints"]["items"]["$ref"] == f"#/$defs/{definition_name}"
    assert (
        definitions["NewEntityPairTagHintRegistry"]["properties"]["tag"]["$ref"]
        == "#/$defs/PairTagName"
    )
    assert (
        definitions["OrreryAdjudicationRegistry"]["properties"][
            "replacement_event_type"
        ]["anyOf"][0]["$ref"]
        == "#/$defs/EventTypeName"
    )

    replacement = definitions["OrreryReplacementStateDelta"]["properties"]
    for field_name in (
        "entity_tags_add",
        "entity_tags_remove",
        "entity_tags_target_add",
        "entity_tags_target_remove",
        "entity_pair_tags_target_clear_inbound",
    ):
        assert replacement[field_name]["items"] == {"type": "string"}


@pytest.mark.requires_postgres
def test_gaia_registry_strict_schema_stays_within_measured_budget_and_limits(
    qa638_registry_db: str,
) -> None:
    tiktoken = pytest.importorskip("tiktoken")
    encoding = tiktoken.get_encoding("o200k_base")
    spec = load_gaia_registry_wire_spec(qa638_registry_db)
    static_schema = skald_gaia_strict_text_format()["schema"]
    registry_schema = skald_gaia_strict_text_format(spec.model)["schema"]
    static_wire = json.dumps(
        static_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    registry_wire = json.dumps(
        registry_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    static_tokens = len(encoding.encode(static_wire))
    registry_tokens = len(encoding.encode(registry_wire))
    registry_bytes = len(registry_wire.encode("utf-8"))
    enum_nodes = _all_enum_nodes(registry_schema)
    enum_value_count = sum(len(node["enum"]) for node in enum_nodes)
    enum_value_headroom = OPENAI_SCHEMA_ENUM_VALUE_LIMIT - enum_value_count

    print(
        "Gaia strict schema measurement: "
        f"static={len(static_wire.encode('utf-8'))} bytes/{static_tokens} tokens; "
        f"registry={registry_bytes} bytes/{registry_tokens} tokens; "
        f"enum_values={enum_value_count}/{OPENAI_SCHEMA_ENUM_VALUE_LIMIT} "
        f"({enum_value_headroom} headroom)"
    )
    assert registry_bytes <= GAIA_REGISTRY_STRICT_MAX_BYTES
    assert registry_tokens <= GAIA_REGISTRY_STRICT_MAX_TOKENS
    assert enum_value_count == GAIA_REGISTRY_STRICT_ENUM_VALUE_COUNT
    assert enum_value_headroom >= 0
    for node in enum_nodes:
        values = [str(value) for value in node["enum"]]
        if len(values) > OPENAI_LARGE_ENUM_VALUE_THRESHOLD:
            assert sum(len(value) for value in values) <= (
                OPENAI_LARGE_ENUM_STRING_LENGTH_LIMIT
            )


def _clear_only_values(schema_model: type[SkaldGaiaWire], name: str) -> set[str]:
    definitions = skald_gaia_strict_text_format(schema_model)["schema"]["$defs"]
    if name not in definitions:
        return set()
    return _enum_values(definitions[name])


@pytest.mark.requires_postgres
def test_turn_grammar_offers_a_deprecated_tag_only_when_a_present_entity_has_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn's Gaia grammar clears ``worksite`` only while the scene shows it.

    ``worksite`` sits under the deprecated ``place_affordance`` category. The
    first place carries it; the second does not. LOGON's own schema selection
    reads the turn's present entities (cast, setting, player) from the
    presence baseline, so the clear-only enum follows the setting.
    """

    with disposable_slot_database("qa640_811_gaia_scene") as dbname:
        monkeypatch.setattr(
            slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
        )
        seed_zone(
            dbname,
            name="Harbor Ward",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        carrying, carrying_entity = seed_place(dbname, name="Dry Dock Nine")
        bare, _ = seed_place(dbname, name="Lamplighter Row", longitude=-73.95)
        seed_protagonist(dbname)
        seed_entity_tag(dbname, entity_id=carrying_entity, tag="worksite")

        settings = load_settings()
        assert settings.apex.tag_library.schema_enums is True
        utility = LogonUtility(
            settings,
            dbname=dbname,
            model_override="TEST",
            story_settings=StorySettings(),
        )
        utility._validation_dbname = dbname

        def turn_model(place_id: int, name: str) -> type[SkaldGaiaWire]:
            return utility._gaia_schema_model(
                "openai",
                presence_baseline=PresenceBaseline(
                    setting=PlaceRef(kind="place", name=name, id=place_id)
                ),
            )

        present = turn_model(carrying, "Dry Dock Nine")
        absent = turn_model(bare, "Lamplighter Row")

        assert _clear_only_values(present, "PlaceClearOnlyTagName") == {"worksite"}
        assert _clear_only_values(absent, "PlaceClearOnlyTagName") == set()
        for schema_model in (present, absent):
            definitions = skald_gaia_strict_text_format(schema_model)["schema"]["$defs"]
            assert "worksite" not in _enum_values(definitions["PlaceTagName"])
            assert "CharacterClearOnlyTagName" not in definitions
            assert "FactionClearOnlyTagName" not in definitions

        def payload(place_id: int, field_name: str) -> dict[str, Any]:
            return {
                "letter": "Clear what the scene still shows.",
                "new_entities": [],
                "orrery_adjudications": [],
                "updates": {
                    "characters": [],
                    "places": [
                        {
                            "id": place_id,
                            "name": "Dry Dock Nine",
                            field_name: ["worksite"],
                        }
                    ],
                    "factions": [],
                    "relationships": [],
                },
            }

        cleared = coerce_gaia_registry_wire(
            present.model_validate(payload(carrying, "tags_clear"))
        )
        assert cleared.updates is not None
        assert cleared.updates.places[0].tags_clear == ["worksite"]
        with pytest.raises(ValidationError):
            present.model_validate(payload(carrying, "tags_add"))
        with pytest.raises(ValidationError):
            absent.model_validate(payload(carrying, "tags_clear"))


@pytest.mark.live
@pytest.mark.live_llm
@pytest.mark.requires_postgres
@pytest.mark.skipif(
    os.environ.get("NEXUS_638_ENUM_E2E") != "1",
    reason="Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.",
)
def test_live_openai_accepts_registry_gaia_strict_schema(
    qa638_registry_db: str,
) -> None:
    from nexus.config import load_settings

    settings = load_settings()
    model = settings.resolve_model_ref(
        os.environ.get("NEXUS_638_ENUM_MODEL_REF", settings.apex.gaia_model)
    )
    if settings.provider_for_model(model) != "openai":
        pytest.fail("NEXUS_638_ENUM_MODEL_REF must name a registered OpenAI model")
    spec = load_gaia_registry_wire_spec(qa638_registry_db)
    text_format = skald_gaia_strict_text_format(spec.model)
    assert "CharacterTagName" in text_format["schema"]["$defs"]

    provider = OpenAIProvider(
        model=model,
        max_output_tokens=1_000,
        reasoning_effort="low",
        structured_output_retries=0,
        usage_seat="gaia_schema_e2e",
    )
    parsed, _response = provider.get_structured_completion(
        (
            "Return a minimal Gaia state record proving this schema is accepted. "
            "Use updates=null, no adjudications, no new entities, and the short "
            "letter 'Registry enum schema accepted.'"
        ),
        spec.model,
        text_format=text_format,
    )

    assert isinstance(parsed, SkaldGaiaWire)
    static = coerce_gaia_registry_wire(parsed)
    assert static.updates is None
    assert static.orrery_adjudications == []
    assert static.new_entities == []
    assert static.letter

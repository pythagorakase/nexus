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

import psycopg2
import pytest
from psycopg2 import sql

from nexus.agents.logon.gaia_registry_schema import (
    coerce_gaia_registry_wire,
    load_gaia_registry_wire_spec,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    skald_gaia_strict_text_format,
)
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.config import resolve_model_ref
from scripts.api_openai import OpenAIProvider


# Measured against the shipped NEXUS_template registry on 2026-07-30:
# 24,321 bytes / 5,982 o200k tokens / 626 enum values. The byte and token
# ceilings retain ~10% headroom.
GAIA_REGISTRY_STRICT_MAX_BYTES = 26_800
GAIA_REGISTRY_STRICT_MAX_TOKENS = 6_600
GAIA_REGISTRY_STRICT_ENUM_VALUE_COUNT = 626

# Current OpenAI Structured Outputs documentation:
# https://developers.openai.com/api/docs/guides/structured-outputs
OPENAI_SCHEMA_ENUM_VALUE_LIMIT = 1_000
OPENAI_LARGE_ENUM_VALUE_THRESHOLD = 250
OPENAI_LARGE_ENUM_STRING_LENGTH_LIMIT = 15_000


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


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


def _array_item_ref(property_schema: dict[str, Any]) -> str:
    candidates = property_schema.get("anyOf") or [property_schema]
    array_schema = next(
        candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("type") == "array"
    )
    return str(array_schema["items"]["$ref"])


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

    for model_name, definition_name in (
        ("CharacterUpdateDeltaRegistry", "CharacterTagName"),
        ("PlaceUpdateDeltaRegistry", "PlaceTagName"),
        ("FactionUpdateDeltaRegistry", "FactionTagName"),
    ):
        for field_name in ("tags_add", "tags_clear"):
            assert (
                _array_item_ref(definitions[model_name]["properties"][field_name])
                == f"#/$defs/{definition_name}"
            )

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
    model_ref = os.environ.get("NEXUS_638_ENUM_MODEL_REF", "@openai.gaia")
    if not model_ref.startswith("@openai."):
        pytest.fail("NEXUS_638_ENUM_MODEL_REF must be an @openai.<role> reference")
    model = resolve_model_ref(model_ref)
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

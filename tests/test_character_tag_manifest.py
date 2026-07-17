"""Tests for character tag migration manifest helpers."""

from argparse import Namespace
from typing import Any

import psycopg2  # type: ignore[import-untyped]
import pytest

from nexus import cli
from nexus.api.character_tag_manifest import (
    CHARACTER_MANIFEST_SCHEMA_VERSION,
    build_character_migration_manifest_from_rows,
)
from nexus.api.db_pool import close_pool


TEST_DBNAME = "save_02"


def test_character_manifest_canonicalizes_resolved_collision_names() -> None:
    """Legacy rows should target the resolved physical tag names."""

    manifest = build_character_migration_manifest_from_rows(
        [
            _row(tag="bodyform:android", category="bodyform"),
            _row(tag="traditionalist", category="disposition"),
            _row(tag="hunter", category="capacity"),
            _row(tag="contacts_available", category="orrery_state"),
            _row(tag="uploaded_consciousness", category="bodyform"),
        ],
        registered_tags={
            "inorganic": {"category": "bodyform.lineage"},
            "tradition_bound": {"category": "disposition"},
            "hunter": {"category": "role.function"},
        },
        slot=2,
        dbname="save_02",
    )

    operations = {
        operation["source"]["tag"]: operation for operation in (manifest["operations"])
    }

    assert manifest["schema_version"] == CHARACTER_MANIFEST_SCHEMA_VERSION
    assert manifest["counters"]["legacy_character_tag_rows"] == 5
    assert manifest["counters"]["review_required_operations"] == 5
    assert operations["bodyform:android"]["target"]["tag"] == "inorganic"
    assert operations["bodyform:android"]["target"]["entity_id"] == 1042
    assert operations["bodyform:android"]["target"]["category"] == ("bodyform.lineage")
    assert operations["traditionalist"]["target"]["tag"] == "tradition_bound"
    assert operations["hunter"]["target"]["category"] == "role.function"
    assert operations["contacts_available"]["operation_type"] == (
        "resolve_pair_tag_target"
    )
    assert operations["contacts_available"]["target"]["object_entity_id"] == 1042
    assert operations["uploaded_consciousness"]["operation_type"] == "preserve_prose"


def test_character_manifest_reports_missing_target_tags() -> None:
    """Unknown legacy rows remain review items instead of inventing vocabulary."""

    manifest = build_character_migration_manifest_from_rows(
        [_row(tag="black_market_operator", category="profession_lite")],
        registered_tags={},
        slot=2,
        dbname="save_02",
    )

    operation = manifest["operations"][0]
    assert operation["operation_type"] == "review_entity_tag"
    assert operation["target"]["target_registered"] is False
    assert manifest["counters"]["missing_target_tag_operations"] == 1


def test_cli_character_apply_requires_manifest_for_execute() -> None:
    """Execute mode must consume a reviewed manifest."""

    result = cli.run_character_apply(
        Namespace(slot=2, execute=True, manifest=None, source_kind="system")
    )

    assert result["success"] is False
    assert "--manifest is required with --execute" in result["error"]


@pytest.mark.requires_postgres
def test_cli_character_manifest_returns_live_slot2_payload() -> None:
    """CLI character-manifest should read the slot and return a manifest."""

    try:
        result = cli.run_character_manifest(Namespace(slot=2, output=None))
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    finally:
        close_pool(TEST_DBNAME)

    assert result["success"] is True
    assert result["character_manifest"]["schema_version"] == (
        CHARACTER_MANIFEST_SCHEMA_VERSION
    )
    assert result["character_manifest"]["dry_run"] is True
    assert result["character_manifest"]["source"]["slot"] == 2


# Slot-2 retrofit live coverage was retired by owner order on 2026-07-17;
# the tooling remains available for any future legacy import.


def _row(
    *,
    tag: str,
    category: str,
    character_id: int = 42,
    character_name: str = "Alex",
) -> dict[str, Any]:
    return {
        "character_id": character_id,
        "character_name": character_name,
        "entity_id": 1000 + character_id,
        "tag_id": hash((tag, category)) & 0xFFFFFF,
        "tag": tag,
        "category": category,
    }

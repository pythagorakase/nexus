"""Tests for character tag migration manifest helpers."""

from argparse import Namespace
from collections.abc import Iterator
from typing import Any

import pytest

from nexus import cli
from nexus.api.character_tag_manifest import (
    CHARACTER_MANIFEST_SCHEMA_VERSION,
    build_character_migration_manifest_from_rows,
)
from nexus.api.db_pool import close_pool
from tests.pg_fixtures import (
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_deprecated_category_tag,
    seed_entity_tag,
    seed_protagonist,
)

# The row-builder tests below take no database; the builders only echo this
# label into the manifest's ``source``.
LABEL_DBNAME = "fixture_character_manifest_db"
TEST_SLOT = 2
# A disposable name no fixture creates: the execute refusal tests route the
# slot here so a regressed refusal cannot reach an owner database.
REFUSAL_NEVER_CREATED_DBNAME = "qa885_refusal_never_created"

# The review-required operations the seeded characters yield, by
# ``(character name, source tag, operation type, target tag or None)``. Each
# source row exercises one branch of the manifest's legacy mapping:
# ``bodyform:android`` (deprecated ``bodyform`` category) canonicalizes to the
# registered ``inorganic``; ``debt_pulse_active`` (deprecated
# ``orrery_signal``) is a structured remainder; ``off_grid`` (live
# ``orrery_state``) is preserved as prose; ``hunter`` (live
# ``role.function``) is a watched collision tag reviewed in place.
SEEDED_CHARACTER_OPERATIONS = {
    ("Fixture Android", "bodyform:android", "review_entity_tag", "inorganic"),
    ("Fixture Debtor", "debt_pulse_active", "structured_remainder", None),
    ("Fixture Drifter", "off_grid", "preserve_prose", None),
    ("Fixture Hunter", "hunter", "review_entity_tag", "hunter"),
}


@pytest.fixture(scope="module")
def character_manifest_dbname() -> Iterator[str]:
    """Route slot 2 to a template clone seeded with legacy character tags.

    A fifth character, "Fixture Guardian", carries only the live
    ``kin_protector`` disposition tag, which is neither legacy nor watched,
    so it must not appear in the manifest.
    """

    with disposable_slot_database("qa885_character_manifest") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=TEST_SLOT, dbname=dbname)
            _, android = seed_protagonist(dbname, name="Fixture Android")
            _, debtor = seed_character(dbname, name="Fixture Debtor")
            _, drifter = seed_character(dbname, name="Fixture Drifter")
            _, hunter = seed_character(dbname, name="Fixture Hunter")
            _, guardian = seed_character(dbname, name="Fixture Guardian")
            seed_deprecated_category_tag(
                dbname, entity_id=android, tag="bodyform:android"
            )
            seed_deprecated_category_tag(
                dbname, entity_id=debtor, tag="debt_pulse_active"
            )
            seed_entity_tag(dbname, entity_id=drifter, tag="off_grid")
            seed_entity_tag(dbname, entity_id=hunter, tag="hunter")
            seed_entity_tag(dbname, entity_id=guardian, tag="kin_protector")
            yield dbname


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
        dbname=LABEL_DBNAME,
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
        dbname=LABEL_DBNAME,
    )

    operation = manifest["operations"][0]
    assert operation["operation_type"] == "review_entity_tag"
    assert operation["target"]["target_registered"] is False
    assert manifest["counters"]["missing_target_tag_operations"] == 1


def test_cli_character_apply_requires_manifest_for_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute mode must consume a reviewed manifest.

    The refusal happens before any connection opens. The slot is routed to a
    database that is never created, so a regressed guard fails on connect
    instead of writing ready operations to an owner slot.
    """

    route_slot_to_disposable(
        monkeypatch.setattr, slot=TEST_SLOT, dbname=REFUSAL_NEVER_CREATED_DBNAME
    )
    result = cli.run_character_apply(
        Namespace(slot=TEST_SLOT, execute=True, manifest=None, source_kind="system")
    )

    assert result["success"] is False
    assert "--manifest is required with --execute" in result["error"]


@pytest.mark.requires_postgres
def test_cli_character_manifest_returns_seeded_slot_payload(
    character_manifest_dbname: str,
) -> None:
    """CLI character-manifest should read the slot and return a manifest."""

    try:
        result = cli.run_character_manifest(Namespace(slot=TEST_SLOT, output=None))
    finally:
        close_pool(character_manifest_dbname)

    assert result["success"] is True
    assert result["dbname"] == character_manifest_dbname
    manifest = result["character_manifest"]
    assert manifest["schema_version"] == (CHARACTER_MANIFEST_SCHEMA_VERSION)
    assert manifest["dry_run"] is True
    assert manifest["source"]["slot"] == TEST_SLOT
    assert manifest["source"]["dbname"] == character_manifest_dbname
    assert {
        (
            operation["character_name"],
            operation["source"]["tag"],
            operation["operation_type"],
            operation["target"].get("tag"),
        )
        for operation in manifest["operations"]
    } == SEEDED_CHARACTER_OPERATIONS
    assert all(
        operation["status"] == "review_required"
        and operation["review_required"] is True
        for operation in manifest["operations"]
    )
    (android,) = [
        operation
        for operation in manifest["operations"]
        if operation["source"]["tag"] == "bodyform:android"
    ]
    assert android["target"]["category"] == "bodyform.lineage"
    assert android["target"]["target_registered"] is True
    counters = manifest["counters"]
    assert counters["legacy_character_tag_rows"] == len(SEEDED_CHARACTER_OPERATIONS)
    assert counters["review_required_operations"] == len(SEEDED_CHARACTER_OPERATIONS)
    assert "missing_target_tag_operations" not in counters


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

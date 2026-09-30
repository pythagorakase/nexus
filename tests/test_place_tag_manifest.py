"""Tests for read-only place tag migration manifests."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterator
from typing import NamedTuple

import pytest

from nexus import cli
from nexus.api.place_tag_manifest import (
    LEGACY_PLACE_AFFORDANCE_MAP,
    PLACE_MANIFEST_SCHEMA_VERSION,
    build_place_migration_manifest_from_rows,
)
from nexus.api.db_pool import close_pool
from tests.pg_fixtures import (
    disposable_slot_database,
    route_slot_to_disposable,
    seed_deprecated_category_tag,
    seed_place,
    seed_zone,
)

# The row-builder tests below take no database; the builders only echo this
# label into the manifest's ``source``.
LABEL_DBNAME = "fixture_place_manifest_db"
TEST_SLOT = 2
# A disposable name no fixture creates: the execute refusal tests route the
# slot here so a regressed refusal cannot reach an owner database.
REFUSAL_NEVER_CREATED_DBNAME = "qa885_refusal_never_created"


class PlaceManifestSlot(NamedTuple):
    """The routed slot-2 clone and the places seeded into it."""

    dbname: str
    lot_place_id: int
    lot_entity_id: int
    clinic_place_id: int
    clinic_entity_id: int


# The review-required operations the seeded places yield, by
# ``(place name, source kind, source tag or keyword, target tag)``. "Quiet Lot"
# has prose that matches no keyword rule and carries the legacy
# ``place_affordance`` tag ``worksite``, which LEGACY_PLACE_AFFORDANCE_MAP maps
# to ``production``. "Lantern Clinic" carries no tag; its prose ("clinic",
# "hidden") matches the ``place_medical`` and ``place_hidden`` keyword rules.
SEEDED_PLACE_OPERATIONS = {
    ("Lantern Clinic", "prose_keyword", "clinic", "place_medical"),
    ("Lantern Clinic", "prose_keyword", "hidden", "place_hidden"),
    ("Quiet Lot", "legacy_entity_tag", "worksite", "production"),
}


@pytest.fixture(scope="module")
def place_manifest_slot() -> Iterator[PlaceManifestSlot]:
    """Route slot 2 to a template clone seeded with two places."""

    with disposable_slot_database("qa885_place_manifest") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=TEST_SLOT, dbname=dbname)
            seed_zone(
                dbname,
                name="Manifest Ward",
                min_longitude=-74.1,
                min_latitude=40.6,
                max_longitude=-73.8,
                max_latitude=40.9,
            )
            lot_place_id, lot_entity_id = seed_place(
                dbname, name="Quiet Lot", summary="Fixture lot."
            )
            clinic_place_id, clinic_entity_id = seed_place(
                dbname,
                name="Lantern Clinic",
                summary="A hidden clinic.",
                longitude=-73.95,
            )
            seed_deprecated_category_tag(
                dbname, entity_id=lot_entity_id, tag="worksite"
            )
            yield PlaceManifestSlot(
                dbname=dbname,
                lot_place_id=lot_place_id,
                lot_entity_id=lot_entity_id,
                clinic_place_id=clinic_place_id,
                clinic_entity_id=clinic_entity_id,
            )


def _operation_key(operation: dict) -> tuple[str, str, str, str]:
    """Name one place operation by place, source kind, source, and target."""

    source = operation["source"]
    if source["kind"] == "legacy_entity_tag":
        source_name = source["tag"]
    else:
        (source_name,) = {
            keyword for match in source["matches"] for keyword in match["keywords"]
        }
    return (
        operation["place_name"],
        source["kind"],
        source_name,
        operation["target"]["tag"],
    )


def _registered(*pairs: tuple[str, str]) -> dict[str, dict[str, object]]:
    return {
        tag: {"category": category, "deprecated": False, "synonym_for": None}
        for tag, category in pairs
    }


def test_place_manifest_suggests_registered_place_tags_from_prose() -> None:
    """Place prose becomes review-required replacement-category candidates."""

    manifest = build_place_migration_manifest_from_rows(
        [
            {
                "place_id": 122,
                "place_name": "Alex's Night City Safehouse",
                "entity_id": 9001,
                "type": "fixed_location",
                "summary": (
                    "A half-buried off-grid safehouse and transit hub in " "Night City."
                ),
                "history": "",
                "current_status": "Locked down after a breach.",
                "secrets": "Hidden escape shaft.",
                "extra_data": {
                    "surroundings": {
                        "accessibility": (
                            "No street signage; approach through service alleys."
                        )
                    },
                    "technology": {"systems": ["turrets"]},
                },
            }
        ],
        [],
        registered_tags=_registered(
            ("dwelling", "place_function"),
            ("haven", "place_function"),
            ("place_hidden", "place_visibility"),
            ("place_restricted", "place_access"),
            ("transit", "place_function"),
            ("urban_dense", "place_environment"),
            ("fortification", "place_function"),
        ),
        slot=2,
        dbname=LABEL_DBNAME,
    )

    assert manifest["schema_version"] == PLACE_MANIFEST_SCHEMA_VERSION
    assert manifest["dry_run"] is True
    targets = {
        operation["target"]["tag"]: operation for operation in manifest["operations"]
    }
    assert {
        "dwelling",
        "haven",
        "place_hidden",
        "place_restricted",
        "transit",
        "urban_dense",
        "fortification",
    } <= set(targets)
    assert all(
        operation["status"] == "review_required" for operation in targets.values()
    )
    for tag in {
        "dwelling",
        "haven",
        "place_hidden",
        "place_restricted",
        "transit",
        "urban_dense",
        "fortification",
    }:
        assert targets[tag]["target"]["target_registered"] is True
        assert targets[tag]["target"]["entity_id"] == 9001
    assert manifest["counters"]["candidate_entity_tags"] == len(manifest["operations"])


def test_place_manifest_maps_legacy_affordances_without_ready_writes() -> None:
    """Legacy place_affordance rows become reviewed replacement candidates."""

    manifest = build_place_migration_manifest_from_rows(
        [
            {
                "place_id": 10,
                "place_name": "Market Square",
                "entity_id": 100,
                "type": "fixed_location",
                "summary": "",
                "history": "",
                "current_status": "",
                "secrets": "",
                "extra_data": {},
            }
        ],
        [
            {
                "place_id": 10,
                "place_name": "Market Square",
                "entity_id": 100,
                "type": "fixed_location",
                "tag_id": 5,
                "tag": "safe_house",
                "category": "place_affordance",
            }
        ],
        registered_tags=_registered(
            ("dwelling", "place_function"),
            ("haven", "place_function"),
            ("place_hidden", "place_visibility"),
            ("place_restricted", "place_access"),
        ),
        slot=2,
        dbname=LABEL_DBNAME,
    )

    assert manifest["counters"]["legacy_place_tag_rows"] == 1
    assert manifest["counters"]["legacy_category:place_affordance"] == 1
    legacy_operations = [
        operation
        for operation in manifest["operations"]
        if operation["source"]["kind"] == "legacy_entity_tag"
    ]
    expected_tags = set(LEGACY_PLACE_AFFORDANCE_MAP["safe_house"])
    assert len(legacy_operations) == len(expected_tags)
    assert "ready_operations" not in manifest["counters"]
    assert {operation["target"]["tag"] for operation in legacy_operations} == (
        expected_tags
    )
    assert all(
        operation["target"]["entity_id"] == 100 for operation in legacy_operations
    )
    assert all(
        operation["source"]["kind"] == "legacy_entity_tag"
        for operation in legacy_operations
    )


def test_place_manifest_keeps_multiple_unmapped_legacy_tags() -> None:
    """Each unmapped legacy affordance should survive as its own remainder."""

    manifest = build_place_migration_manifest_from_rows(
        [
            {
                "place_id": 10,
                "place_name": "Quiet Lot",
                "entity_id": 100,
                "type": "fixed_location",
                "summary": "",
                "history": "",
                "current_status": "",
                "secrets": "",
                "extra_data": {},
            }
        ],
        [
            {
                "place_id": 10,
                "place_name": "Quiet Lot",
                "entity_id": 100,
                "type": "fixed_location",
                "tag_id": 5,
                "tag": "legacy_alpha",
                "category": "place_affordance",
            },
            {
                "place_id": 10,
                "place_name": "Quiet Lot",
                "entity_id": 100,
                "type": "fixed_location",
                "tag_id": 6,
                "tag": "legacy_beta",
                "category": "place_affordance",
            },
        ],
        registered_tags={},
        slot=2,
        dbname=LABEL_DBNAME,
    )

    remainders = [
        operation
        for operation in manifest["operations"]
        if operation["operation_type"] == "structured_remainder"
    ]
    assert {operation["source"]["tag"] for operation in remainders} == {
        "legacy_alpha",
        "legacy_beta",
    }


def test_place_manifest_keeps_unregistered_candidates_reviewable() -> None:
    """Missing target tags are counted instead of becoming registry growth."""

    manifest = build_place_migration_manifest_from_rows(
        [
            {
                "place_id": 20,
                "place_name": "Cold Archive",
                "entity_id": 200,
                "type": "virtual",
                "summary": "A frozen archive of impossible records.",
                "history": "",
                "current_status": "",
                "secrets": "",
                "extra_data": {},
            }
        ],
        [],
        registered_tags={},
        slot=2,
        dbname=LABEL_DBNAME,
    )

    assert manifest["counters"]["missing_target_tag_operations"] >= 1
    assert all(
        operation["target"]["target_registered"] is False
        for operation in manifest["operations"]
    )


def test_cli_place_apply_requires_manifest_for_execute(
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
    result = cli.run_place_apply(
        Namespace(slot=TEST_SLOT, execute=True, manifest=None, source_kind="system")
    )

    assert result["success"] is False
    assert "--manifest is required with --execute" in result["error"]


@pytest.mark.requires_postgres
def test_cli_place_manifest_returns_seeded_slot_payload(
    place_manifest_slot: PlaceManifestSlot,
) -> None:
    """CLI place-manifest should read the slot and return a manifest."""

    try:
        result = cli.run_place_manifest(Namespace(slot=TEST_SLOT, output=None))
    finally:
        close_pool(place_manifest_slot.dbname)

    assert result["success"] is True
    assert result["dbname"] == place_manifest_slot.dbname
    manifest = result["place_manifest"]
    assert manifest["schema_version"] == (PLACE_MANIFEST_SCHEMA_VERSION)
    assert manifest["dry_run"] is True
    assert manifest["source"]["slot"] == TEST_SLOT
    assert manifest["source"]["dbname"] == place_manifest_slot.dbname
    assert {
        _operation_key(operation) for operation in manifest["operations"]
    } == SEEDED_PLACE_OPERATIONS
    assert len(manifest["operations"]) == len(SEEDED_PLACE_OPERATIONS)
    assert all(
        operation["status"] == "review_required"
        and operation["review_required"] is True
        and operation["target"]["target_registered"] is True
        for operation in manifest["operations"]
    )
    assert {
        (operation["place_name"], operation["entity_id"])
        for operation in manifest["operations"]
    } == {
        ("Quiet Lot", place_manifest_slot.lot_entity_id),
        ("Lantern Clinic", place_manifest_slot.clinic_entity_id),
    }
    assert manifest["counters"]["places_scanned"] == 2
    assert manifest["counters"]["legacy_place_tag_rows"] == 1
    assert manifest["counters"]["review_required_operations"] == len(
        SEEDED_PLACE_OPERATIONS
    )


@pytest.mark.requires_postgres
def test_cli_place_apply_dry_run_skips_unreviewed_seeded_manifest(
    place_manifest_slot: PlaceManifestSlot,
) -> None:
    """CLI place-apply should not write generated review-required rows."""

    try:
        manifest = cli.run_place_manifest(Namespace(slot=TEST_SLOT, output=None))[
            "place_manifest"
        ]
        result = cli.run_place_apply(
            Namespace(
                slot=TEST_SLOT, execute=False, manifest=None, source_kind="system"
            )
        )
    finally:
        close_pool(place_manifest_slot.dbname)

    assert result["success"] is True
    assert result["dbname"] == place_manifest_slot.dbname
    apply_result = result["place_apply"]
    assert apply_result["dry_run"] is True
    assert apply_result["entity_kind"] == "place"
    assert apply_result["counters"]["ready_entity_tag_operations"] == 0
    assert apply_result["counters"]["review_required_operations_skipped"] == len(
        SEEDED_PLACE_OPERATIONS
    )
    assert apply_result["counters"]["entity_tags_would_insert"] == 0
    assert [
        (operation["operation_id"], operation["status"])
        for operation in apply_result["operations"]
    ] == [
        (operation["operation_id"], "skipped_review_required")
        for operation in manifest["operations"]
    ]

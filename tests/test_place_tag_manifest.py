"""Tests for read-only place tag migration manifests."""

from __future__ import annotations

from argparse import Namespace

import psycopg2  # type: ignore[import-untyped]
import pytest

from nexus import cli
from nexus.api.place_tag_manifest import (
    PLACE_MANIFEST_SCHEMA_VERSION,
    build_place_migration_manifest_from_rows,
)
from nexus.api.db_pool import close_pool


TEST_DBNAME = "save_02"


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
        dbname="save_02",
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
        dbname="save_02",
    )

    assert manifest["counters"]["legacy_place_tag_rows"] == 1
    assert manifest["counters"]["legacy_category:place_affordance"] == 1
    legacy_operations = [
        operation
        for operation in manifest["operations"]
        if operation["source"]["kind"] == "legacy_entity_tag"
    ]
    assert len(legacy_operations) == 4
    assert "ready_operations" not in manifest["counters"]
    assert {operation["target"]["tag"] for operation in legacy_operations} == {
        "dwelling",
        "haven",
        "place_hidden",
        "place_restricted",
    }
    assert all(
        operation["target"]["entity_id"] == 100 for operation in legacy_operations
    )
    assert all(
        operation["source"]["kind"] == "legacy_entity_tag"
        for operation in legacy_operations
    )


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
        dbname="save_02",
    )

    assert manifest["counters"]["missing_target_tag_operations"] >= 1
    assert all(
        operation["target"]["target_registered"] is False
        for operation in manifest["operations"]
    )


@pytest.mark.requires_postgres
def test_cli_place_manifest_returns_live_slot2_payload() -> None:
    """CLI place-manifest should read the slot and return a manifest."""

    try:
        result = cli.run_place_manifest(Namespace(slot=2, output=None))
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    finally:
        close_pool(TEST_DBNAME)

    assert result["success"] is True
    assert result["place_manifest"]["schema_version"] == (PLACE_MANIFEST_SCHEMA_VERSION)
    assert result["place_manifest"]["dry_run"] is True
    assert result["place_manifest"]["source"]["slot"] == 2

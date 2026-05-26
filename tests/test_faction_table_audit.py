"""Tests for faction table migration dry-run audit helpers."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict
from decimal import Decimal
import json
from typing import Any

import psycopg2  # type: ignore[import-untyped]
import pytest

from nexus import cli
from nexus.api.db_pool import close_pool, get_connection
from nexus.api.faction_table_audit import (
    LEGACY_TAG_CATEGORIES,
    LegacyTagRow,
    audit_faction_row,
    build_faction_migration_manifest,
    build_faction_table_audit,
)


TEST_DBNAME = "save_02"


def _slot2_faction_audit() -> dict[str, Any]:
    try:
        with get_connection(TEST_DBNAME, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                return build_faction_table_audit(cur)
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    finally:
        close_pool(TEST_DBNAME)


def test_audit_faction_row_flags_network_resource_ambiguity() -> None:
    """The overloaded legacy network value should not silently pick one tag."""

    entry = audit_faction_row(
        {
            "id": 7,
            "name": "Quiet Hand",
            "entity_id": 707,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": "network",
        },
        existing_pair_tags={},
        legacy_tags=[],
    )

    resource_candidates = [
        item for item in entry.mapping_candidates if item.source_column == "resources"
    ]

    assert entry.review_required is True
    assert {item.target_tag for item in resource_candidates} == {
        "criminal_network",
        "information",
        "patronage",
    }
    assert all(item.confidence == "ambiguous" for item in resource_candidates)


def test_audit_faction_row_maps_specific_network_resource() -> None:
    """Specific network prose should reach the keyword matcher."""

    entry = audit_faction_row(
        {
            "id": 8,
            "name": "Ledger Ring",
            "entity_id": 808,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": "information network",
        },
        existing_pair_tags={},
        legacy_tags=[],
    )

    resource_candidates = [
        item for item in entry.mapping_candidates if item.source_column == "resources"
    ]

    assert [(item.target_tag, item.confidence) for item in resource_candidates] == [
        ("information", "suggested")
    ]


def test_power_level_point_one_maps_to_declining() -> None:
    """The 0.10 band edge should not collapse the faction."""

    entry = audit_faction_row(
        {
            "id": 9,
            "name": "Thin Crown",
            "entity_id": 909,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": Decimal("0.10"),
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[],
    )

    candidates = [
        item for item in entry.mapping_candidates if item.source_column == "power_level"
    ]

    assert candidates[0].target_tag == "declining"


@pytest.mark.requires_postgres
def test_build_faction_table_audit_reads_slot2_legacy_tag_categories() -> None:
    """The audit should cover every legacy faction category present in slot 2."""

    audit = _slot2_faction_audit()
    counters = audit["counters"]
    factions = audit["factions"]
    legacy_categories = {
        tag["category"] for faction in factions for tag in faction["legacy_tags"]
    }
    candidate_sources = {
        candidate["source_column"]
        for faction in factions
        for candidate in faction["mapping_candidates"]
    }

    assert audit["dry_run"] is True
    assert "legacy_tag_rows" not in audit
    assert counters["factions_scanned"] >= 1
    assert counters["legacy_tag_rows"] >= len(legacy_categories)
    assert legacy_categories <= set(LEGACY_TAG_CATEGORIES)
    assert "state" not in legacy_categories
    for category in legacy_categories:
        assert f"entity_tags_current.{category}" in candidate_sources


def test_operational_secrecy_hidden_maps_to_operational_mode_covert() -> None:
    """Legacy operational_secrecy rows should seed operational_mode candidates."""

    entry = audit_faction_row(
        {
            "id": 3,
            "name": "Veiled Office",
            "entity_id": 303,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[
            LegacyTagRow(
                faction_id=3,
                faction_name="Veiled Office",
                entity_id=303,
                category="operational_secrecy",
                tag="hidden",
            )
        ],
    )

    candidates = [
        item
        for item in entry.mapping_candidates
        if item.source_column == "entity_tags_current.operational_secrecy"
    ]

    assert len(candidates) == 1
    assert candidates[0].target_category == "operational_mode"
    assert candidates[0].target_tag == "covert"


def test_operational_secrecy_cellular_maps_to_reviewable_covert() -> None:
    """Old structure-flavored secrecy tags should still point at covert mode."""

    entry = audit_faction_row(
        {
            "id": 4,
            "name": "Cell Office",
            "entity_id": 404,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[
            LegacyTagRow(
                faction_id=4,
                faction_name="Cell Office",
                entity_id=404,
                category="operational_secrecy",
                tag="cellular_clandestine",
            )
        ],
    )

    candidates = [
        item
        for item in entry.mapping_candidates
        if item.source_column == "entity_tags_current.operational_secrecy"
    ]

    assert candidates[0].target_category == "operational_mode"
    assert candidates[0].target_tag == "covert"
    assert candidates[0].review_required is True


def test_legitimacy_status_gray_legal_maps_to_shadow_legal() -> None:
    """Legacy legitimacy rows should point at the new legitimacy category."""

    entry = audit_faction_row(
        {
            "id": 5,
            "name": "Licensed Knives",
            "entity_id": 505,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[
            LegacyTagRow(
                faction_id=5,
                faction_name="Licensed Knives",
                entity_id=505,
                category="legitimacy_status",
                tag="gray_legal",
            )
        ],
    )

    candidates = [
        item
        for item in entry.mapping_candidates
        if item.source_column == "entity_tags_current.legitimacy_status"
    ]

    assert candidates[0].target_category == "legitimacy"
    assert candidates[0].target_tag == "shadow_legal"
    assert candidates[0].review_required is True


def test_history_class_is_explicit_no_replacement() -> None:
    """No-replacement legacy categories should be visible in dry-run output."""

    entry = audit_faction_row(
        {
            "id": 6,
            "name": "Old Compact",
            "entity_id": 606,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[
            LegacyTagRow(
                faction_id=6,
                faction_name="Old Compact",
                entity_id=606,
                category="history_class",
                tag="ancient_continuous",
            )
        ],
    )

    candidates = [
        item
        for item in entry.mapping_candidates
        if item.source_column == "entity_tags_current.history_class"
    ]

    assert candidates[0].target_kind == "no_replacement"
    assert candidates[0].review_required is True


@pytest.mark.requires_postgres
def test_cli_faction_audit_returns_live_slot2_payload() -> None:
    """The faction audit CLI should resolve slot 2 against the real database."""

    try:
        result = cli.run_faction_audit(Namespace(slot=2))
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    finally:
        close_pool(TEST_DBNAME)

    assert result["success"] is True
    assert result["slot"] == 2
    assert result["dbname"] == "save_02"
    assert result["faction_audit"]["dry_run"] is True
    assert result["faction_audit"]["counters"]["factions_scanned"] >= 1


def test_cli_faction_audit_json_output_handles_decimal_payload(capsys) -> None:
    """Faction audit JSON output should round-trip Decimal-origin values."""

    entry = audit_faction_row(
        {
            "id": 10,
            "name": "Measured Guild",
            "entity_id": 1010,
            "ideology": None,
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": Decimal("0.10"),
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[],
    )
    payload = {
        "message": "Faction table audit for slot 2 (dry run).",
        "faction_audit": {
            "counters": {},
            "non_null_counts": {"power_level": 1},
            "factions": [asdict(entry)],
        },
    }

    cli.emit_output(payload, as_json=True)
    decoded = json.loads(capsys.readouterr().out)

    assert (
        decoded["faction_audit"]["factions"][0]["obsolete_columns"]["power_level"]
        == 0.1
    )


def test_cli_prints_all_pair_edge_counters(capsys) -> None:
    """Human faction audit output should include both relation edge counters."""

    cli.emit_output(
        {
            "message": "Faction table audit for slot 2 (dry run).",
            "faction_audit": {
                "counters": {
                    "active_claim_edges": 2,
                    "active_operates_from_edges": 3,
                },
                "non_null_counts": {},
                "factions": [],
            },
        },
        as_json=False,
    )

    output = capsys.readouterr().out

    assert "active_claim_edges: 2" in output
    assert "active_operates_from_edges: 3" in output


def test_faction_migration_manifest_classifies_operations() -> None:
    """The manifest should separate ready writes from review-only work."""

    entry = audit_faction_row(
        {
            "id": 11,
            "name": "Canal League",
            "entity_id": 1111,
            "ideology": "mercantilist",
            "history": "Founded after the river war.",
            "current_activity": None,
            "hidden_agenda": None,
            "territory": "controls the canal district",
            "primary_location": None,
            "power_level": None,
            "resources": "network",
        },
        existing_pair_tags={},
        legacy_tags=[
            LegacyTagRow(
                faction_id=11,
                faction_name="Canal League",
                entity_id=1111,
                category="history_class",
                tag="ancient_continuous",
            )
        ],
    )
    audit = {
        "counters": {},
        "source_columns": ["ideology", "history", "territory", "resources"],
        "keep_columns": ["id", "name"],
        "factions": [asdict(entry)],
    }

    manifest = build_faction_migration_manifest(
        audit,
        slot=2,
        dbname="save_02",
    )
    operation_types = {
        operation["operation_type"] for operation in manifest["operations"]
    }

    assert manifest["schema_version"] == "faction-migration-manifest.v1"
    assert manifest["dry_run"] is True
    assert manifest["source"]["slot"] == 2
    assert manifest["counters"]["ready_operations"] == 1
    assert manifest["counters"]["insert_entity_tag_operations"] == 1
    assert "review_entity_tag" in operation_types
    assert "resolve_pair_tag_target" in operation_types
    assert "preserve_prose" in operation_types
    assert "drop_legacy_tag_after_review" in operation_types
    assert all(
        operation["operation_id"].startswith("faction-migration-")
        for operation in manifest["operations"]
    )
    assert all(
        operation["review_required"] == (operation["status"] != "ready")
        for operation in manifest["operations"]
    )


@pytest.mark.requires_postgres
def test_cli_faction_manifest_returns_live_slot2_payload() -> None:
    """The faction manifest CLI should build from the real slot 2 audit."""

    try:
        result = cli.run_faction_manifest(Namespace(slot=2))
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    finally:
        close_pool(TEST_DBNAME)

    manifest = result["faction_manifest"]

    assert result["success"] is True
    assert result["slot"] == 2
    assert manifest["dry_run"] is True
    assert manifest["counters"]["operation_items"] >= 1
    assert manifest["counters"]["operation_items"] == len(manifest["operations"])


def test_cli_prints_faction_manifest_summary(capsys) -> None:
    """Human faction manifest output should show operation counters."""

    cli.emit_output(
        {
            "message": "Faction migration manifest for slot 2 (dry run).",
            "faction_manifest": {
                "schema_version": "faction-migration-manifest.v1",
                "dry_run": True,
                "counters": {
                    "operation_items": 2,
                    "ready_operations": 1,
                    "review_required_operations": 1,
                    "manual_review_operations": 1,
                },
                "factions": [
                    {
                        "faction_id": 11,
                        "faction_name": "Canal League",
                        "review_required_operations": 1,
                    }
                ],
            },
        },
        as_json=False,
    )

    output = capsys.readouterr().out

    assert "operation_items: 2" in output
    assert "ready_operations: 1" in output
    assert "manual_review_operations: 1" in output
    assert "Canal League (id 11): 1 item(s)" in output

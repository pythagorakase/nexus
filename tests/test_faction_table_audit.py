"""Tests for faction table migration dry-run audit helpers."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict
from decimal import Decimal
import json
from typing import Any

import psycopg2  # type: ignore[import-untyped]
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
import pytest

from nexus import cli
from nexus.api.db_pool import close_pool, get_connection
from nexus.api.faction_table_audit import (
    EXCLUSIVE_FACTION_CATEGORIES,
    FACTION_CATEGORY_CARDINALITY,
    FACTION_MANIFEST_SCHEMA_VERSION,
    LEGACY_TAG_CATEGORIES,
    LegacyTagRow,
    apply_faction_migration_manifest,
    audit_faction_row,
    build_faction_migration_manifest,
    build_faction_table_audit,
)
from nexus.api.slot_utils import get_slot_db_url


TEST_DBNAME = "save_02"


class FactionApplyCursor:
    """Small fake cursor for deterministic faction manifest apply tests."""

    def __init__(
        self,
        *,
        active_entity_tags: list[dict[str, Any]] | None = None,
    ) -> None:
        self.source_kinds = {"system", "skald_inline", "llm_generated"}
        self.allowed_categories = {
            "agenda",
            "ideology",
            "legitimacy",
            "operational_mode",
            "power_status",
            "resource_base",
        }
        self.tags: dict[tuple[str, str], dict[str, Any]] = {
            ("ideology", "mercantilist"): {
                "id": 101,
                "tag": "mercantilist",
                "category": "ideology",
            },
            ("legitimacy", "outlaw"): {
                "id": 202,
                "tag": "outlaw",
                "category": "legitimacy",
            },
            ("legitimacy", "contested"): {
                "id": 203,
                "tag": "contested",
                "category": "legitimacy",
            },
        }
        self.tag_by_id: dict[int, dict[str, Any]] = {
            int(row["id"]): row for row in self.tags.values()
        }
        self.entities: dict[int, str] = {1111: "faction"}
        self.entity_tags: list[dict[str, Any]] = list(active_entity_tags or [])
        self.next_entity_tag_id = 9001
        self.rowcount = 0
        self._rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Handle the SQL shapes emitted by faction apply."""

        normalized = " ".join(sql.split())
        self.rowcount = 0
        if "FROM pg_enum" in normalized:
            source_kind = str(params[0])
            self._rows = [{"exists": 1}] if source_kind in self.source_kinds else []
        elif "FROM tag_category_registry" in normalized:
            self._rows = [
                {"category": category} for category in sorted(self.allowed_categories)
            ]
        elif normalized == "SELECT max(world_time) AS world_time FROM chunk_metadata":
            self._rows = [{"world_time": None}]
        elif "FROM tags" in normalized and "WHERE tag = %s" in normalized:
            tag, category = params
            row = self.tags.get((str(category), str(tag)))
            self._rows = [row] if row else []
        elif "FROM entities" in normalized:
            entity_id = int(params[0])
            kind = self.entities.get(entity_id)
            self._rows = [{"id": entity_id, "kind": kind}] if kind else []
        elif (
            normalized.startswith("SELECT id FROM entity_tags")
            and "tag_id = %s" in normalized
        ):
            entity_id, tag_id = (int(params[0]), int(params[1]))
            self._rows = [
                {"id": row["id"]}
                for row in self.entity_tags
                if row["entity_id"] == entity_id
                and row["tag_id"] == tag_id
                and row.get("cleared_at") is None
            ]
        elif "JOIN tags t ON t.id = et.tag_id" in normalized:
            entity_id, category, excluded_tag_id = (
                int(params[0]),
                str(params[1]),
                int(params[2]),
            )
            self._rows = []
            for row in self.entity_tags:
                tag_row = self.tag_by_id[int(row["tag_id"])]
                if (
                    row["entity_id"] == entity_id
                    and row.get("cleared_at") is None
                    and tag_row["category"] == category
                    and tag_row["id"] != excluded_tag_id
                ):
                    self._rows.append({"tag": tag_row["tag"]})
            self._rows.sort(key=lambda item: item["tag"])
        elif normalized.startswith("INSERT INTO entity_tags"):
            entity_id, tag_id, world_time, source_kind = params
            existing = [
                row
                for row in self.entity_tags
                if row["entity_id"] == entity_id
                and row["tag_id"] == tag_id
                and row.get("cleared_at") is None
            ]
            if existing:
                self._rows = []
                return

            entity_tag_id = self.next_entity_tag_id
            self.next_entity_tag_id += 1
            self.entity_tags.append(
                {
                    "id": entity_tag_id,
                    "entity_id": entity_id,
                    "tag_id": tag_id,
                    "applied_at_world_time": world_time,
                    "source_kind": source_kind,
                    "cleared_at": None,
                }
            )
            self.rowcount = 1
            self._rows = [{"id": entity_tag_id}]
        else:
            raise AssertionError(f"Unhandled SQL in fake cursor: {normalized}")

    def fetchone(self) -> dict[str, Any] | None:
        """Return one pending row."""

        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchall(self) -> list[dict[str, Any]]:
        """Return all pending rows."""

        rows = list(self._rows)
        self._rows.clear()
        return rows


class RetiredFactionColumnsAuditCursor:
    """Fake cursor for auditing after legacy faction columns are dropped."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self._rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Handle the SQL shapes emitted by the audit path."""

        normalized = " ".join(sql.split())
        self.statements.append(normalized)
        if "FROM information_schema.columns" in normalized:
            self._rows = [
                {"column_name": column}
                for column in (
                    "id",
                    "name",
                    "entity_id",
                    "summary",
                    "primary_location",
                    "created_at",
                    "updated_at",
                    "extra_data",
                )
            ]
        elif "FROM factions ORDER BY id" in normalized:
            assert "NULL::text AS ideology" in normalized
            assert "NULL::numeric AS power_level" in normalized
            self._rows = [
                {
                    "id": 1,
                    "name": "Columnless League",
                    "entity_id": 1001,
                    "ideology": None,
                    "history": None,
                    "current_activity": None,
                    "hidden_agenda": None,
                    "territory": None,
                    "primary_location": None,
                    "power_level": None,
                    "resources": None,
                }
            ]
        elif "FROM entity_pair_tags" in normalized:
            self._rows = []
        elif "FROM entity_tags_current" in normalized:
            self._rows = []
        else:
            raise AssertionError(f"Unhandled SQL in fake cursor: {normalized}")

    def fetchone(self) -> dict[str, Any] | None:
        """Return one pending row."""

        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchall(self) -> list[dict[str, Any]]:
        """Return all pending rows."""

        rows = list(self._rows)
        self._rows.clear()
        return rows


def _manifest_operation(
    *,
    operation_id: str,
    status: str,
    operation_type: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "operation_type": operation_type,
        "status": status,
        "faction_id": 11,
        "faction_name": "Canal League",
        "entity_id": target.get("entity_id"),
        "source": {"column": "ideology", "value": "mercantilist"},
        "target": target,
        "confidence": "deterministic",
        "review_required": status != "ready",
        "reason": "test",
    }


def _apply_manifest(operations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": FACTION_MANIFEST_SCHEMA_VERSION,
        "dry_run": True,
        "operations": operations,
        "source": {"slot": 2, "dbname": "save_02"},
    }


def _ready_entity_tag_manifest(
    *,
    operation_id: str = "ready",
    entity_id: int = 1111,
    category: str = "ideology",
    tag: str = "mercantilist",
) -> dict[str, Any]:
    return _apply_manifest(
        [
            _manifest_operation(
                operation_id=operation_id,
                status="ready",
                operation_type="insert_entity_tag",
                target={
                    "entity_kind": "faction",
                    "entity_id": entity_id,
                    "category": category,
                    "tag": tag,
                },
            )
        ]
    )


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


def test_build_faction_table_audit_handles_retired_legacy_columns() -> None:
    """The dry-run audit should still work after migration 058 drops columns."""

    cur = RetiredFactionColumnsAuditCursor()

    audit = build_faction_table_audit(cur)

    assert audit["available_source_columns"] == []
    assert audit["retired_source_columns"] == [
        "ideology",
        "history",
        "current_activity",
        "hidden_agenda",
        "territory",
        "power_level",
        "resources",
    ]
    assert audit["non_null_counts"] == {
        "ideology": 0,
        "history": 0,
        "current_activity": 0,
        "hidden_agenda": 0,
        "territory": 0,
        "power_level": 0,
        "resources": 0,
    }
    assert audit["counters"]["factions_scanned"] == 1
    assert audit["counters"]["non_null_legacy_values"] == 0


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


def test_exclusive_faction_categories_derive_from_cardinality_map() -> None:
    """Exclusive-axis enforcement should not use a standalone category list."""

    assert EXCLUSIVE_FACTION_CATEGORIES == {
        category
        for category, cardinality in FACTION_CATEGORY_CARDINALITY.items()
        if cardinality == "exclusive"
    }
    assert FACTION_CATEGORY_CARDINALITY == {
        "agenda": "multi",
        "ideology": "multi",
        "legitimacy": "exclusive",
        "operational_mode": "exclusive",
        "power_status": "exclusive",
        "resource_base": "multi",
    }


def test_manifest_requires_entity_id_for_ready_entity_tag_operations() -> None:
    """A deterministic mapping cannot be ready if the faction has no entity."""

    entry = audit_faction_row(
        {
            "id": 12,
            "name": "Unattached League",
            "entity_id": None,
            "ideology": "mercantilist",
            "history": None,
            "current_activity": None,
            "hidden_agenda": None,
            "territory": None,
            "primary_location": None,
            "power_level": None,
            "resources": None,
        },
        existing_pair_tags={},
        legacy_tags=[],
    )
    audit = {
        "counters": {},
        "source_columns": ["ideology"],
        "keep_columns": ["id", "name"],
        "factions": [asdict(entry)],
    }

    manifest = build_faction_migration_manifest(
        audit,
        slot=2,
        dbname="save_02",
    )

    assert manifest["counters"]["ready_operations"] == 0
    assert manifest["operations"][0]["operation_type"] == "review_entity_tag"
    assert "no entity_id" in manifest["operations"][0]["reason"]


def test_apply_faction_manifest_dry_run_only_counts_ready_writes() -> None:
    """The apply pass should report ready inserts without mutating in dry run."""

    cur = FactionApplyCursor()
    manifest = _apply_manifest(
        [
            _manifest_operation(
                operation_id="ready",
                status="ready",
                operation_type="insert_entity_tag",
                target={
                    "entity_kind": "faction",
                    "entity_id": 1111,
                    "category": "ideology",
                    "tag": "mercantilist",
                },
            ),
            _manifest_operation(
                operation_id="review",
                status="review_required",
                operation_type="review_entity_tag",
                target={
                    "entity_kind": "faction",
                    "entity_id": 1111,
                    "category": "ideology",
                    "tag": "mercantilist",
                },
            ),
        ]
    )

    result = apply_faction_migration_manifest(cur, manifest, dry_run=True)

    assert result["dry_run"] is True
    assert result["counters"]["ready_entity_tag_operations"] == 1
    assert result["counters"]["entity_tags_would_insert"] == 1
    assert result["counters"]["review_required_operations_skipped"] == 1
    assert result["counters"].get("entity_tags_inserted", 0) == 0
    assert cur.entity_tags == []
    assert [operation["status"] for operation in result["operations"]] == [
        "would_insert",
        "skipped_review_required",
    ]


def test_apply_faction_manifest_execute_inserts_ready_tag() -> None:
    """The execute pass should insert ready faction entity tags."""

    cur = FactionApplyCursor()
    manifest = _ready_entity_tag_manifest()

    result = apply_faction_migration_manifest(cur, manifest, dry_run=False)

    assert result["dry_run"] is False
    assert result["counters"]["entity_tags_inserted"] == 1
    assert result["operations"][0]["status"] == "inserted"
    assert cur.entity_tags == [
        {
            "id": 9001,
            "entity_id": 1111,
            "tag_id": 101,
            "applied_at_world_time": None,
            "source_kind": "system",
            "cleared_at": None,
        }
    ]


def test_apply_faction_manifest_blocks_exclusive_category_conflicts() -> None:
    """Exclusive faction axes should not be overwritten without review."""

    cur = FactionApplyCursor(
        active_entity_tags=[
            {
                "id": 8001,
                "entity_id": 1111,
                "tag_id": 203,
                "cleared_at": None,
            }
        ],
    )
    manifest = _apply_manifest(
        [
            _manifest_operation(
                operation_id="ready",
                status="ready",
                operation_type="insert_entity_tag",
                target={
                    "entity_kind": "faction",
                    "entity_id": 1111,
                    "category": "legitimacy",
                    "tag": "outlaw",
                },
            )
        ]
    )

    result = apply_faction_migration_manifest(cur, manifest, dry_run=False)

    assert result["counters"]["blocked_existing_sibling_operations"] == 1
    assert result["operations"][0]["status"] == "blocked_existing_sibling"
    assert result["operations"][0]["existing_sibling_tags"] == ["contested"]
    assert len(cur.entity_tags) == 1


def test_cli_faction_apply_execute_requires_manifest_file() -> None:
    """Executing from a freshly rebuilt manifest would violate review contract."""

    result = cli.run_faction_apply(
        Namespace(slot=2, execute=True, source_kind="system", manifest=None)
    )

    assert result["success"] is False
    assert "--manifest is required" in result["error"]


def test_cli_faction_apply_rejects_manifest_slot_mismatch(tmp_path) -> None:
    """Persisted manifests should be scoped to the requested slot."""

    manifest_path = tmp_path / "manifest.json"
    manifest = _ready_entity_tag_manifest()
    manifest["source"] = {"slot": 5, "dbname": "save_05"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = cli.run_faction_apply(
        Namespace(
            slot=2,
            execute=True,
            source_kind="system",
            manifest=manifest_path,
        )
    )

    assert result["success"] is False
    assert "does not match --slot" in result["error"]


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


@pytest.mark.requires_postgres
def test_live_faction_apply_execute_inserts_and_rolls_back() -> None:
    """The execute path should hit real FK, enum, and ON CONFLICT behavior."""

    conn = None
    try:
        conn = psycopg2.connect(get_slot_db_url(dbname=TEST_DBNAME))
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.id AS faction_id, f.name, f.entity_id
                FROM factions f
                JOIN entities e ON e.id = f.entity_id
                WHERE e.kind = 'faction'::entity_kind
                ORDER BY f.id
                LIMIT 1
                """
            )
            faction = cur.fetchone()
            if faction is None:
                pytest.skip(f"{TEST_DBNAME} has no faction entity to target")

            entity_id = int(faction["entity_id"])
            cur.execute(
                """
                INSERT INTO tag_category_registry (
                    category, entity_kind, prompt_order, description
                )
                VALUES (
                    'ideology', 'faction'::entity_kind, 999,
                    'Test-scoped faction apply category registration.'
                )
                ON CONFLICT (category, entity_kind) DO NOTHING
                """
            )
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral, deprecated, description
                )
                VALUES (
                    'test_faction_apply_temp',
                    'ideology',
                    FALSE,
                    FALSE,
                    'Rollback-scoped test tag for faction apply.'
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = FALSE,
                    clearance_kind = NULL,
                    clear_on = NULL,
                    synonym_for = NULL,
                    deprecated = FALSE,
                    description = EXCLUDED.description
                RETURNING id, tag, category
                """
            )
            tag_row = cur.fetchone()
            if tag_row is None:
                pytest.skip(f"{TEST_DBNAME} could not seed rollback-scoped test tag")
            cur.execute(
                """
                DELETE FROM entity_tags
                WHERE entity_id = %s
                  AND tag_id = %s
                """,
                (entity_id, int(tag_row["id"])),
            )

            manifest = _ready_entity_tag_manifest(
                entity_id=entity_id,
                category=str(tag_row["category"]),
                tag=str(tag_row["tag"]),
            )
            manifest["source"] = {"slot": 2, "dbname": TEST_DBNAME}

            result = apply_faction_migration_manifest(cur, manifest, dry_run=False)

            assert result["counters"]["entity_tags_inserted"] == 1
            assert result["operations"][0]["status"] == "inserted"

            cur.execute(
                """
                SELECT source_kind::text AS source_kind
                FROM entity_tags
                WHERE entity_id = %s
                  AND tag_id = %s
                  AND cleared_at IS NULL
                """,
                (entity_id, int(tag_row["id"])),
            )
            inserted = cur.fetchone()
            assert inserted is not None
            assert inserted["source_kind"] == "system"
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()


@pytest.mark.requires_postgres
def test_cli_faction_apply_dry_run_returns_live_slot2_payload() -> None:
    """The faction apply CLI should validate ready writes without mutating."""

    try:
        result = cli.run_faction_apply(
            Namespace(slot=2, execute=False, source_kind="system")
        )
    except psycopg2.Error as exc:
        pytest.skip(f"{TEST_DBNAME} PostgreSQL test database unavailable: {exc}")
    except ValueError as exc:
        message = str(exc)
        if (
            "Unknown or deprecated faction tag" in message
            or "No Orrery tag categories registered" in message
            or "not registered for factions" in message
        ):
            pytest.skip(f"{TEST_DBNAME} faction vocabulary not seeded: {exc}")
        raise
    finally:
        close_pool(TEST_DBNAME)

    apply_result = result["faction_apply"]

    assert result["success"] is True
    assert result["slot"] == 2
    assert apply_result["dry_run"] is True
    assert apply_result["counters"]["operation_items"] >= 1
    assert apply_result["counters"]["ready_entity_tag_operations"] >= 0


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


def test_cli_prints_faction_apply_summary(capsys) -> None:
    """Human faction apply output should show write/read-only counters."""

    cli.emit_output(
        {
            "message": "Faction migration apply for slot 2 (dry run).",
            "faction_apply": {
                "schema_version": "faction-migration-apply.v1",
                "dry_run": True,
                "source_kind": "system",
                "counters": {
                    "operation_items": 2,
                    "ready_entity_tag_operations": 1,
                    "entity_tags_would_insert": 1,
                    "review_required_operations_skipped": 1,
                },
                "operations": [],
            },
        },
        as_json=False,
    )

    output = capsys.readouterr().out

    assert "schema_version: faction-migration-apply.v1" in output
    assert "dry_run: True" in output
    assert "entity_tags_would_insert: 1" in output
    assert "review_required_operations_skipped: 1" in output

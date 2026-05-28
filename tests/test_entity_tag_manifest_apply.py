"""Tests for reviewed entity-tag manifest apply helpers."""

from __future__ import annotations

from typing import Any

import pytest

from nexus.api.entity_tag_manifest_apply import apply_entity_tag_manifest


class EntityApplyCursor:
    """Small fake cursor for deterministic entity-tag apply tests."""

    def __init__(
        self,
        *,
        entity_kind: str = "character",
        active_entity_tags: list[dict[str, Any]] | None = None,
    ) -> None:
        self.source_kinds = {"system", "skald_inline", "llm_generated"}
        self.registered_categories = {
            "character": {"role.function", "role.fame"},
            "place": {"place_function", "place_visibility"},
        }
        self.tags: dict[tuple[str, str], dict[str, Any]] = {
            ("role.function", "scholar"): {
                "id": 101,
                "tag": "scholar",
                "category": "role.function",
            },
            ("role.fame", "known"): {
                "id": 202,
                "tag": "known",
                "category": "role.fame",
            },
            ("role.fame", "renowned"): {
                "id": 203,
                "tag": "renowned",
                "category": "role.fame",
            },
            ("place_function", "dwelling"): {
                "id": 301,
                "tag": "dwelling",
                "category": "place_function",
            },
        }
        self.tag_by_id: dict[int, dict[str, Any]] = {
            int(row["id"]): row for row in self.tags.values()
        }
        self.entities: dict[int, str] = {1001: entity_kind}
        self.entity_tags: list[dict[str, Any]] = list(active_entity_tags or [])
        self.next_entity_tag_id = 9001
        self._rows: list[dict[str, Any]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Handle the SQL shapes emitted by entity-tag apply."""

        normalized = " ".join(sql.split())
        self.rowcount = 0
        if "FROM pg_enum" in normalized:
            source_kind = str(params[0])
            self._rows = [{"exists": 1}] if source_kind in self.source_kinds else []
        elif "FROM tag_category_registry" in normalized:
            entity_kind = str(params[0])
            self._rows = [
                {"category": category}
                for category in sorted(self.registered_categories.get(entity_kind, ()))
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


def test_apply_entity_tag_manifest_dry_runs_promoted_review_operation() -> None:
    """A reviewed ready entity-tag candidate can be planned without writing."""

    result = apply_entity_tag_manifest(
        EntityApplyCursor(),
        _manifest(
            [
                _operation(
                    operation_id="ready-scholar",
                    status="ready",
                    review_required=False,
                    operation_type="review_entity_tag",
                    target={
                        "entity_kind": "character",
                        "entity_id": 1001,
                        "category": "role.function",
                        "tag": "scholar",
                        "target_registered": True,
                    },
                )
            ]
        ),
        manifest_schema_version="test-manifest.v1",
        entity_kind="character",
        allowed_categories=("role.function", "role.fame"),
        exclusive_categories=("role.fame",),
        dry_run=True,
    )

    assert result["counters"]["ready_entity_tag_operations"] == 1
    assert result["counters"]["entity_tags_would_insert"] == 1
    assert result["operations"][0]["status"] == "would_insert"


def test_apply_entity_tag_manifest_skips_review_required_rows() -> None:
    """Generated manifests remain non-mutating until rows are explicitly ready."""

    result = apply_entity_tag_manifest(
        EntityApplyCursor(),
        _manifest(
            [
                _operation(
                    operation_id="needs-review",
                    status="review_required",
                    review_required=True,
                    operation_type="review_entity_tag",
                    target={
                        "entity_kind": "character",
                        "entity_id": 1001,
                        "category": "role.function",
                        "tag": "scholar",
                        "target_registered": True,
                    },
                )
            ]
        ),
        manifest_schema_version="test-manifest.v1",
        entity_kind="character",
        allowed_categories=("role.function", "role.fame"),
        exclusive_categories=("role.fame",),
        dry_run=True,
    )

    assert result["counters"]["ready_entity_tag_operations"] == 0
    assert result["counters"]["review_required_operations_skipped"] == 1
    assert result["operations"][0]["status"] == "skipped_review_required"


def test_apply_entity_tag_manifest_blocks_existing_exclusive_sibling() -> None:
    """Ready exclusive-category rows do not overwrite active sibling tags."""

    result = apply_entity_tag_manifest(
        EntityApplyCursor(
            active_entity_tags=[
                {
                    "id": 7001,
                    "entity_id": 1001,
                    "tag_id": 202,
                    "cleared_at": None,
                }
            ]
        ),
        _manifest(
            [
                _operation(
                    operation_id="ready-renown",
                    status="ready",
                    review_required=False,
                    operation_type="review_entity_tag",
                    target={
                        "entity_kind": "character",
                        "entity_id": 1001,
                        "category": "role.fame",
                        "tag": "renowned",
                        "target_registered": True,
                    },
                )
            ]
        ),
        manifest_schema_version="test-manifest.v1",
        entity_kind="character",
        allowed_categories=("role.function", "role.fame"),
        exclusive_categories=("role.fame",),
        dry_run=False,
    )

    assert result["counters"]["blocked_existing_sibling_operations"] == 1
    assert result["operations"][0]["status"] == "blocked_existing_sibling"
    assert result["operations"][0]["existing_sibling_tags"] == ["known"]


def test_apply_entity_tag_manifest_blocks_planned_exclusive_sibling() -> None:
    """Dry runs mirror execute-time exclusive sibling conflicts."""

    result = apply_entity_tag_manifest(
        EntityApplyCursor(),
        _manifest(
            [
                _operation(
                    operation_id="ready-known",
                    status="ready",
                    review_required=False,
                    operation_type="review_entity_tag",
                    target={
                        "entity_kind": "character",
                        "entity_id": 1001,
                        "category": "role.fame",
                        "tag": "known",
                        "target_registered": True,
                    },
                ),
                _operation(
                    operation_id="ready-renown",
                    status="ready",
                    review_required=False,
                    operation_type="review_entity_tag",
                    target={
                        "entity_kind": "character",
                        "entity_id": 1001,
                        "category": "role.fame",
                        "tag": "renowned",
                        "target_registered": True,
                    },
                ),
            ]
        ),
        manifest_schema_version="test-manifest.v1",
        entity_kind="character",
        allowed_categories=("role.function", "role.fame"),
        exclusive_categories=("role.fame",),
        dry_run=True,
    )

    assert result["counters"]["ready_entity_tag_operations"] == 2
    assert result["counters"]["entity_tags_would_insert"] == 1
    assert result["counters"]["blocked_planned_sibling_operations"] == 1
    assert [operation["status"] for operation in result["operations"]] == [
        "would_insert",
        "blocked_planned_sibling",
    ]
    assert result["operations"][1]["planned_sibling_tags"] == ["known"]


def test_apply_entity_tag_manifest_rejects_ready_unregistered_target() -> None:
    """Ready rows may not carry target_registered=false."""

    with pytest.raises(ValueError, match="target_registered=false"):
        apply_entity_tag_manifest(
            EntityApplyCursor(),
            _manifest(
                [
                    _operation(
                        operation_id="bad-ready",
                        status="ready",
                        review_required=False,
                        operation_type="review_entity_tag",
                        target={
                            "entity_kind": "character",
                            "entity_id": 1001,
                            "category": "role.function",
                            "tag": "missing",
                            "target_registered": False,
                        },
                    )
                ]
            ),
            manifest_schema_version="test-manifest.v1",
            entity_kind="character",
            allowed_categories=("role.function", "role.fame"),
            exclusive_categories=("role.fame",),
            dry_run=True,
        )


def _manifest(operations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "test-manifest.v1",
        "dry_run": True,
        "source": {"slot": 2, "dbname": "save_02"},
        "operations": operations,
    }


def _operation(
    *,
    operation_id: str,
    status: str,
    review_required: bool,
    operation_type: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "operation_type": operation_type,
        "status": status,
        "review_required": review_required,
        "character_id": 42,
        "character_name": "Alex",
        "entity_id": target.get("entity_id"),
        "source": {"tag": "scholar", "category": "role"},
        "target": target,
    }

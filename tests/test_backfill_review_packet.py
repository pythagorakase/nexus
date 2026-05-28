"""Tests for Slot backfill review packet helpers."""

from __future__ import annotations

from argparse import Namespace
import json

import pytest

from nexus import cli
from nexus.api.backfill_review_packet import (
    BACKFILL_REVIEW_PACKET_SCHEMA_VERSION,
    build_backfill_review_packet,
    render_backfill_review_packet_markdown,
)


def test_build_backfill_review_packet_groups_review_queues() -> None:
    """Review packets summarize current manifests without promoting rows."""

    packet = build_backfill_review_packet(
        {
            "faction": _manifest(
                "faction-migration-manifest.v1",
                [
                    _operation(
                        operation_id="faction-tag",
                        operation_type="review_entity_tag",
                        source={"column": "power_level", "value": "0.5"},
                        target={"category": "power_status", "tag": "stable"},
                    ),
                    _operation(
                        operation_id="faction-drop",
                        operation_type="drop_legacy_tag_after_review",
                        source={"column": "legacy", "value": "old"},
                        target={"destination": "drop_after_review"},
                    ),
                ],
            ),
            "character": _manifest(
                "orrery_character_manifest.v1",
                [
                    _operation(
                        operation_id="character-missing",
                        operation_type="review_entity_tag",
                        source={"category": "profession_lite", "tag": "fixer"},
                        target={
                            "category": None,
                            "tag": "fixer",
                            "target_registered": False,
                        },
                    ),
                    _operation(
                        operation_id="character-pair",
                        operation_type="resolve_pair_tag_target",
                        source={"category": "orrery_state", "tag": "contacts"},
                        target={"pair_tag": "contact:<kind>"},
                    ),
                ],
            ),
            "place": _manifest(
                "orrery_place_manifest.v1",
                [
                    _operation(
                        operation_id="place-tag",
                        operation_type="review_entity_tag",
                        source={"kind": "prose_keyword"},
                        target={
                            "category": "place_function",
                            "tag": "dwelling",
                            "target_registered": True,
                        },
                    )
                ],
            ),
        },
        slot=2,
        examples_per_queue=1,
    )

    assert packet["schema_version"] == BACKFILL_REVIEW_PACKET_SCHEMA_VERSION
    assert packet["policy"]["mutates_data"] is False
    assert packet["policy"]["promotes_ready_rows"] is False
    counters = packet["counters"]
    assert counters["operation_items"] == 5
    assert counters["ready_operations"] == 0
    assert counters["review_required_operations"] == 5
    assert counters["queue:registered_single_entity"] == 2
    assert counters["queue:missing_target_tag"] == 1
    assert counters["queue:pair_target_resolution"] == 1
    assert counters["queue:drop_after_review"] == 1


def test_render_backfill_review_packet_markdown_names_gate() -> None:
    """Markdown output should make the no-promotion policy visible."""

    packet = build_backfill_review_packet(
        {
            family: _manifest("test.v1", [])
            for family in ("faction", "character", "place")
        },
        slot=2,
    )

    markdown = render_backfill_review_packet_markdown(packet)

    assert "# Slot 2 Orrery Backfill Review Packet" in markdown
    assert "does not mark any manifest row ready" in markdown
    assert "| faction | 0 | 0 | 0 |" in markdown


def test_backfill_review_packet_rejects_slot_mismatch() -> None:
    """Manifests cannot be mixed across slots."""

    with pytest.raises(ValueError, match="character manifest slot 3"):
        build_backfill_review_packet(
            {
                "faction": _manifest("test.v1", []),
                "character": _manifest("test.v1", [], slot=3),
                "place": _manifest("test.v1", []),
            },
            slot=2,
        )


def test_cli_backfill_review_packet_writes_markdown(tmp_path) -> None:
    """CLI command loads manifest files and writes a Markdown packet."""

    faction_path = tmp_path / "faction.json"
    character_path = tmp_path / "character.json"
    place_path = tmp_path / "place.json"
    output_path = tmp_path / "packet.md"
    faction_path.write_text(
        json.dumps(_manifest("faction-migration-manifest.v1", [])),
        encoding="utf-8",
    )
    character_path.write_text(
        json.dumps(
            {"character_manifest": _manifest("orrery_character_manifest.v1", [])}
        ),
        encoding="utf-8",
    )
    place_path.write_text(
        json.dumps({"place_manifest": _manifest("orrery_place_manifest.v1", [])}),
        encoding="utf-8",
    )

    result = cli.run_backfill_review_packet(
        Namespace(
            slot=2,
            faction_manifest=faction_path,
            character_manifest=character_path,
            place_manifest=place_path,
            output=output_path,
            examples_per_queue=2,
        )
    )

    assert result["success"] is True
    assert result["packet_output"] == str(output_path)
    assert result["packet_markdown"] is None
    assert "Slot 2 Orrery Backfill Review Packet" in output_path.read_text(
        encoding="utf-8"
    )


def test_cli_backfill_review_packet_rejects_swapped_manifest_payload(tmp_path) -> None:
    """A wrong-family CLI payload should fail instead of counting zero rows."""

    faction_path = tmp_path / "faction.json"
    character_path = tmp_path / "character.json"
    place_path = tmp_path / "place.json"
    faction_path.write_text(
        json.dumps(_manifest("faction-migration-manifest.v1", [])),
        encoding="utf-8",
    )
    character_path.write_text(
        json.dumps({"place_manifest": _manifest("orrery_place_manifest.v1", [])}),
        encoding="utf-8",
    )
    place_path.write_text(
        json.dumps({"place_manifest": _manifest("orrery_place_manifest.v1", [])}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected character_manifest payload"):
        cli.run_backfill_review_packet(
            Namespace(
                slot=2,
                faction_manifest=faction_path,
                character_manifest=character_path,
                place_manifest=place_path,
                output=None,
                examples_per_queue=2,
            )
        )


def test_cli_backfill_review_packet_rejects_raw_wrong_schema(tmp_path) -> None:
    """A raw manifest with the wrong schema should fail before summarizing."""

    faction_path = tmp_path / "faction.json"
    character_path = tmp_path / "character.json"
    place_path = tmp_path / "place.json"
    faction_path.write_text(
        json.dumps(_manifest("faction-migration-manifest.v1", [])),
        encoding="utf-8",
    )
    character_path.write_text(
        json.dumps(_manifest("orrery_place_manifest.v1", [])),
        encoding="utf-8",
    )
    place_path.write_text(
        json.dumps(_manifest("orrery_place_manifest.v1", [])),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Character manifest requires"):
        cli.run_backfill_review_packet(
            Namespace(
                slot=2,
                faction_manifest=faction_path,
                character_manifest=character_path,
                place_manifest=place_path,
                output=None,
                examples_per_queue=2,
            )
        )


def _manifest(
    schema_version: str,
    operations: list[dict[str, object]],
    *,
    slot: int = 2,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "source": {"slot": slot, "dbname": f"save_{slot:02d}"},
        "operations": operations,
    }


def _operation(
    *,
    operation_id: str,
    operation_type: str,
    source: dict[str, object],
    target: dict[str, object],
) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "operation_type": operation_type,
        "status": "review_required",
        "review_required": True,
        "entity_id": 1,
        "source": source,
        "target": target,
        "reason": "Needs review.",
    }

"""Tests for faction table migration dry-run audit helpers."""

from __future__ import annotations

from argparse import Namespace
from decimal import Decimal
from typing import Any

from nexus import cli
from nexus.api.faction_table_audit import (
    LegacyTagRow,
    audit_faction_row,
    build_faction_table_audit,
)


class FakeFactionAuditConnection:
    """Context-manager connection double for faction audit CLI tests."""

    def __enter__(self) -> "FakeFactionAuditConnection":
        """Enter connection context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit connection context."""

        return None

    def cursor(self) -> "FakeFactionAuditCursor":
        """Return a context-manager cursor double."""

        return FakeFactionAuditCursor()


class FakeFactionAuditCursor:
    """Cursor double for the read-only faction audit query sequence."""

    def __init__(self) -> None:
        self._result: list[dict[str, Any]] = []
        self.executed_sql: list[str] = []

    def __enter__(self) -> "FakeFactionAuditCursor":
        """Enter cursor context."""

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit cursor context."""

        return None

    def execute(self, sql: str, params: Any = None) -> None:
        """Return canned rows for each audit query."""

        del params
        self.executed_sql.append(sql)
        if "SET TRANSACTION READ ONLY" in sql:
            self._result = []
        elif "FROM factions" in sql and "entity_tags_current" not in sql:
            self._result = [
                {
                    "id": 1,
                    "name": "Canal League",
                    "entity_id": 101,
                    "ideology": "mercantilist",
                    "history": "Founded after the river war.",
                    "current_activity": "expansion",
                    "hidden_agenda": "network",
                    "territory": "controls the canal district",
                    "primary_location": 44,
                    "power_level": Decimal("0.72"),
                    "resources": "network",
                }
            ]
        elif "FROM entity_pair_tags" in sql:
            self._result = [
                {"entity_id": 101, "tag": "claims", "active_count": 2},
            ]
        elif "FROM entity_tags_current" in sql:
            self._result = [
                {
                    "faction_id": 1,
                    "faction_name": "Canal League",
                    "entity_id": 101,
                    "category": "operational_secrecy",
                    "tag": "hidden",
                },
                {
                    "faction_id": 1,
                    "faction_name": "Canal League",
                    "entity_id": 101,
                    "category": "state",
                    "tag": "mobilized",
                },
            ]
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self) -> list[dict[str, Any]]:
        """Return rows from the most recent execute call."""

        return self._result


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


def test_build_faction_table_audit_reports_legacy_tag_and_claim_counts() -> None:
    """Audit counters should expose dry-run work and review pressure."""

    audit = build_faction_table_audit(FakeFactionAuditCursor())

    assert audit["dry_run"] is True
    assert audit["non_null_counts"]["resources"] == 1
    assert audit["counters"]["factions_scanned"] == 1
    assert audit["counters"]["active_claim_edges"] == 2
    assert audit["counters"]["legacy_operational_secrecy_tags"] == 1
    assert audit["counters"]["legacy_faction_state_tags"] == 1
    assert audit["counters"]["ambiguous_resource_values"] == 1
    assert audit["factions"][0]["review_required"] is True


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


def test_cli_faction_audit_returns_dry_run_payload(monkeypatch) -> None:
    """The faction audit CLI should resolve the slot and keep the DB read-only."""

    from nexus.api import db_pool

    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda *args, **kwargs: FakeFactionAuditConnection(),
    )

    result = cli.run_faction_audit(Namespace(slot=2))

    assert result["success"] is True
    assert result["slot"] == 2
    assert result["dbname"] == "save_02"
    assert result["faction_audit"]["dry_run"] is True
    assert result["faction_audit"]["counters"]["factions_scanned"] == 1


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
                "runtime_write_surfaces": [],
            },
        },
        as_json=False,
    )

    output = capsys.readouterr().out

    assert "active_claim_edges: 2" in output
    assert "active_operates_from_edges: 3" in output

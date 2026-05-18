"""Tests for migration discovery around Orrery's Python migration."""

from pathlib import Path

import pytest

import scripts.migrate as migrate


def test_discover_migrations_includes_python_and_skips_seed_script(
    tmp_path, monkeypatch
) -> None:
    """Managed Python migrations are discovered, but the old 008 seed is not."""

    (tmp_path / "001_baseline.sql").write_text("SELECT 1;")
    (tmp_path / "008_populate_mock_database.py").write_text("raise SystemExit")
    (tmp_path / "023_orrery_schema.py").write_text("def run(conn): pass")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", Path(tmp_path))

    discovered = migrate.discover_migrations()

    assert [(version, name, path.suffix) for version, name, path in discovered] == [
        ("001", "baseline", ".sql"),
        ("023", "orrery_schema", ".py"),
    ]


def test_relationship_valence_migration_uses_explicit_mapping() -> None:
    """Issue #213's view column uses an explicit enum-to-int contract."""

    migration_sql = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "026_relationship_valence_magnitude.sql"
    ).read_text()

    assert "valence_magnitude" in migration_sql
    assert "SUBSTRING" not in migration_sql.upper()
    assert "CASE cr.emotional_valence::text" in migration_sql
    assert "COMMENT ON COLUMN entity_relationships_v.valence_magnitude" in (
        migration_sql
    )
    for label, magnitude in {
        "+5|devoted": "5",
        "+4|admiring": "4",
        "+3|trusting": "3",
        "+2|friendly": "2",
        "+1|favorable": "1",
        "0|neutral": "0",
        "-1|wary": "-1",
        "-2|disapproving": "-2",
        "-3|resentful": "-3",
        "-4|hostile": "-4",
        "-5|hateful": "-5",
    }.items():
        assert f"WHEN '{label}' THEN {magnitude}" in migration_sql


def test_place_affordance_migration_corrects_category_conflicts() -> None:
    """Place affordance vocabulary must not silently keep wrong categories."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "030_orrery_place_affordance_vocab.py"
    ).read_text()

    assert "ON CONFLICT (tag) DO UPDATE SET" in migration_source
    assert "category = EXCLUDED.category" in migration_source
    assert "category <> 'place_affordance'" in migration_source


def test_slot2_semantic_vocab_migration_seeds_template_gate_tags() -> None:
    """Slot-2 vocabulary seed covers tags already queried by built-in templates."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "031_orrery_slot2_semantic_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    durable_tags = {tag for tag, _category, _description in migration.DURABLE_TAGS}

    # The full migration self-check validates every seeded tag and category
    # at execution time; this test pins the template-gate subset.
    assert {
        "extended_household",
        "forager",
        "hunter",
        "married",
        "parent",
        "survivalist",
        "travel_provisioned",
    } <= durable_tags


def test_slot2_semantic_vocab_assertion_rejects_runtime_drift() -> None:
    """Migration 031 self-check catches bad ephemeral policy rows."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "031_orrery_slot2_semantic_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)

    class FakeCursor:
        def execute(self, _sql, _params=None):
            return None

        def fetchall(self):
            return [
                (
                    "schismatic_internal_threat",
                    "hidden_agenda_class",
                    True,
                    "semantic",
                    "new_row",
                    {
                        "description": (
                            "cleared when the internal schism, split, or "
                            "factional threat is narratively resolved"
                        )
                    },
                )
            ]

    with pytest.raises(RuntimeError, match="mismatched"):
        migration._assert_seeded_categories(FakeCursor())


def test_slot2_semantic_vocab_documents_new_faction_categories() -> None:
    """Migration 031 names the new faction category namespaces."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "031_orrery_slot2_semantic_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    documented = {
        category for category, _description in migration.FACTION_CATEGORY_DESCRIPTIONS
    }

    assert {
        "history_class",
        "ideology_axis",
        "resource_class",
        "operational_secrecy",
        "legitimacy_status",
        "power_posture",
        "hidden_agenda_class",
    } <= documented


def test_interpersonal_need_migration_extends_need_vocab() -> None:
    """Migration 032 seeds the interpersonal need vocabulary."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "032_orrery_interpersonal_needs.py"
    )
    migration = migrate._load_python_migration(migration_path)

    assert migration.NEED_TYPES == ("socialize", "intimacy")
    assert {
        "under_socialized_1_mild",
        "under_socialized_4_critical",
        "intimacy_starved_1_mild",
        "intimacy_starved_4_critical",
        "closeted",
        "intimate_services_contact",
        "libido_absent",
    } <= {tag for tag, _category, _description in migration.SEVERITY_TAGS}
    assert {
        "socialized",
        "socialized_alone",
        "intimacy_fulfilled",
        "intimacy_pursued",
        "intimacy_partial",
        "intimacy_deferred",
    } <= {
        event_type
        for event_type, _category, _severity, _description in migration.EVENT_TYPES
    }


def test_interpersonal_need_migration_uses_safe_enum_extension_pattern() -> None:
    """Migration 032 keeps enum extension compatible with earlier migrations."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "032_orrery_interpersonal_needs.py"
    ).read_text()

    assert "def _enum_value_exists" in migration_source
    assert "ALTER TYPE character_need_type ADD VALUE {}" in migration_source
    assert "sql.Literal(need_type)" in migration_source
    assert "ADD VALUE IF NOT EXISTS" not in migration_source


def test_travel_work_migration_keeps_routing_schema_extensible() -> None:
    """Migration 033 stores estimates now while leaving space for real routes."""

    migration_path = (
        Path(__file__).parent.parent.parent / "migrations" / "033_orrery_travel_work.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert migration.TRAVEL_STATUS_VALUES == ("at_place", "planned", "in_transit")
    assert migration.TRAVEL_ROUTE_METHOD_VALUES == (
        "estimated",
        "authored_edge",
        "osm_graph",
    )
    assert {
        "walking",
        "vehicle",
        "rail",
        "water",
        "air",
        "covert",
        "mixed",
    } <= set(migration.TRAVEL_MODE_VALUES)
    assert "character_travel_states" in migration_source
    assert "orrery_travel_edges" in migration_source
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration_source
    assert "route_geometry geometry(LineString, 4326)" in migration_source
    assert "backfilled_from_current_location" in migration_source
    assert "COMMENT ON COLUMN character_travel_states.anchor_place_id" in (
        migration_source
    )
    assert "COMMENT ON COLUMN orrery_travel_edges.route_geometry" in migration_source
    assert "status <> 'planned'" in migration_source


def test_travel_work_migration_seeds_work_travel_vocab() -> None:
    """Migration 033 registers the tags and event types queried by templates."""

    migration_path = (
        Path(__file__).parent.parent.parent / "migrations" / "033_orrery_travel_work.py"
    )
    migration = migrate._load_python_migration(migration_path)

    assert {"work_obligation", "field_worker", "route_familiar", "travel_ready"} <= {
        tag for tag, _category, _description in migration.DURABLE_TAGS
    }
    assert {"workplace", "worksite", "administrative_office", "transit_hub"} <= {
        tag for tag, _description in migration.PLACE_AFFORDANCE_TAGS
    }
    assert {
        "travel_departed",
        "travel_prepared",
        "travel_progressed",
        "travel_delayed",
        "travel_arrived",
        "work_performed",
        "household_work_performed",
    } <= {
        event_type
        for event_type, _category, _severity, _description in migration.EVENT_TYPES
    }


def test_concealment_surveillance_migration_seeds_package_vocab() -> None:
    """Migration 034 registers tags/events for HIDE, SURVEIL, and contact risk."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "034_orrery_concealment_surveillance_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)

    assert {
        "cover_identity",
        "off_grid",
        "undercover",
        "presumed_dead",
        "presumed_dead_by_some",
        "long_hidden",
        "long_absent",
        "hidden_identity",
        "wanted",
        "signal_operator",
        "surveillance_capable",
        "safehouse_operator",
    } <= {tag for tag, _category, _description in migration.DURABLE_TAGS}
    ephemeral_tags = {row[0] for row in migration.EPHEMERAL_TAGS}
    assert {"contained", "immobile"} <= ephemeral_tags
    assert {"street"} <= {tag for tag, _description in migration.PLACE_AFFORDANCE_TAGS}
    assert {
        "hideout_maintained",
        "signal_exposure_reduced",
        "counter_surveillance_sweep",
        "surveillance_performed",
        "intel_reviewed",
        "contact_deferred",
    } <= {
        event_type
        for event_type, _category, _severity, _description in migration.EVENT_TYPES
    }
    migration_source = migration_path.read_text()
    assert "ON CONFLICT (type) DO UPDATE SET" in migration_source


def test_osm_route_graph_migration_adds_local_graph_tables() -> None:
    """Migration 035 adds offline graph tables instead of map API calls."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "035_orrery_osm_route_graph.py"
    ).read_text()

    assert "orrery_route_graph_nodes" in migration_source
    assert "orrery_route_graph_edges" in migration_source
    assert "orrery_place_route_graph_nodes" in migration_source
    assert "coordinates geometry(Point, 4326)" in migration_source
    assert "route_geometry geometry(LineString, 4326)" in migration_source
    assert "travel_mode orrery_travel_mode" in migration_source
    assert "COMMENT ON TABLE orrery_route_graph_nodes" in migration_source


def test_tag_category_registry_migration_covers_current_vocab_categories() -> None:
    """Migration 037 owns the entity-kind/category compatibility contract."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "037_orrery_tag_category_registry.py"
    )
    migration = migrate._load_python_migration(migration_path)
    registered = {
        (category, entity_kind)
        for category, entity_kind, _order, _description in migration.CATEGORY_REGISTRY
    }

    assert ("orrery_need", "character") in registered
    assert ("orrery_concealment", "character") in registered
    assert ("place_affordance", "place") in registered
    assert ("power_posture", "faction") in registered
    assert "tag_category_registry" in migration_path.read_text()

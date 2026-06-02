"""Tests for migration discovery around Orrery's Python migration."""

import json
from pathlib import Path
from typing import Any, Iterable

import psycopg2
import pytest

import scripts.migrate as migrate
from nexus.agents.orrery.needs import NEED_IMMUNITY_TAGS as RUNTIME_NEED_IMMUNITY_TAGS
from nexus.agents.orrery.needs import NEED_TYPES, need_applies_to_tags
from nexus.api.slot_utils import get_slot_db_url


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


def test_routine_anchor_migration_creates_explicit_schedule_surface() -> None:
    """Routine anchors model home/work facts instead of inferring from places."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "056_orrery_routine_anchors.py"
    ).read_text()

    assert "character_routine_anchors" in migration_source
    assert "orrery_routine_anchor_type" in migration_source
    assert "orrery_routine_mobility_policy" in migration_source
    assert '"works_from_home"' in migration_source
    assert "UNIQUE (character_entity_id, anchor_type)" in migration_source


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


def test_need_applicability_migration_syncs_bodyform_immunity() -> None:
    """Migration 057 updates triggers and prunes impossible bodyform need rows."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "057_orrery_need_bodyform_applicability.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert migration.NEED_TYPES == (
        "sleep",
        "hunger",
        "thirst",
        "socialize",
        "intimacy",
    )
    assert "orrery_need_applies_to_tags" in migration_source
    assert "orrery_sync_character_need_states" in migration_source
    assert "trg_entity_tags_need_state_applicability" in migration_source
    assert "DELETE FROM character_need_states" in migration_source
    assert "inorganic" in migration_source
    assert "virtual" in migration_source
    assert "libido_absent" in migration_source


def test_need_applicability_migration_matches_runtime_immunity_map() -> None:
    """Migration 057's SQL source map should stay equivalent to runtime gates."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "057_orrery_need_bodyform_applicability.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_map = {
        need_type: frozenset(tags)
        for need_type, tags in migration.NEED_IMMUNITY_TAGS.items()
    }

    assert migration_map == dict(RUNTIME_NEED_IMMUNITY_TAGS)

    tags = sorted(set().union(*migration_map.values()))
    for need_type in NEED_TYPES:
        for tag in tags:
            assert need_applies_to_tags(need_type, {tag}) is (
                tag not in migration_map[need_type]
            )


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


def test_category_refactor_phase1_migration_marks_cutover_categories() -> None:
    """Migration 043 records new category axes without rewriting live tags."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "043_orrery_category_refactor_phase1.py"
    )
    migration = migrate._load_python_migration(migration_path)
    registered = {
        (category, entity_kind)
        for category, entity_kind, _order, _description in (
            migration.NEW_CATEGORY_REGISTRY
        )
    }
    deprecated = {
        (category, entity_kind): replacements
        for category, entity_kind, replacements in (
            migration.DEPRECATED_CATEGORY_REPLACEMENTS
        )
    }

    assert {
        ("place_function", "place"),
        ("place_visibility", "place"),
        ("place_access", "place"),
        ("place_environment", "place"),
        ("place_threat", "place"),
        ("ideology", "faction"),
        ("power_status", "faction"),
        ("agenda", "faction"),
        ("resource_base", "faction"),
        ("legitimacy", "faction"),
        ("operational_mode", "faction"),
    } <= registered
    assert deprecated[("place_affordance", "place")] == (
        "place_function",
        "place_visibility",
        "place_access",
        "place_environment",
        "place_threat",
    )
    assert deprecated[("profession_lite", "character")] == ("role",)
    assert deprecated[("orrery_signal", "character")] == ("state",)
    assert deprecated[("history_class", "faction")] is None

    migration_source = migration_path.read_text()
    assert "ADD COLUMN IF NOT EXISTS deprecated" in migration_source
    assert "ADD COLUMN IF NOT EXISTS replacement_categories" in migration_source
    assert "AND entity_kind = %s::entity_kind" in migration_source
    assert "||" not in migration_source


def test_status_reputation_disambiguation_migration_updates_wizard_copy() -> None:
    """Migration 044 clarifies scoped Status vs broad Reputation/Fame."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "044_disambiguate_status_reputation_traits.sql"
    ).read_text()

    assert "known within that group" in migration_source
    assert "broadly you''re recognized beyond any one specific group" in (
        migration_source
    )
    assert "use Status instead when recognition is limited" in migration_source


def test_tag_baseline_reconciliation_migration_closes_slot_drift() -> None:
    """Migration 038 keeps template clones and existing slots on one vocab set."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "038_orrery_tag_baseline_reconciliation.py"
    )
    migration = migrate._load_python_migration(migration_path)

    assert {"intimate_services_contact", "kin_protector"} <= {
        tag for tag, _category, _description in migration.DURABLE_TAGS
    }
    assert "ON CONFLICT (tag) DO UPDATE SET" in migration_path.read_text()


def test_new_story_character_orrery_tags_migration_adds_cache_column() -> None:
    """Migration 039 preserves protagonist tags until setup transition."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "039_new_story_character_orrery_tags.py"
    ).read_text()

    assert "character_orrery_tags jsonb" in migration_source
    assert "OrreryTagBestowal JSON" in migration_source


def test_trait_compiler_substrate_migration_seeds_required_contracts() -> None:
    """Migration 045 owns the closed vocab and audit storage for issue #295."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "045_trait_compiler_substrate.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert {"role.resources", "role.fame"} == {
        category for category, _order, _description in migration.ROLE_CATEGORIES
    }
    assert {
        "destitute",
        "poor",
        "comfortable",
        "wealthy",
        "magnate",
    } <= {tag for tag, _category, _description in migration.ROLE_TAGS}
    assert {"obscure", "known", "renowned", "legendary"} <= {
        tag for tag, _category, _description in migration.ROLE_TAGS
    }
    assert {"ally", "contact", "hostile_to"} <= {
        tag for tag, *_rest in migration.PAIR_TAGS
    }
    assert {
        "status:junior",
        "status:senior",
        "status:executive",
        "status:sovereign",
        "status:respected",
        "status:elite",
        "status:outcast",
        "status:pariah",
        "status:enslaved",
    } == {tag for tag, *_rest in migration.STATUS_PAIR_TAGS}
    assert "trait_compile_result jsonb" in migration_source
    assert "SET subject_kinds = ARRAY['character', 'faction']" in migration_source
    assert "SET name = 'fame'" in migration_source


def test_canonical_grieving_migration_aliases_legacy_grief_tags() -> None:
    """Migration 046 collapses bereaved and partner grief into grieving."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "046_canonical_grieving_state.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert migration.LEGACY_TAGS == ("bereaved", "grieving_recent_partner")
    assert "'grieving', 'state', TRUE" in migration_source
    assert "'extend_expiry'::entity_tag_reapplication_policy" in migration_source
    assert "ON CONFLICT (entity_id, tag_id)" in migration_source
    assert "synonym_for = %s" in migration_source


def test_kind_qualified_contact_migration_deprecates_contact_flags() -> None:
    """Migration 047 replaces overloaded contact flags with pair-tag kinds."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "047_kind_qualified_contact_pair_tags.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert {"contact:lodging", "contact:social", "contact:intimate"} == {
        tag for tag, _description in migration.CONTACT_PAIR_TAGS
    }
    assert {"contacts_available", "intimate_services_contact"} == {
        tag for tag, _replacement_note in migration.LEGACY_CONTACT_TAGS
    }
    assert migration.LEGACY_CONTACT_PAIR_TAGS == (
        (
            "contact",
            "Replaced by kind-qualified contact pair-tags: contact:lodging, "
            "contact:social, and contact:intimate.",
        ),
    )
    assert "INSERT INTO pair_tags" in migration_source
    assert "SET deprecated = TRUE" in migration_source


def test_hunting_pair_tag_migration_retires_pursuit_vocabulary() -> None:
    """Migration 048 moves active-targeting vocabulary to hunting."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "048_orrery_hunting_pair_tag.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert "physical chase physics" in migration.PURSUING_REPLACEMENT_NOTE
    assert "who was hunting" in migration.UNDER_ACTIVE_PURSUIT_REPLACEMENT_NOTE
    assert "INSERT INTO pair_tags" in migration_source
    assert "WHERE tag = 'pursuing'" in migration_source
    assert "UPDATE entity_pair_tags" in migration_source
    assert "SET pair_tag_id = %s" in migration_source
    assert "WHERE tag = 'under_active_pursuit'" in migration_source


def test_entity_tag_expiry_substrate_migration_adds_expiry_column() -> None:
    """Migration 049 adds the scheduled-expiry column and sweeper index."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "049_orrery_entity_tag_expiry_substrate.py"
    ).read_text()

    assert "ADD COLUMN IF NOT EXISTS expires_at_world_time timestamptz" in (
        migration_source
    )
    assert "ix_entity_tags_expiring" in migration_source
    assert "WHERE cleared_at IS NULL" in migration_source
    assert "expires_at_world_time IS NOT NULL" in migration_source


def test_state_clearance_event_type_migration_registers_new_events() -> None:
    """Migration 050 registers event types named by state clear_on contracts."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "050_orrery_state_clearance_event_types.py"
    )
    migration = migrate._load_python_migration(migration_path)
    migration_source = migration_path.read_text()

    assert {
        "recovered_from_illness",
        "cured",
        "escaped",
        "revealed",
        "discovered",
        "unmasked",
        "exposed",
        "threat_removed",
        "confrontation_resolved",
        "circumstance_reversed",
    } == {
        event_type
        for event_type, _category, _severity, _description in migration.EVENT_TYPES
    }
    assert "ON CONFLICT (type) DO UPDATE SET" in migration_source
    assert "synonym_for = NULL" in migration_source


def test_time_clearance_kind_migration_extends_tag_clearance_enum() -> None:
    """Migration 051 adds the time mechanism used by expiry sweeps."""

    migration_source = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "051_orrery_time_tag_clearance_kind.py"
    ).read_text()

    assert "ALTER TYPE entity_tag_clearance_kind ADD VALUE IF NOT EXISTS" in (
        migration_source
    )
    assert 'sql.Literal("time")' in migration_source


def test_faction_tag_vocab_migration_seeds_closed_anchor_set() -> None:
    """Migration 052 seeds the closed faction vocabulary from the doc draft."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "052_orrery_faction_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    durable_tags = {
        (tag, category) for tag, category, _description in migration.DURABLE_TAGS
    }
    ephemeral_tags = {
        (tag, category)
        for tag, category, _clear_on_json, _description in migration.EPHEMERAL_TAGS
    }
    tag_names = {tag for tag, _category in durable_tags | ephemeral_tags}

    assert len(tag_names) == 65
    assert len(migration.DURABLE_TAGS) == 39
    assert len(migration.EPHEMERAL_TAGS) == 26
    assert {
        "ideology",
        "resource_base",
        "legitimacy",
        "operational_mode",
    } == {category for _tag, category in durable_tags}
    assert {"power_status", "agenda"} == {category for _tag, category in ephemeral_tags}
    assert {
        "stable",
        "capital",
        "territory",
        "underground",
        "retaliate",
    } <= tag_names
    assert "'replace'::entity_tag_reapplication_policy" in migration_path.read_text()


def test_faction_legacy_write_default_migration_drops_power_default() -> None:
    """Migration 053 should stop new inserts from creating power_level data."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "053_retire_faction_legacy_write_defaults.py"
    )
    source = migration_path.read_text()

    assert "ALTER TABLE factions" in source
    assert "ALTER COLUMN power_level DROP DEFAULT" in source
    assert "Orrery power_status tags" in source


def test_completed_tag_vocab_migration_seeds_state_and_place_anchors() -> None:
    """Migration 054 seeds completed state/place vocabulary without collisions."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "054_orrery_completed_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)

    place_durable = {
        (tag, category) for tag, category, _description in migration.PLACE_DURABLE_TAGS
    }
    place_ephemeral = {
        (tag, category)
        for tag, category, _clear_on_json, _description in (
            migration.PLACE_EPHEMERAL_TAGS
        )
    }
    state_event = {
        tag
        for tag, _clear_on_json, _reapplication_policy, _description in (
            migration.STATE_EVENT_TAGS
        )
    }
    state_time = {
        tag for tag, _reapplication_policy, _description in migration.STATE_TIME_TAGS
    }
    tag_names = (
        {tag for tag, _category in place_durable | place_ephemeral}
        | state_event
        | state_time
    )

    assert len(tag_names) == 52
    assert len(tag_names) == (
        len(migration.PLACE_DURABLE_TAGS)
        + len(migration.PLACE_EPHEMERAL_TAGS)
        + len(migration.STATE_EVENT_TAGS)
        + len(migration.STATE_TIME_TAGS)
    )
    assert len(migration.PLACE_DURABLE_TAGS) == 35
    assert len(migration.PLACE_EPHEMERAL_TAGS) == 3
    assert len(migration.STATE_EVENT_TAGS) == 10
    assert len(migration.STATE_TIME_TAGS) == 4
    assert {
        "place_known",
        "place_hidden",
        "place_open",
        "place_restricted",
        "place_contested",
        "place_medical",
        "water_source",
        "administration",
        "intoxicated:stimulant",
        "disguised",
    } <= tag_names
    assert not ({"known", "medical", "contested"} & tag_names)
    assert {
        "place_function",
        "place_visibility",
        "place_access",
        "place_environment",
    } == {category for _tag, category in place_durable}
    assert {"place_threat"} == {category for _tag, category in place_ephemeral}
    assert {
        tag for tag, _reapplication_policy, _description in migration.STATE_TIME_TAGS
    } == {
        "intoxicated:stimulant",
        "intoxicated:depressant",
        "intoxicated:hallucinogen",
        "intoxicated:dissociative",
    }
    assert {
        reapplication_policy
        for _tag, reapplication_policy, _description in migration.STATE_TIME_TAGS
    } == {"extend_expiry"}
    assert migration.ALLOWED_CATEGORY_REWRITES == {
        "wilderness": frozenset({"place_affordance"})
    }


def test_character_tag_vocab_migration_resolves_registry_collisions() -> None:
    """Migration 055 seeds durable character anchors with global tag names."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "055_orrery_character_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    expected = migration._expected_rows()
    registered = {
        (category, entity_kind)
        for category, entity_kind, _order, _description in (
            migration.NEW_CATEGORY_REGISTRY
        )
    }
    deprecated = {
        (category, entity_kind): replacements
        for category, entity_kind, replacements in (
            migration.DEPRECATED_CATEGORY_REPLACEMENTS
        )
    }

    assert {
        ("bodyform.lineage", "character"),
        ("bodyform.condition", "character"),
        ("role.function", "character"),
    } <= registered
    assert deprecated[("bodyform", "character")] == (
        "bodyform.lineage",
        "bodyform.condition",
    )
    assert deprecated[("role", "character")] == ("role.function",)
    assert deprecated[("profession_lite", "character")] == ("role.function",)
    assert expected["tradition_bound"][0] == "disposition"
    assert "traditionalist" not in expected
    assert expected["hunter"][0] == "role.function"
    assert "hunter" not in migration.CAPACITY_TAGS
    assert migration.ALLOWED_CATEGORY_REWRITES["hunter"] == frozenset(
        {"capacity", "role"}
    )
    assert len(expected) == (
        len(migration.BODYFORM_LINEAGE_TAGS)
        + len(migration.BODYFORM_CONDITION_TAGS)
        + len(migration.DISPOSITION_TAGS)
        + len(migration.CAPACITY_TAGS)
        + len(migration.ROLE_FUNCTION_TAGS)
    )
    source = migration_path.read_text()
    assert "COMMENT ON COLUMN tag_category_registry.deprecated" in source
    assert "COMMENT ON COLUMN tag_category_registry.replacement_categories" in source


def test_character_tag_vocab_guard_rejects_silent_alias_promotion() -> None:
    """Migration 055 guard should catch deprecated or synonym collisions."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "055_orrery_character_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)

    class FakeCursor:
        def execute(self, _sql: str, _params: object = None) -> None:
            return None

        def fetchall(self) -> list[tuple[str, str, bool, int | None]]:
            return [
                ("human", "bodyform", True, None),
                ("elf", "bodyform", False, 101),
            ]

    with pytest.raises(RuntimeError, match="cannot be promoted implicitly"):
        migration._assert_no_unexpected_category_conflicts(
            FakeCursor(),
            migration._expected_rows(),
        )


@pytest.mark.requires_postgres
def test_character_tag_vocab_migration_executes_against_slot_db() -> None:
    """Migration 055 executes guard, registry updates, and tag seed live."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "055_orrery_character_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    expected = migration._expected_rows()
    tag_names = list(expected)
    category_names = [
        *(
            category
            for category, _kind, _order, _description in (
                migration.NEW_CATEGORY_REGISTRY
            )
        ),
        *(
            category
            for category, _kind, _replacements in (
                migration.DEPRECATED_CATEGORY_REPLACEMENTS
            )
        ),
    ]

    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    tag_snapshot = _snapshot_tags(conn, tag_names)
    category_snapshot = _snapshot_tag_categories(conn, category_names)
    try:
        migration.run(conn)
        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag, category, is_ephemeral, deprecated, synonym_for,
                       description
                FROM tags
                WHERE tag = ANY(%s)
                """,
                (tag_names,),
            )
            rows = {row[0]: row[1:] for row in cur.fetchall()}

            cur.execute(
                """
                SELECT category, entity_kind::text, deprecated,
                       replacement_categories
                FROM tag_category_registry
                WHERE category = ANY(%s)
                """,
                (category_names,),
            )
            categories = {row[0]: row[1:] for row in cur.fetchall()}

        assert set(rows) == set(expected)
        for tag, (category, description) in expected.items():
            assert rows[tag] == (category, False, False, None, description)
        assert categories["bodyform.lineage"] == ("character", False, None)
        assert categories["bodyform.condition"] == ("character", False, None)
        assert categories["role.function"] == ("character", False, None)
        assert categories["bodyform"] == (
            "character",
            True,
            ["bodyform.lineage", "bodyform.condition"],
        )
        assert categories["role"] == ("character", True, ["role.function"])
        assert categories["profession_lite"] == (
            "character",
            True,
            ["role.function"],
        )
        assert rows["hunter"][0] == "role.function"
    finally:
        conn.rollback()
        _restore_tags(conn, tag_snapshot, tag_names)
        _restore_tag_categories(conn, category_snapshot, category_names)
        conn.close()


@pytest.mark.requires_postgres
def test_completed_tag_vocab_migration_executes_against_slot_db() -> None:
    """Migration 054 executes its guard, upserts, and post-check on a real slot."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "054_orrery_completed_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    clearance_kind_migration = migrate._load_python_migration(
        Path(__file__).parent.parent.parent
        / "migrations"
        / "051_orrery_time_tag_clearance_kind.py"
    )
    expected = migration._expected_rows()
    tag_names = list(expected)

    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    snapshot = _snapshot_tags(conn, tag_names)
    try:
        clearance_kind_migration.run(conn)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tags (
                        tag, category, is_ephemeral, clearance_kind,
                        reapplication_policy, clear_on, synonym_for,
                        deprecated, description
                    ) VALUES (
                        'wilderness', 'place_affordance', FALSE, NULL,
                        NULL, NULL, NULL, FALSE,
                        'legacy wilderness test seed.'
                    )
                    ON CONFLICT (tag) DO UPDATE SET
                        category = EXCLUDED.category,
                        is_ephemeral = EXCLUDED.is_ephemeral,
                        clearance_kind = EXCLUDED.clearance_kind,
                        reapplication_policy = EXCLUDED.reapplication_policy,
                        clear_on = EXCLUDED.clear_on,
                        synonym_for = NULL,
                        deprecated = FALSE,
                        description = EXCLUDED.description
                    """
                )

        migration.run(conn)
        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag,
                       category,
                       is_ephemeral,
                       clearance_kind::text,
                       reapplication_policy::text,
                       clear_on,
                       deprecated,
                       synonym_for,
                       description
                FROM tags
                WHERE tag = ANY(%s)
                ORDER BY tag
                """,
                (tag_names,),
            )
            rows = {
                row[0]: (
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    _normalize_jsonb(row[5]),
                    row[6],
                    row[7],
                    row[8],
                )
                for row in cur.fetchall()
            }

        assert set(rows) == set(expected)
        for tag, expected_row in expected.items():
            assert rows[tag] == (*expected_row[:-1], None, expected_row[-1])
        assert rows["wilderness"][0] == "place_environment"
        assert rows["intoxicated:stimulant"][3] == "extend_expiry"
    finally:
        conn.rollback()
        _restore_tags(conn, snapshot, tag_names)
        conn.close()


@pytest.mark.requires_postgres
def test_entity_tag_expiry_substrate_migration_executes_against_slot_db() -> None:
    """Migration 049 DDL is idempotent against a real slot schema."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "049_orrery_entity_tag_expiry_substrate.py"
    )
    migration = migrate._load_python_migration(migration_path)
    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    column_existed = _column_exists(conn, "entity_tags", "expires_at_world_time")
    index_definition_before = _index_definition(conn, "ix_entity_tags_expiring")
    try:
        migration.run(conn)
        migration.run(conn)

        assert _column_exists(conn, "entity_tags", "expires_at_world_time")
        index_definition = _index_definition(conn, "ix_entity_tags_expiring")
        assert index_definition is not None
        assert "expires_at_world_time" in index_definition
        assert "cleared_at IS NULL" in index_definition
        assert "expires_at_world_time IS NOT NULL" in index_definition
    finally:
        with conn:
            with conn.cursor() as cur:
                if index_definition_before is None:
                    cur.execute("DROP INDEX IF EXISTS ix_entity_tags_expiring")
                if not column_existed:
                    cur.execute(
                        "ALTER TABLE entity_tags "
                        "DROP COLUMN IF EXISTS expires_at_world_time"
                    )
        conn.close()


@pytest.mark.requires_postgres
def test_faction_tag_vocab_migration_executes_against_slot_db() -> None:
    """Migration 052 seeds all faction anchors idempotently against a real slot."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "052_orrery_faction_tag_vocab.py"
    )
    migration = migrate._load_python_migration(migration_path)
    durable = {
        tag: (category, description)
        for tag, category, description in migration.DURABLE_TAGS
    }
    ephemeral = {
        tag: (category, json.loads(clear_on_json), description)
        for tag, category, clear_on_json, description in migration.EPHEMERAL_TAGS
    }
    faction_tags = [*durable, *ephemeral]

    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    snapshot = _snapshot_tags(conn, faction_tags)
    try:
        migration.run(conn)
        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag, category, is_ephemeral, clearance_kind::text,
                       reapplication_policy::text, clear_on,
                       deprecated, synonym_for, description
                FROM tags
                WHERE tag = ANY(%s)
                """,
                (faction_tags,),
            )
            rows = {
                row[0]: (
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    _normalize_jsonb(row[5]),
                    row[6],
                    row[7],
                    row[8],
                )
                for row in cur.fetchall()
            }

        assert set(rows) == set(faction_tags)
        for tag, (category, description) in durable.items():
            assert rows[tag] == (
                category,
                False,
                None,
                None,
                None,
                False,
                None,
                description,
            )
        for tag, (category, clear_on, description) in ephemeral.items():
            assert rows[tag] == (
                category,
                True,
                "semantic",
                "replace",
                clear_on,
                False,
                None,
                description,
            )
    finally:
        conn.rollback()
        _restore_tags(conn, snapshot, faction_tags)
        conn.close()


@pytest.mark.requires_postgres
def test_state_clearance_event_type_migration_executes_against_slot_db() -> None:
    """Migration 050 event-type seeding is idempotent against a real slot."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "050_orrery_state_clearance_event_types.py"
    )
    migration = migrate._load_python_migration(migration_path)
    event_types = [event_type for event_type, *_rest in migration.EVENT_TYPES]
    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    snapshot = _snapshot_event_types(conn, event_types)
    try:
        migration.run(conn)
        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT type, category, severity::text, deprecated, synonym_for
                FROM event_types
                WHERE type = ANY(%s)
                """,
                (event_types,),
            )
            rows = {row[0]: row[1:] for row in cur.fetchall()}

        assert set(rows) == set(event_types)
        assert all(row[2] is False for row in rows.values())
        assert all(row[3] is None for row in rows.values())
    finally:
        _restore_event_types(conn, snapshot, event_types)
        conn.close()


@pytest.mark.requires_postgres
def test_kind_qualified_contact_migration_executes_against_slot_db() -> None:
    """Migration 047 seeds kinded contacts and deprecates legacy rows."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "047_kind_qualified_contact_pair_tags.py"
    )
    migration = migrate._load_python_migration(migration_path)
    contact_pair_tags = [tag for tag, _description in migration.CONTACT_PAIR_TAGS]
    legacy_pair_tags = [tag for tag, _note in migration.LEGACY_CONTACT_PAIR_TAGS]
    legacy_tags = [tag for tag, _note in migration.LEGACY_CONTACT_TAGS]

    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    pair_tag_names = [*contact_pair_tags, *legacy_pair_tags]
    pair_tag_snapshot = _snapshot_pair_tags(conn, pair_tag_names)
    tag_snapshot = _snapshot_tags(conn, legacy_tags)

    try:
        with conn:
            with conn.cursor() as cur:
                for tag in legacy_pair_tags:
                    cur.execute(
                        """
                        INSERT INTO pair_tags (
                            tag, subject_kinds, object_kinds,
                            is_ephemeral, clearance_kind, description, deprecated
                        ) VALUES (
                            %s,
                            ARRAY['character'],
                            ARRAY['character'],
                            FALSE,
                            NULL,
                            'legacy contact pair-tag test seed.',
                            FALSE
                        )
                        ON CONFLICT (tag) DO UPDATE SET
                            subject_kinds = EXCLUDED.subject_kinds,
                            object_kinds = EXCLUDED.object_kinds,
                            is_ephemeral = FALSE,
                            clearance_kind = NULL,
                            description = EXCLUDED.description,
                            deprecated = FALSE
                        """,
                        (tag,),
                    )
                for tag in legacy_tags:
                    cur.execute(
                        """
                        INSERT INTO tags (
                            tag, category, is_ephemeral, clearance_kind,
                            synonym_for, deprecated, description
                        ) VALUES (
                            %s,
                            'orrery_state',
                            FALSE,
                            NULL,
                            NULL,
                            FALSE,
                            'legacy contact tag test seed.'
                        )
                        ON CONFLICT (tag) DO UPDATE SET
                            category = EXCLUDED.category,
                            is_ephemeral = FALSE,
                            clearance_kind = NULL,
                            synonym_for = NULL,
                            deprecated = FALSE,
                            description = EXCLUDED.description
                        """,
                        (tag,),
                    )

        migration.run(conn)
        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag, subject_kinds, object_kinds, is_ephemeral,
                       deprecated, description
                FROM pair_tags
                WHERE tag = ANY(%s)
                """,
                (pair_tag_names,),
            )
            pair_rows = {row[0]: row[1:] for row in cur.fetchall()}
            for tag in contact_pair_tags:
                assert pair_rows[tag][0] == ["character"]
                assert pair_rows[tag][1] == ["character"]
                assert pair_rows[tag][2] is False
                assert pair_rows[tag][3] is False

            for tag in legacy_pair_tags:
                description = pair_rows[tag][4]
                assert pair_rows[tag][3] is True
                assert description.count("Replaced by") == 1

            cur.execute(
                """
                SELECT tag, deprecated, description
                FROM tags
                WHERE tag = ANY(%s)
                """,
                (legacy_tags,),
            )
            tag_rows = {row[0]: row[1:] for row in cur.fetchall()}
            for tag in legacy_tags:
                assert tag_rows[tag][0] is True
                assert tag_rows[tag][1].count("Replaced by") == 1
    finally:
        conn.rollback()
        _restore_pair_tags(conn, pair_tag_snapshot, pair_tag_names)
        _restore_tags(conn, tag_snapshot, legacy_tags)
        conn.close()


@pytest.mark.requires_postgres
def test_canonical_grieving_migration_executes_against_slot_db() -> None:
    """Migration 046 moves active legacy rows and preserves grief reapply policy."""

    migration_path = (
        Path(__file__).parent.parent.parent
        / "migrations"
        / "046_canonical_grieving_state.py"
    )
    migration = migrate._load_python_migration(migration_path)
    try:
        conn = psycopg2.connect(get_slot_db_url(dbname="save_05"))
    except psycopg2.Error as exc:
        pytest.skip(f"save_05 PostgreSQL test database unavailable: {exc}")

    created_entity_ids: list[int] = []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tag, id
                    FROM tags
                    WHERE tag = ANY(%s)
                    """,
                    (list(migration.LEGACY_TAGS),),
                )
                legacy_ids = {tag: tag_id for tag, tag_id in cur.fetchall()}
                missing = set(migration.LEGACY_TAGS) - set(legacy_ids)
                if missing:
                    pytest.skip(f"Missing legacy grief tags: {sorted(missing)}")

                for tag in migration.LEGACY_TAGS:
                    cur.execute(
                        "INSERT INTO entities (kind, is_active) "
                        "VALUES ('character', true) RETURNING id"
                    )
                    entity_id = cur.fetchone()[0]
                    created_entity_ids.append(entity_id)
                    cur.execute(
                        """
                        INSERT INTO entity_tags (entity_id, tag_id, source_kind)
                        VALUES (%s, %s, 'skald_inline')
                        """,
                        (entity_id, legacy_ids[tag]),
                    )

        migration.run(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, reapplication_policy, deprecated, synonym_for
                FROM tags
                WHERE tag = 'grieving'
                """
            )
            grieving_id, reapply, deprecated, synonym_for = cur.fetchone()
            assert reapply == "extend_expiry"
            assert deprecated is False
            assert synonym_for is None

            cur.execute(
                """
                SELECT t.tag, t.deprecated, t.synonym_for
                FROM tags t
                WHERE t.tag = ANY(%s)
                ORDER BY t.tag
                """,
                (list(migration.LEGACY_TAGS),),
            )
            assert {
                tag: (is_deprecated, alias_target)
                for tag, is_deprecated, alias_target in cur.fetchall()
            } == {tag: (True, grieving_id) for tag in migration.LEGACY_TAGS}

            cur.execute(
                """
                SELECT e.id, active.tag, legacy.tag
                FROM entities e
                JOIN entity_tags et
                  ON et.entity_id = e.id
                 AND et.cleared_at IS NULL
                JOIN tags active ON active.id = et.tag_id
                LEFT JOIN entity_tags old_et
                  ON old_et.entity_id = e.id
                 AND old_et.tag_id = ANY(%s)
                 AND old_et.cleared_at IS NULL
                LEFT JOIN tags legacy ON legacy.id = old_et.tag_id
                WHERE e.id = ANY(%s)
                ORDER BY e.id
                """,
                (
                    [legacy_ids[tag] for tag in migration.LEGACY_TAGS],
                    created_entity_ids,
                ),
            )
            assert cur.fetchall() == [
                (entity_id, "grieving", None) for entity_id in created_entity_ids
            ]
    finally:
        try:
            with conn:
                with conn.cursor() as cur:
                    if created_entity_ids:
                        cur.execute(
                            "DELETE FROM entities WHERE id = ANY(%s)",
                            (created_entity_ids,),
                        )
        finally:
            conn.close()


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            """,
            (table_name, column_name),
        )
        return cur.fetchone() is not None


def _index_definition(conn: Any, index_name: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = %s
            """,
            (index_name,),
        )
        row = cur.fetchone()
        return row[0] if row is not None else None


def _normalize_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _snapshot_event_types(
    conn: Any,
    event_types: Iterable[str],
) -> dict[str, tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT type, category, severity::text, description,
                   deprecated, synonym_for
            FROM event_types
            WHERE type = ANY(%s)
            """,
            (list(event_types),),
        )
        return {row[0]: row[1:] for row in cur.fetchall()}


def _restore_event_types(
    conn: Any,
    snapshot: dict[str, tuple[Any, ...]],
    event_types: Iterable[str],
) -> None:
    with conn:
        with conn.cursor() as cur:
            for event_type in event_types:
                row = snapshot.get(event_type)
                if row is None:
                    cur.execute(
                        "DELETE FROM event_types WHERE type = %s", (event_type,)
                    )
                    continue
                cur.execute(
                    """
                    UPDATE event_types
                    SET category = %s,
                        severity = %s::event_severity_kind,
                        description = %s,
                        deprecated = %s,
                        synonym_for = %s
                    WHERE type = %s
                    """,
                    (*row, event_type),
                )


def _snapshot_pair_tags(
    conn: Any,
    tag_names: Iterable[str],
) -> dict[str, tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tag, subject_kinds, object_kinds, is_ephemeral,
                   clearance_kind::text, reapplication_policy::text,
                   clear_on::text, deprecated, description
            FROM pair_tags
            WHERE tag = ANY(%s)
            """,
            (list(tag_names),),
        )
        return {row[0]: row[1:] for row in cur.fetchall()}


def _restore_pair_tags(
    conn: Any,
    snapshot: dict[str, tuple[Any, ...]],
    tag_names: Iterable[str],
) -> None:
    with conn:
        with conn.cursor() as cur:
            for tag in tag_names:
                row = snapshot.get(tag)
                if row is None:
                    cur.execute("DELETE FROM pair_tags WHERE tag = %s", (tag,))
                    continue
                cur.execute(
                    """
                    UPDATE pair_tags
                    SET subject_kinds = %s,
                        object_kinds = %s,
                        is_ephemeral = %s,
                        clearance_kind = %s::entity_tag_clearance_kind,
                        reapplication_policy =
                            %s::entity_tag_reapplication_policy,
                        clear_on = %s::jsonb,
                        deprecated = %s,
                        description = %s
                    WHERE tag = %s
                    """,
                    (*row, tag),
                )


def _snapshot_tags(
    conn: Any,
    tag_names: Iterable[str],
) -> dict[str, tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tag, category, is_ephemeral, clearance_kind::text,
                   reapplication_policy::text, clear_on::text, synonym_for,
                   deprecated, description
            FROM tags
            WHERE tag = ANY(%s)
            """,
            (list(tag_names),),
        )
        return {row[0]: row[1:] for row in cur.fetchall()}


def _restore_tags(
    conn: Any,
    snapshot: dict[str, tuple[Any, ...]],
    tag_names: Iterable[str],
) -> None:
    with conn:
        with conn.cursor() as cur:
            for tag in tag_names:
                row = snapshot.get(tag)
                if row is None:
                    cur.execute("DELETE FROM tags WHERE tag = %s", (tag,))
                    continue
                cur.execute(
                    """
                    UPDATE tags
                    SET category = %s,
                        is_ephemeral = %s,
                        clearance_kind = %s::entity_tag_clearance_kind,
                        reapplication_policy =
                            %s::entity_tag_reapplication_policy,
                        clear_on = %s::jsonb,
                        synonym_for = %s,
                        deprecated = %s,
                        description = %s
                    WHERE tag = %s
                    """,
                    (*row, tag),
                )


def _snapshot_tag_categories(
    conn: Any,
    category_names: Iterable[str],
) -> dict[str, tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT category, entity_kind::text, prompt_order, description,
                   deprecated, replacement_categories
            FROM tag_category_registry
            WHERE category = ANY(%s)
            """,
            (list(category_names),),
        )
        return {row[0]: row[1:] for row in cur.fetchall()}


def _restore_tag_categories(
    conn: Any,
    snapshot: dict[str, tuple[Any, ...]],
    category_names: Iterable[str],
) -> None:
    with conn:
        with conn.cursor() as cur:
            for category in category_names:
                row = snapshot.get(category)
                if row is None:
                    cur.execute(
                        "DELETE FROM tag_category_registry WHERE category = %s",
                        (category,),
                    )
                    continue
                cur.execute(
                    """
                    UPDATE tag_category_registry
                    SET entity_kind = %s::entity_kind,
                        prompt_order = %s,
                        description = %s,
                        deprecated = %s,
                        replacement_categories = %s
                    WHERE category = %s
                    """,
                    (*row, category),
                )

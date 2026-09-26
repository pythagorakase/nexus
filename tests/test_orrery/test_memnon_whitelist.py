"""Tests for MEMNON read-only SQL access to Orrery schema surfaces."""

from nexus.agents.memnon.memnon import READONLY_SQL_ALLOWED_TABLES


def test_memnon_allows_public_orrery_read_surfaces() -> None:
    """MEMNON can query Orrery public tables while internal queues stay private."""

    assert {
        "entities",
        "entity_names_v",
        "entity_tags_current",
        "character_need_states",
        "character_travel_states",
        "world_events",
        "world_event_entities",
        "orrery_resolutions",
        "orrery_travel_edges",
        "orrery_route_graph_nodes",
        "orrery_route_graph_edges",
        "orrery_place_route_graph_nodes",
        "offscreen_narrations",
        "event_types",
        "tags",
    }.issubset(READONLY_SQL_ALLOWED_TABLES)
    assert "orrery_narration_jobs" not in READONLY_SQL_ALLOWED_TABLES
    assert "tag_clearance_log" not in READONLY_SQL_ALLOWED_TABLES
    assert "entity_tags" not in READONLY_SQL_ALLOWED_TABLES


def test_memnon_whitelist_names_world_events_not_absent_legacy_events() -> None:
    """The template has no legacy ``events`` relation; ``world_events`` is canonical.

    tests/test_lore/test_entity_phase_subtraction_pg.py asserts
    ``to_regclass('events') IS NULL`` on a canonical template clone (#813).
    """

    assert "world_events" in READONLY_SQL_ALLOWED_TABLES
    assert "events" not in READONLY_SQL_ALLOWED_TABLES

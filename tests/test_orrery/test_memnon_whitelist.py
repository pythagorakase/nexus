"""Tests for MEMNON read-only SQL access to Orrery schema surfaces."""

from nexus.agents.memnon.memnon import READONLY_SQL_ALLOWED_TABLES


def test_memnon_allows_public_orrery_read_surfaces() -> None:
    """MEMNON can query Orrery public tables while internal queues stay private."""

    assert {
        "entities",
        "entity_names_v",
        "entity_tags_current",
        "character_need_states",
        "world_events",
        "world_event_entities",
        "orrery_resolutions",
        "offscreen_narrations",
        "event_types",
        "tags",
    }.issubset(READONLY_SQL_ALLOWED_TABLES)
    assert "orrery_narration_jobs" not in READONLY_SQL_ALLOWED_TABLES
    assert "tag_clearance_log" not in READONLY_SQL_ALLOWED_TABLES
    assert "entity_tags" not in READONLY_SQL_ALLOWED_TABLES

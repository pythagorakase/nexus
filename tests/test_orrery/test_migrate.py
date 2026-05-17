"""Tests for migration discovery around Orrery's Python migration."""

from pathlib import Path

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

    assert {
        "extended_household",
        "forager",
        "hunter",
        "married",
        "parent",
        "survivalist",
        "travel_provisioned",
    } <= durable_tags

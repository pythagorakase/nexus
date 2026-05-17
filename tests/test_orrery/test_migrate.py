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

    migration_sql = Path(
        "migrations/026_relationship_valence_magnitude.sql"
    ).read_text()

    assert "valence_magnitude" in migration_sql
    assert "SUBSTRING" not in migration_sql.upper()
    assert "CASE cr.emotional_valence::text" in migration_sql
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

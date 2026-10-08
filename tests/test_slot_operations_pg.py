"""Real staging builds, refusal records and sweeps on routed qa640_ databases.

All source/destination fixtures come from pg_fixtures. Staging and the explicit
orphan are the only databases created by this file's operations; teardown sweeps
only its private journal and drops only its own orphan. Owner staging is excluded.
"""

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterator
from uuid import uuid4

from psycopg2 import sql
import pytest

from nexus.api.db_pool import MaintenanceTarget, get_maintenance_connection
from nexus.api.story_identity import record_fork
from nexus.runtime.slot_operations import (
    MaintenanceTargetError,
    SlotOperation,
    StagingRefused,
    open_operation,
    read_operation,
    staging_dbname,
    sweep_staging,
)
from scripts import migrate, new_story_setup, rebuild_memory_idf
from tests.pg_fixtures import (
    connect,
    disposable_database,
    disposable_slot_database,
    route_slots_to_disposable,
    seed_played_story,
)

pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).resolve().parents[1]
DEST_SLOT = 5


def _rows(
    dbname: str, statement: str, params: tuple[Any, ...] = ()
) -> list[tuple[Any, ...]]:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall() if cur.description is not None else []


def _exists(dbname: str) -> bool:
    return bool(
        _rows("postgres", "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
    )


@pytest.fixture(scope="module")
def template() -> Iterator[str]:
    with disposable_slot_database("qa640_823s1_tpl") as dbname:
        yield dbname


@dataclass(frozen=True)
class Scenario:
    """Private destinations, source story, and isolated retained artifacts."""

    src: str
    dest: str
    dest_oid: int
    chunks: list[int]
    journal_dir: Path
    uploads_dir: Path


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Scenario]:
    with (
        disposable_database("qa640_823s1_dest") as dest,
        disposable_slot_database("qa640_823s1_src") as src,
    ):
        route_slots_to_disposable(monkeypatch.setattr, {4: src, 5: dest})
        _rows(dest, "CREATE TABLE qa640_destination_marker (value text NOT NULL)")
        _rows(dest, "INSERT INTO qa640_destination_marker VALUES ('untouched')")
        oid = int(
            _rows(
                "postgres", "SELECT oid FROM pg_database WHERE datname = %s", (dest,)
            )[0][0]
        )
        chunks = seed_played_story(src, turns=2, slot=4)
        case = Scenario(
            src, dest, oid, chunks, tmp_path / "journal", tmp_path / "uploads"
        )
        try:
            yield case
        finally:
            sweep_staging(case.journal_dir)
            assert not _rows(
                "postgres",
                "SELECT datname FROM pg_database WHERE datname LIKE %s",
                (dest + "_staging_%",),
            )
            assert _rows(
                "postgres", "SELECT oid FROM pg_database WHERE datname = %s", (dest,)
            ) == [(oid,)]
            assert _rows(dest, "SELECT value FROM qa640_destination_marker") == [
                ("untouched",)
            ]


def _snapshot(dbname: str) -> list[tuple[Any, ...]]:
    return _rows(
        dbname,
        "SELECT slot_number, (SELECT count(*) FROM narrative_chunks), "
        "(SELECT count(*) FROM chunk_metadata), "
        "(SELECT array_agg(version ORDER BY version) FROM schema_migrations) "
        "FROM global_variables WHERE id = TRUE",
    )


def _stage_clone(case: Scenario, **kwargs: Any) -> SlotOperation:
    return new_story_setup.stage_slot_clone(
        DEST_SLOT,
        case.src,
        journal_dir=case.journal_dir,
        uploads_dir=case.uploads_dir,
        **kwargs,
    )


def _target(case: Scenario, operation: SlotOperation) -> MaintenanceTarget:
    return MaintenanceTarget(
        operation.staging_db,
        operation.operation_id,
        case.journal_dir / f"{operation.operation_id}.json",
    )


def _staged_rows(
    case: Scenario, operation: SlotOperation, statement: str
) -> list[tuple[Any, ...]]:
    with (
        get_maintenance_connection(_target(case, operation)) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(statement)
        return cur.fetchall()


def _image(case: Scenario, *, exists: bool) -> None:
    ((player,),) = _rows(
        case.src, "SELECT user_character FROM global_variables WHERE id = TRUE"
    )
    relative = f"character_portraits/{player}/qa640_ok.png"
    _rows(
        case.src,
        "INSERT INTO assets.character_images "
        "(character_id, file_path, is_main, display_order) VALUES (%s, %s, 0, 0)",
        (player, "/" + relative),
    )
    if exists:
        path = case.uploads_dir / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"qa640 referenced image")


def test_stage_from_template_validates_without_touching_destination(
    template: str, scenario: Scenario
) -> None:
    operation = new_story_setup.stage_slot_from_template(
        5,
        source_db=template,
        journal_dir=scenario.journal_dir,
        uploads_dir=scenario.uploads_dir,
    )
    assert operation.phase == "validated"
    assert operation.staging_db == staging_dbname(scenario.dest, operation.operation_id)
    assert {
        row[0]
        for row in _staged_rows(
            scenario, operation, "SELECT version FROM schema_migrations"
        )
    } == {version for version, _, _ in migrate.discover_migrations()}
    assert _staged_rows(
        scenario, operation, "SELECT slot_number FROM global_variables"
    ) == [(5,)]
    assert _staged_rows(
        scenario,
        operation,
        "SELECT corpus_kind, document_count, "
        "analyzer_version = 'pg_catalog.english/v1/' || "
        "current_setting('server_version_num') "
        "FROM memory_idf_corpora ORDER BY corpus_kind",
    ) == [("narrative", 0, True), ("retrograde_summary", 0, True)]
    assert _staged_rows(scenario, operation, "SELECT origin FROM story_identity") == [
        ("wizard",)
    ]
    assert _staged_rows(scenario, operation, "SELECT count(*) FROM story_lineage") == [
        (0,)
    ]


def test_stage_clone_of_played_story_validates(scenario: Scenario) -> None:
    _image(scenario, exists=True)
    before = _snapshot(scenario.src)
    ((parent,),) = _rows(scenario.src, "SELECT story_uuid::text FROM story_identity")
    with closing(connect(scenario.src)) as conn, conn, conn.cursor() as cur:
        record_fork(
            cur,
            child_uuid=parent,
            parent_uuid=str(uuid4()),
            source_dbname="qa640_823s1_ancestor",
            evidence="prior copied lineage must not survive",
        )
    operation = _stage_clone(scenario)
    assert operation.phase == "validated"
    assert _staged_rows(
        scenario,
        operation,
        "SELECT (SELECT count(*) FROM narrative_chunks), new_story, slot_number "
        "FROM global_variables",
    ) == [(2, True, 5)]
    ((child, origin),) = _staged_rows(
        scenario, operation, "SELECT story_uuid::text, origin FROM story_identity"
    )
    assert child != parent and origin == "clone"
    assert _staged_rows(
        scenario,
        operation,
        "SELECT parent_uuid::text, source_dbname FROM story_lineage",
    ) == [(parent, scenario.src)]
    assert _snapshot(scenario.src) == before
    assert _rows(scenario.src, "SELECT count(*) FROM story_lineage") == [(1,)]


def test_clone_staging_runs_pending_migrations(
    scenario: Scenario, tmp_path: Path
) -> None:
    tree = tmp_path / "migrations"
    shutil.copytree(ROOT / "migrations", tree)
    (tree / "999_qa640_probe.sql").write_text(
        "CREATE TABLE qa640_823s1_probe (id int); "
        "COMMENT ON TABLE qa640_823s1_probe IS 'Test probe.';"
    )
    operation = _stage_clone(scenario, migrations_dir=tree)
    assert operation.phase == "validated"
    assert _staged_rows(
        scenario,
        operation,
        "SELECT version FROM schema_migrations WHERE version = '999'",
    ) == [("999",)]
    assert _staged_rows(
        scenario, operation, "SELECT to_regclass('qa640_823s1_probe') IS NOT NULL"
    ) == [(True,)]
    assert (
        _rows(
            scenario.src, "SELECT version FROM schema_migrations WHERE version = '999'"
        )
        == []
    )
    assert _rows(scenario.src, "SELECT to_regclass('qa640_823s1_probe')") == [(None,)]


@pytest.mark.parametrize(
    "defect, prefix",
    [
        ("pins", "pins:"),
        ("pass2_missing", "pass2:"),
        ("pass2_fingerprint", "pass2:"),
        ("stamps", "stamps:"),
        ("clock", "invariants:"),
        ("assets", "assets:"),
    ],
)
def test_clone_staging_refuses(scenario: Scenario, defect: str, prefix: str) -> None:
    tail = scenario.chunks[-1]
    if defect == "pins":
        _rows(scenario.src, "UPDATE global_variables SET model = 'qa640-unregistered'")
    elif defect == "pass2_missing":
        _rows(
            scenario.src, "DELETE FROM lore_pass_baselines WHERE chunk_id = %s", (tail,)
        )
    elif defect == "pass2_fingerprint":
        _rows(
            scenario.src,
            "UPDATE lore_pass_baselines SET payload = jsonb_set(payload, "
            "'{config_fingerprint}', to_jsonb(%s::text)) WHERE chunk_id = %s",
            ("0" * 64, tail),
        )
    elif defect == "stamps":
        _rows(
            scenario.src,
            "INSERT INTO schema_migrations (version, name) "
            "VALUES ('998', 'qa640_unknown')",
        )
    elif defect == "clock":
        _rows(
            scenario.src,
            "UPDATE chunk_metadata SET world_time = "
            "world_time + interval '1 hour' WHERE chunk_id = %s",
            (tail,),
        )
    else:
        _image(scenario, exists=False)
    with pytest.raises(StagingRefused) as caught:
        _stage_clone(scenario)
    error = caught.value
    assert error.operation.phase == "refused"
    assert error.refusals and all(
        reason.startswith(prefix) for reason in error.refusals
    )
    assert prefix in str(error) and str(error.journal_path) in str(error)
    assert _exists(error.operation.staging_db)
    assert read_operation(error.journal_path) == error.operation
    target = _target(scenario, error.operation)
    with pytest.raises(MaintenanceTargetError):
        with get_maintenance_connection(target):
            pytest.fail("Refused build remained authorized")
    with pytest.raises(MaintenanceTargetError):
        migrate.migrate_database(
            target.dbname, skip_locked=False, maintenance_target=target
        )
    with pytest.raises(MaintenanceTargetError):
        rebuild_memory_idf.rebuild_database(target.dbname, maintenance_target=target)


def test_unstamped_clone_fails_before_migrating(scenario: Scenario) -> None:
    _rows(scenario.src, "DELETE FROM schema_migrations")
    with pytest.raises(RuntimeError, match="empty schema_migrations"):
        _stage_clone(scenario)
    (path,) = scenario.journal_dir.glob("*.json")
    record = read_operation(path)
    assert record.phase == "failed"
    assert _exists(record.staging_db)
    # A refused target cannot use production maintenance admission; inspect only
    # this exact owned qa640_ name through the disposable fixture connection.
    assert record.staging_db.startswith(scenario.dest + "_staging_")
    assert _rows(record.staging_db, "SELECT count(*) FROM schema_migrations") == [(0,)]


def test_stale_idf_key_is_rebuilt_in_staging(scenario: Scenario) -> None:
    _rows(
        scenario.src,
        "UPDATE memory_idf_corpora SET analyzer_version = 'pg_catalog.english/v1/0'",
    )
    operation = _stage_clone(scenario)
    assert operation.phase == "validated"
    assert _staged_rows(
        scenario,
        operation,
        "SELECT bool_and(analyzer_version = 'pg_catalog.english/v1/' || "
        "current_setting('server_version_num')) FROM memory_idf_corpora",
    ) == [(True,)]
    assert _rows(
        scenario.src, "SELECT DISTINCT analyzer_version FROM memory_idf_corpora"
    ) == [("pg_catalog.english/v1/0",)]


def _child(script: str, *args: str) -> Any:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["NEXUS_KEYRING_DISABLE"] = "1"
    env["NEXUS_TEST_PROVIDER_ONLY"] = "1"
    # Authorization must survive without the parent's routing state.
    env.pop("NEXUS_ROUTED_SLOT", None)
    env.pop("NEXUS_ROUTED_SLOT_DATABASE", None)
    completed = subprocess.run(
        [sys.executable, "-c", script, *args],
        env=env,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    return json.loads(completed.stdout)


def test_journal_survives_a_new_process(template: str, scenario: Scenario) -> None:
    operation = new_story_setup.stage_slot_from_template(
        5,
        source_db=template,
        journal_dir=scenario.journal_dir,
        uploads_dir=scenario.uploads_dir,
    )
    path = scenario.journal_dir / f"{operation.operation_id}.json"
    report = _child(
        """
from dataclasses import asdict
import json, sys
from pathlib import Path
from nexus.api.db_pool import MaintenanceTarget, get_maintenance_connection
from nexus.runtime.slot_operations import read_operation, sweep_staging
path = Path(sys.argv[1])
record = read_operation(path)
assert record.staging_db.startswith('qa640_823s1_dest_')
target = MaintenanceTarget(record.staging_db, record.operation_id, path)
with get_maintenance_connection(target) as conn, conn.cursor() as cur:
    cur.execute('SELECT slot_number FROM global_variables')
    slot = cur.fetchone()[0]
print(json.dumps({'slot': slot, 'sweep': asdict(sweep_staging(path.parent))}))
""",
        str(path),
    )
    assert report["slot"] == 5
    assert report["sweep"]["dropped"] == [operation.staging_db]
    assert read_operation(path).phase == "swept"
    assert not _exists(operation.staging_db)
    assert sweep_staging(scenario.journal_dir).dropped == []


def test_sweep_skips_a_held_operation_and_reports_unowned(scenario: Scenario) -> None:
    handle = open_operation(
        "stage_clone", slot=5, source_db=scenario.src, journal_dir=scenario.journal_dir
    )
    handle.advance("building")
    orphan = f"qa640_823s1_orphan_staging_{uuid4().hex[:12]}"
    script = """
from dataclasses import asdict
import json, sys
from pathlib import Path
from nexus.runtime.slot_operations import sweep_staging
print(json.dumps(asdict(sweep_staging(Path(sys.argv[1])))))
"""
    try:
        with closing(connect("postgres")) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                for name in (handle.record.staging_db, orphan):
                    assert name.startswith("qa640_")
                    cur.execute(
                        sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                            sql.Identifier(name)
                        )
                    )
        first = _child(script, str(scenario.journal_dir))
        assert first["dropped"] == []
        assert first["in_use"] == [handle.record.staging_db]
        assert orphan in first["unowned"]
        handle.close()
        second = _child(script, str(scenario.journal_dir))
        assert second["dropped"] == [handle.record.staging_db]
        assert orphan in second["unowned"]
        assert _exists(orphan)
    finally:
        handle.close()
        with closing(connect("postgres")) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(orphan)
                    )
                )


def test_runner_target_mismatch_refuses_without_checkout(scenario: Scenario) -> None:
    handle = open_operation(
        "stage_clone", slot=5, source_db=scenario.src, journal_dir=scenario.journal_dir
    )
    try:
        with pytest.raises(ValueError, match="does not match"):
            migrate.migrate_database(scenario.src, maintenance_target=handle.target)
        with pytest.raises(ValueError, match="does not match"):
            rebuild_memory_idf.rebuild_database(
                scenario.src, maintenance_target=handle.target
            )
    finally:
        handle.close()

"""Pure contract checks for migration 078 orchestration order."""

from pathlib import Path
from types import ModuleType

import pytest

from nexus.agents.orrery.retrograde_maturation import (
    MATURATION_MANIFEST_SCHEMA_VERSION,
)
import scripts.migrate as migrate


@pytest.fixture()
def migration() -> ModuleType:
    return migrate._load_python_migration(
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    )


def test_migration_locks_all_legacy_writers_before_reading_rows() -> None:
    """Writer exclusion must precede embedding discovery and legacy reads."""

    source = (
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    ).read_text(encoding="utf-8")

    lock_call = source.index("_lock_legacy_writers(cur)")
    discovery_call = source.index("_discover_source_embedding_tables(cur)")
    dynamic_lock_call = source.index("_lock_source_embedding_tables(cur")
    legacy_read_call = source.index("_load_and_validate_legacy_rows(cur)")
    assert lock_call < discovery_call < dynamic_lock_call < legacy_read_call

    lock_body = source[
        source.index("def _lock_legacy_writers") : source.index(
            "def _lock_source_embedding_tables"
        )
    ]
    for table_name in (
        "world_events",
        "narrative_chunks",
        "chunk_metadata",
        "orrery_maturation_jobs",
    ):
        assert table_name in lock_body
    assert "ACCESS EXCLUSIVE" in lock_body


def test_runtime_and_migration_use_manifest_v1(migration: ModuleType) -> None:
    assert MATURATION_MANIFEST_SCHEMA_VERSION == (
        "orrery_retrograde_maturation_manifest.v1"
    )
    assert migration.TARGET_MANIFEST_SCHEMA_VERSION == (
        MATURATION_MANIFEST_SCHEMA_VERSION
    )


def test_manifest_rewrite_is_strict_and_changes_typed_identity(
    migration: ModuleType,
) -> None:
    rewritten = migration._rewrite_maturation_manifest(
        job_id=7,
        raw_manifest={
            "schema_version": "orrery_retrograde_maturation_manifest.v0",
            "persisted": True,
            "embedding_pending_chunk_ids": [41],
            "embedding": {
                "status": "succeeded",
                "results": [{"chunk_id": 41, "job_id": "embed-41"}],
            },
        },
        legacy_id_set={41},
        legacy_owner_by_summary={41: 7},
    )

    assert rewritten["schema_version"] == ("orrery_retrograde_maturation_manifest.v1")
    assert rewritten["embedding_pending_summary_ids"] == [41]
    assert "embedding_pending_chunk_ids" not in rewritten
    assert rewritten["embedding"]["results"] == [
        {"summary_id": 41, "job_id": "embed-41"}
    ]


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v1",
                "persisted": False,
            },
            "expected.*v0",
        ),
        (
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v0",
                "persisted": True,
                "embedding_pending_chunk_ids": ["41"],
            },
            "positive integer",
        ),
        (
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v0",
                "persisted": True,
            },
            "no legacy pending-chunk key",
        ),
    ],
)
def test_manifest_rewrite_rejects_ambiguous_v0_shapes(
    migration: ModuleType,
    manifest: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        migration._rewrite_maturation_manifest(
            job_id=7,
            raw_manifest=manifest,
            legacy_id_set={41},
            legacy_owner_by_summary={41: 7},
        )


def test_runtime_boundary_trusts_validated_durable_job(migration: ModuleType) -> None:
    class _BoundaryCursor:
        def __init__(self) -> None:
            self.statement = ""
            self.params: object = None

        def execute(self, statement: str, params: object = None) -> None:
            self.statement = statement
            self.params = params

        def fetchone(self) -> tuple[int, int]:
            return (37, 37)

    cursor = _BoundaryCursor()
    boundary = migration._resolve_event_recording_boundary(
        cursor,
        event_ref="maturation_job_7_event_003",
        prologue_ids=[1],
        artifact="test event",
    )

    assert boundary == 37
    assert cursor.params == (7,)
    assert "orrery_maturation_jobs" in cursor.statement
    assert "LEFT JOIN narrative_chunks" in cursor.statement
    assert "ORDER BY" not in cursor.statement


def test_nested_maturation_request_resolves_to_surviving_root(
    migration: ModuleType,
) -> None:
    jobs = {
        21: (1447, {}, False),
        22: (1456, {}, False),
    }
    owner_by_summary = {1456: 21}

    assert (
        migration._resolve_surviving_job_request(
            job_id=22,
            jobs=jobs,
            owner_by_summary=owner_by_summary,
        )
        == 1447
    )


def test_nested_maturation_request_rejects_owner_cycles(
    migration: ModuleType,
) -> None:
    jobs = {
        21: (1457, {}, False),
        22: (1456, {}, False),
    }
    owner_by_summary = {
        1456: 21,
        1457: 22,
    }

    with pytest.raises(RuntimeError, match="ancestry cycle"):
        migration._resolve_surviving_job_request(
            job_id=22,
            jobs=jobs,
            owner_by_summary=owner_by_summary,
        )


def test_nested_maturation_request_rejects_ownerless_summary(
    migration: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="without a maturation-job owner"):
        migration._resolve_surviving_job_request(
            job_id=22,
            jobs={22: (1456, {}, False)},
            owner_by_summary={1456: None},
        )


def test_nested_maturation_request_rejects_missing_owner_job(
    migration: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="names missing owner job"):
        migration._resolve_surviving_job_request(
            job_id=22,
            jobs={22: (1456, {}, False)},
            owner_by_summary={1456: 21},
        )


def test_migration_installs_guards_after_legacy_cleanup() -> None:
    source = (
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    ).read_text(encoding="utf-8")

    assert source.index("_delete_legacy_chunks(cur") < source.index(
        "_install_legacy_write_guards(cur)"
    )
    assert source.index("_install_legacy_write_guards(cur)") < source.index(
        "_validate_postconditions("
    )
    assert "trg_narrative_chunks_reject_retrograde_summary" in source
    assert "trg_world_events_reject_retrograde_summary_link" in source
    assert "trg_orrery_maturation_jobs_require_manifest_v1" in source
    assert "_copy_backfill_summaries(cur" in source
    assert "_require_embedding_stamp_coverage(cur" in source


def test_manifest_guard_allows_only_empty_or_v1_manifests(
    migration: ModuleType,
) -> None:
    class _RecordingCursor:
        def __init__(self) -> None:
            self.statement = ""
            self.params: object = None

        def execute(self, statement: str, params: object = None) -> None:
            self.statement = statement
            self.params = params

    cursor = _RecordingCursor()
    migration._install_legacy_write_guards(cursor)

    assert cursor.params == (migration.TARGET_MANIFEST_SCHEMA_VERSION,)
    for guard_clause in (
        "NEW.result_manifest IS NULL",
        "NEW.result_manifest = '{}'::jsonb",
        "jsonb_typeof(NEW.result_manifest) IS DISTINCT FROM 'object'",
        "NEW.result_manifest ? 'embedding_pending_chunk_ids'",
        "NEW.result_manifest #> '{embedding,results}'",
        "result.value ? 'chunk_id'",
        "BEFORE INSERT OR UPDATE OF result_manifest",
    ):
        assert guard_clause in cursor.statement


def test_postconditions_require_all_guards_to_be_enabled() -> None:
    source = (
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    ).read_text(encoding="utf-8")
    postconditions = source[source.index("def _validate_postconditions") :]

    assert "trg_orrery_maturation_jobs_require_manifest_v1" in postconditions
    assert "tgenabled <> 'D'" in postconditions
    assert "guard_count != 3" in postconditions

"""Durable ownership and validation for slot builds kept beside live slots."""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import fcntl
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nexus.api.db_pool import MaintenanceTarget, get_maintenance_connection
from nexus.api.slot_utils import slot_dbname
from nexus.database import connection_kwargs

Phase = Literal[
    "created", "building", "built", "validated", "refused", "failed", "swept"
]
OperationKind = Literal["stage_template", "stage_clone"]


class SlotOperationError(RuntimeError):
    """The durable operation record is invalid or a transition is forbidden."""


class MaintenanceTargetError(RuntimeError):
    """A journal does not currently authorize the requested staging database."""


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("Operation timestamps must be aware UTC")
    return value.astimezone(timezone.utc)


class OperationStep(BaseModel):
    """One durable phase entry, with its operator-facing detail."""

    model_config = ConfigDict(extra="forbid")
    phase: Phase
    at: datetime
    detail: str | None = None

    @field_validator("at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        """Reject naive or non-UTC history timestamps."""
        return _utc(value)


class SlotOperation(BaseModel):
    """Versioned journal record; only its derived staging name is owned."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: OperationKind
    slot: int = Field(ge=1, le=5)
    destination_db: str
    source_db: str
    staging_db: str
    pid: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime
    phase: Phase
    history: list[OperationStep]
    refusals: list[str] = Field(default_factory=list)
    error: str | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        """Reject naive or non-UTC operation timestamps."""
        return _utc(value)


class StagingRefused(RuntimeError):
    """A completed build is retained because one or more validations refused it."""

    def __init__(self, operation: SlotOperation, journal_path: Path):
        self.operation = operation
        self.refusals = list(operation.refusals)
        self.journal_path = journal_path
        super().__init__(
            f"Staging database {operation.staging_db} refused: "
            + "; ".join(self.refusals)
            + f" (journal {journal_path})"
        )


def default_journal_dir() -> Path:
    """Resolve the configured journal directory without creating it."""
    from nexus.runtime.home import resolve_runtime_home

    return resolve_runtime_home().state_dir / "slot_operations"


def staging_dbname(destination_db: str, operation_id: str) -> str:
    """Derive the exact owned name without PostgreSQL identifier truncation."""
    name = f"{destination_db}_staging_{operation_id[:12]}"
    if len(name.encode("utf-8")) > 63:
        raise ValueError("Staging database name exceeds PostgreSQL's 63-byte limit")
    return name


def read_operation(path: Path) -> SlotOperation:
    """Read and validate an existing record; malformed state is never skipped."""
    try:
        return SlotOperation.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlotOperationError(f"Invalid operation journal {path}: {exc}") from exc


def _write_operation(path: Path, record: SlotOperation) -> None:
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(record.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _advanced(
    record: SlotOperation,
    phase: Phase,
    *,
    detail: str | None = None,
    refusals: list[str] | None = None,
    error: str | None = None,
) -> SlotOperation:
    legal = {
        "created": {"building", "failed", "swept"},
        "building": {"built", "failed", "swept"},
        "built": {"validated", "refused", "failed", "swept"},
        "validated": {"swept"},
        "refused": {"swept"},
        "failed": {"swept"},
        "swept": set(),
    }
    if phase not in legal[record.phase]:
        raise SlotOperationError(
            f"Illegal slot operation move {record.phase} -> {phase}"
        )
    now = datetime.now(timezone.utc)
    return SlotOperation.model_validate(
        {
            **record.model_dump(),
            "phase": phase,
            "updated_at": now,
            "history": [
                *record.history,
                OperationStep(phase=phase, at=now, detail=detail),
            ],
            "refusals": record.refusals if refusals is None else refusals,
            "error": record.error if error is None else error,
        }
    )


class OperationHandle:
    """Hold exclusive operation ownership until close or process death."""

    def __init__(self, record: SlotOperation, path: Path, lock_fd: int):
        self.record = record
        self.path = path
        self._lock_fd: int | None = lock_fd

    @property
    def target(self) -> MaintenanceTarget:
        """Return the explicit target revalidated by every database checkout."""
        return MaintenanceTarget(
            self.record.staging_db, self.record.operation_id, self.path
        )

    def advance(
        self,
        phase: Phase,
        *,
        detail: str | None = None,
        refusals: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        """Persist one legal phase transition before exposing it to the caller."""
        if self._lock_fd is None:
            raise SlotOperationError("Operation handle is closed")
        updated = _advanced(
            self.record, phase, detail=detail, refusals=refusals, error=error
        )
        _write_operation(self.path, updated)
        self.record = updated

    def close(self) -> None:
        """Release ownership exactly once; the durable record remains."""
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None


def open_operation(
    kind: OperationKind,
    *,
    slot: int,
    source_db: str,
    journal_dir: Path | None = None,
) -> OperationHandle:
    """Create and lock the journal before a staging build can create its database."""
    destination = slot_dbname(slot)
    operation_id = uuid4().hex
    now = datetime.now(timezone.utc)
    record = SlotOperation(
        operation_id=operation_id,
        kind=kind,
        slot=slot,
        destination_db=destination,
        source_db=source_db,
        staging_db=staging_dbname(destination, operation_id),
        pid=os.getpid(),
        created_at=now,
        updated_at=now,
        phase="created",
        history=[OperationStep(phase="created", at=now)],
    )
    directory = default_journal_dir() if journal_dir is None else journal_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{operation_id}.json"
    lock_fd = os.open(
        path.with_suffix(".lock"), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _write_operation(path, record)
    except BaseException:
        os.close(lock_fd)
        raise
    return OperationHandle(record, path, lock_fd)


def require_authorized(target: MaintenanceTarget) -> SlotOperation:
    """Re-read durable authorization without consulting process-local slot routing."""
    try:
        record = read_operation(target.journal_path)
        expected = staging_dbname(record.destination_db, record.operation_id)
    except (SlotOperationError, ValueError) as exc:
        raise MaintenanceTargetError(str(exc)) from exc
    if (
        target.journal_path.name != f"{target.operation_id}.json"
        or record.operation_id != target.operation_id
        or record.staging_db != target.dbname
        or record.staging_db != expected
        or record.phase not in {"building", "built", "validated"}
    ):
        raise MaintenanceTargetError(
            f"Journal {target.journal_path} does not authorize {target.dbname} "
            f"in phase {record.phase}"
        )
    return record


def validate_staging(
    target: MaintenanceTarget,
    *,
    slot: int,
    uploads_dir: Path | None = None,
    migrations_dir: Path | None = None,
) -> list[str]:
    """Collect staging refusals in one repeatable-read, read-only transaction."""
    from nexus.agents.orrery.replay import (
        verify_checkpoints_sync,
        verify_chunk_clocks_sync,
    )
    from nexus.config import load_settings
    from nexus.config.story_model import (
        AUXILIARY_SEATS,
        StorySettings,
        resolve_seat,
        story_context_settings,
    )
    from nexus.memory.context_state import parse_pass2_baseline
    from nexus.memory.manager import incompatible_pass2_baseline_reason
    from nexus.runtime.home import UPLOADS_DIR, repo_root
    from scripts.migrate import SCRIPT_ONLY_MIGRATIONS, discover_migrations
    from scripts.replay_state import _verify_correspondence_provenance

    # #820 moves uploads into the runtime home; until then the endpoints serve the checkout.  # noqa: E501
    uploads = (
        repo_root() / UPLOADS_DIR if uploads_dir is None else uploads_dir
    ).resolve()
    expected_stamps = {version for version, _, _ in discover_migrations(migrations_dir)}
    settings = load_settings()
    refusals: list[str] = []
    with get_maintenance_connection(target) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            stamped = {row[0] for row in cur.fetchall()}
            refusals.extend(
                f"stamps: missing {version}"
                for version in sorted(expected_stamps - stamped)
            )
            refusals.extend(
                f"stamps: unknown {version}"
                for version in sorted(
                    stamped - expected_stamps - SCRIPT_ONLY_MIGRATIONS
                )
            )
            cur.execute(
                "SELECT model, gaia_model, apex_context_window, slot_number "
                "FROM global_variables WHERE id = TRUE"
            )
            row = cur.fetchone()
            story = None
            if row is None:
                refusals.append("story: global_variables row is missing")
            else:
                if row[3] != slot:
                    refusals.append(f"slot: slot_number is {row[3]!r}, expected {slot}")
                try:
                    story = StorySettings(
                        skald_model=row[0],
                        gaia_model=row[1],
                        apex_context_window=row[2],
                        slot=slot,
                        dbname=target.dbname,
                    )
                except (
                    ValidationError
                ) as exc:  # nexus-exception-disposition: fail; reason=a validation failure becomes a staging refusal; safety=the refusal blocks the operation and the staging database is kept  # noqa: E501
                    refusals.append(f"story: {exc}")
            if story is not None:
                for seat in ("skald", "gaia", *AUXILIARY_SEATS):
                    try:
                        resolve_seat(seat, settings=settings, story=story)
                    except (
                        ValueError
                    ) as exc:  # nexus-exception-disposition: fail; reason=a validation failure becomes a staging refusal; safety=the refusal blocks the operation and the staging database is kept  # noqa: E501
                        refusals.append(f"pins: {seat}: {exc}")
                cur.execute("SELECT max(id) FROM narrative_chunks")
                chunk_id = cur.fetchone()[0]
                if chunk_id is not None:
                    cur.execute(
                        "SELECT schema_version, payload FROM lore_pass_baselines "
                        "WHERE chunk_id = %s",
                        (chunk_id,),
                    )
                    baseline_row = cur.fetchone()
                    if baseline_row is None:
                        refusals.append(f"pass2: chunk {chunk_id} has no baseline")
                    else:
                        try:
                            baseline = parse_pass2_baseline(baseline_row[1])
                        except (
                            ValidationError
                        ) as exc:  # nexus-exception-disposition: fail; reason=a validation failure becomes a staging refusal; safety=the refusal blocks the operation and the staging database is kept  # noqa: E501
                            refusals.append(f"pass2: chunk {chunk_id}: {exc}")
                        else:
                            if baseline_row[0] != baseline.schema_version:
                                refusals.append(
                                    f"pass2: chunk {chunk_id} schema columns disagree"
                                )
                            if baseline.parent_chunk_id != chunk_id:
                                refusals.append(
                                    f"pass2: chunk {chunk_id} parent identity "
                                    f"mismatch ({baseline.parent_chunk_id})"
                                )
                            reason = incompatible_pass2_baseline_reason(
                                baseline, story_context_settings(settings, story)
                            )
                            if reason is not None:
                                refusals.append(f"pass2: chunk {chunk_id}: {reason}")
            cur.execute(
                "SELECT 'pg_catalog.english/v1/' || "
                "current_setting('server_version_num')"
            )
            live_key = cur.fetchone()[0]
            cur.execute("SELECT corpus_kind, analyzer_version FROM memory_idf_corpora")
            corpora = dict(cur.fetchall())
            for kind in ("narrative", "retrograde_summary"):
                if kind not in corpora:
                    refusals.append(f"idf: missing {kind} corpus")
                elif corpora[kind] != live_key:
                    refusals.append(
                        f"idf: {kind} analyzer {corpora[kind]!r}, expected {live_key}"
                    )
            for verdict in verify_checkpoints_sync(cur):
                if verdict.drifts:
                    refusals.append(
                        f"invariants: checkpoints {verdict.base_checkpoint_id} -> "
                        f"{verdict.target_checkpoint_id}: "
                        f"{len(verdict.drifts)} drifts; {asdict(verdict.drifts[0])}"
                    )
            clock_findings = verify_chunk_clocks_sync(cur)
            if clock_findings:
                refusals.append(
                    f"invariants: {len(clock_findings)} chunk clock findings; "
                    f"{asdict(clock_findings[0])}"
                )
            refusals.extend(
                f"invariants: {finding}"
                for finding in _verify_correspondence_provenance(cur)
            )
            cur.execute(
                "SELECT file_path FROM assets.character_images UNION ALL "
                "SELECT file_path FROM assets.place_images"
            )
            missing = []
            for (file_path,) in cur.fetchall():
                path = (uploads / file_path.lstrip("/")).resolve()
                if not path.is_relative_to(uploads) or not path.is_file():
                    missing.append(file_path)
            if missing:
                refusals.append(
                    f"assets: {len(missing)} missing or outside uploads: {missing[:5]}"
                )
    return refusals


@dataclass
class SweepReport:
    """Exact journal-owned drops, live locks and unowned staging names."""

    dropped: list[str] = field(default_factory=list)
    in_use: list[str] = field(default_factory=list)
    unowned: list[str] = field(default_factory=list)


def sweep_staging(journal_dir: Path | None = None) -> SweepReport:
    """Drop only unlocked journal-derived staging names; report all other names."""
    directory = default_journal_dir() if journal_dir is None else journal_dir
    report = SweepReport()
    owned: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        record = read_operation(path)
        owned.add(record.staging_db)
        if record.phase == "swept":
            continue
        lock_fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (
                BlockingIOError
            ):  # nexus-exception-disposition: safe-continuation; reason=a live process holds the operation lock; safety=its staging database and record are left untouched  # noqa: E501
                report.in_use.append(record.staging_db)
                continue
            record = read_operation(path)
            if (
                path.name != f"{record.operation_id}.json"
                or record.staging_db
                != staging_dbname(record.destination_db, record.operation_id)
            ):
                raise SlotOperationError(
                    f"Journal {path} does not own {record.staging_db}"
                )
            if record.phase == "swept":
                continue
            with closing(psycopg2.connect(**connection_kwargs("postgres"))) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(record.staging_db)
                        )
                    )
            _write_operation(path, _advanced(record, "swept"))
            report.dropped.append(record.staging_db)
        finally:
            os.close(lock_fd)
    with closing(psycopg2.connect(**connection_kwargs("postgres"))) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT datname FROM pg_database "
                "WHERE datname ~ '_staging_[0-9a-f]{12}$' ORDER BY datname"
            )
            report.unowned = [row[0] for row in cur.fetchall() if row[0] not in owned]
    return report

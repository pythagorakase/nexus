"""One registry of read-only readiness checks, scoped by machine role (#803).

A machine plays one of three roles:

- ``owner-host`` runs the runtime: configuration, PostgreSQL with its
  extensions, the stamped ``NEXUS_template``, current slot schemas, the
  PostgreSQL client tools, the built UI, and the keys the model seats read.
- ``owner-client`` talks to a runtime: configuration, the gateway's
  ``/runtime/status`` reached with the runtime's auth headers, and a matching
  version.
- ``ci-runner`` checks the repository: configuration and the static import
  reachability gate.

Every check has a stable ID and returns one :class:`CheckResult`. A check
whose dependency did not pass is skipped and names the failed check. Checks
never create, migrate, lock, or write anything: database sessions are
read-only, and secrets are reported as present, missing, or unreadable, never
printed.
``nexus doctor`` runs a role's checks; ``/runtime/status`` carries the subset
the gateway answers in-process. Liveness (``/health``), this readiness report,
and slot playability are separate answers.
"""

from __future__ import annotations

from contextlib import closing, nullcontext
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import (
    Any,
    Callable,
    Collection,
    Literal,
    Mapping,
    Optional,
    Sequence,
    get_args,
)

from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.config.loader import load_settings, settings_path_scope
from nexus.config.settings_models import RuntimeSettings, Settings
from nexus.runtime.contract import RUNTIME_STATUS_PATH
from nexus.runtime.home import (
    RuntimeHome,
    RuntimeHomeError,
    build_runtime_home,
    locate_runtime_home,
    repo_root,
)

Target = Literal["owner-host", "owner-client", "ci-runner"]
CheckStatus = Literal["pass", "fail", "skip"]
TARGETS: tuple[Target, ...] = get_args(Target)

# Bump when a field of CheckResult or ReadinessReport changes meaning or shape.
READINESS_SCHEMA_VERSION: Literal[1] = 1

# Extensions the migrations create (CREATE EXTENSION in migrations/); a test
# keeps this list in step with them.
REQUIRED_EXTENSIONS: tuple[str, ...] = ("vector", "postgis")

# The PostgreSQL maintenance database every server has.
MAINTENANCE_DATABASE = "postgres"

# Most migration versions one observation lists before summarizing the rest.
_LISTED_VERSIONS = 5


class CheckResult(BaseModel):
    """One check's verdict in the machine-readable readiness schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    targets: list[Target]
    status: CheckStatus
    observed: str
    depends_on: list[str]
    remediation: Optional[str]


class ReadinessReport(BaseModel):
    """Every selected check for one target, in registry order.

    ``omitted`` names the target's checks this report did not evaluate: the
    gateway's in-process subset omits the checks only ``nexus doctor`` runs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = READINESS_SCHEMA_VERSION
    target: Target
    ok: bool
    checks: list[CheckResult]
    omitted: list[str]


@dataclass(frozen=True)
class Outcome:
    """What a check function observed; the runner turns it into a result."""

    passed: bool
    observed: str
    remediation: Optional[str] = None


def _passed(observed: str) -> Outcome:
    return Outcome(True, observed)


def _failed(observed: str, remediation: str) -> Outcome:
    return Outcome(False, observed, remediation)


def _default_ui_dist_dir() -> Path:
    """The built client bundle the gateway serves (``nexus.api.static_ui``)."""
    from nexus.api.static_ui import UI_DIST_DIR

    return UI_DIST_DIR


@dataclass
class ReadinessContext:
    """Inputs and shared observations for one readiness run.

    ``config_path`` is an explicit configuration (``nexus doctor --config``);
    the runtime-home locator rule decides otherwise. ``config.valid`` fills
    ``settings`` and ``home``; ``gateway.reachable`` fills ``runtime_status``.
    """

    config_path: Optional[Path] = None
    ui_dist_dir: Path = field(default_factory=_default_ui_dist_dir)
    checkout: Path = field(default_factory=repo_root)
    settings: Optional[Settings] = None
    home: Optional[RuntimeHome] = None
    runtime_status: Optional[dict[str, Any]] = None

    def require_settings(self) -> Settings:
        """Return the settings config.valid validated."""
        if self.settings is None:
            raise RuntimeError("config.valid has not passed in this readiness run")
        return self.settings

    def require_home(self) -> RuntimeHome:
        """Return the runtime home config.valid resolved."""
        if self.home is None:
            raise RuntimeError("config.valid has not passed in this readiness run")
        return self.home

    def require_runtime(self) -> RuntimeSettings:
        """Return ``[runtime]``, which config.valid proved present."""
        runtime = self.require_settings().runtime
        if runtime is None:
            raise RuntimeError("config.valid passed without a [runtime] section")
        return runtime


@dataclass(frozen=True)
class CheckSpec:
    """A registered check: its stable ID, roles, dependencies, and function.

    ``gateway_evaluable`` checks are cheap, in-process, and meaningful from
    inside the gateway; ``/runtime/status`` evaluates exactly those.
    """

    id: str
    targets: tuple[Target, ...]
    depends_on: tuple[str, ...]
    run: Callable[[ReadinessContext], Outcome]
    gateway_evaluable: bool = False


def one_line(exc: BaseException) -> str:
    """Condense an exception to one line; validation errors list their fields."""
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        shown = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in errors[:3]
        )
        extra = len(errors) - 3
        return shown + (f" (+{extra} more)" if extra > 0 else "")
    return " ".join(str(exc).split()) or type(exc).__name__


def _innermost_cause(exc: BaseException) -> str:
    """Name the innermost cause of a wrapped failure, such as a refused connect.

    ``requests`` wraps a refused socket three layers deep (connection error,
    retry error, connection-pool error); the socket error is the answer.
    """
    current = exc
    seen = {id(current)}
    while True:
        candidates = (
            getattr(current, "reason", None),
            current.__cause__,
            current.args[0] if current.args else None,
        )
        inner = next(
            (
                candidate
                for candidate in candidates
                if isinstance(candidate, BaseException) and id(candidate) not in seen
            ),
            None,
        )
        if inner is None:
            return one_line(current)
        seen.add(id(inner))
        current = inner


def runtime_version() -> str:
    """The installed ``nexus`` package version, or ``unknown`` when uninstalled."""
    try:
        return version("nexus")
    except PackageNotFoundError:
        return "unknown"


def _listed(versions: Sequence[str]) -> str:
    """List migration versions compactly: the first few, then a count."""
    shown = ", ".join(versions[:_LISTED_VERSIONS])
    extra = len(versions) - _LISTED_VERSIONS
    return shown + (f" +{extra} more" if extra > 0 else "")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _check_config(ctx: ReadinessContext) -> Outcome:
    """Resolve the active nexus.toml and its runtime home, then validate it."""
    try:
        location = locate_runtime_home(ctx.config_path)
    except RuntimeHomeError as exc:
        return _failed(
            one_line(exc),
            "Point NEXUS_HOME, NEXUS_RUNTIME_CONFIG and --config at one "
            "nexus.toml, or unset the extra locator.",
        )
    path = location.config_path
    try:
        settings = load_settings(path)
        home = build_runtime_home(location, settings)
    except FileNotFoundError:
        return _failed(
            f"{path} does not exist",
            "Point --config, NEXUS_HOME or NEXUS_RUNTIME_CONFIG at an existing "
            "nexus.toml.",
        )
    except (OSError, ValueError, RuntimeHomeError) as exc:
        return _failed(
            f"{path}: {one_line(exc)}",
            f"Correct {path} where the error points; the fields are defined in "
            "nexus/config/settings_models.py.",
        )
    ctx.settings = settings
    ctx.home = home
    return _passed(f"{path} ({location.locator})")


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------


def _target_label(params: dict[str, Any]) -> str:
    """Name a connection target without its password."""
    host = params["host"] or "default socket"
    return f"{params['user']}@{host}:{params['port']}/{params['dbname']}"


def read_only_connection(dbname: str) -> Any:
    """Open a read-only session to ``dbname`` through the connection contract."""
    import psycopg2

    from nexus.database import connection_kwargs

    conn = psycopg2.connect(**connection_kwargs(dbname))
    try:
        conn.set_session(readonly=True)
    except BaseException:
        conn.close()
        raise
    return conn


@dataclass(frozen=True)
class MigrationState:
    """One database's migration stamps against this checkout's migrations.

    ``tracked`` is false when ``schema_migrations`` is missing or empty; the
    runner would bootstrap it. ``unknown`` stamps name migrations this
    checkout does not have (the database is ahead of the code).
    """

    dbname: str
    tracked: bool
    latest: Optional[str]
    pending: list[str]
    unknown: list[str]

    @property
    def current(self) -> bool:
        """Whether the database is stamped exactly through this checkout."""
        return self.tracked and not self.pending and not self.unknown

    def describe(self) -> str:
        """Summarize the state in one clause."""
        if self.current:
            return f"{self.dbname} at {self.latest}"
        parts = [] if self.tracked else ["no schema_migrations stamps"]
        if self.pending:
            parts.append(f"{len(self.pending)} pending ({_listed(self.pending)})")
        if self.unknown:
            parts.append(
                f"{len(self.unknown)} unknown to this checkout "
                f"({_listed(self.unknown)})"
            )
        return f"{self.dbname}: " + ", ".join(parts)


def database_migration_state(
    dbname: str, discovered: Sequence[tuple[str, str, Path]]
) -> MigrationState:
    """Read ``dbname``'s stamps in a read-only session and compare them.

    ``discovered`` is ``scripts.migrate.discover_migrations()``, the runner's
    own view of the migration tree.
    """
    from scripts import migrate

    with closing(read_only_connection(dbname)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'schema_migrations'"
            )
            columns = {row[0] for row in cur.fetchall()}
        applied: set[str] = (
            migrate.get_applied_migrations(conn) if "version" in columns else set()
        )
    versions = [entry[0] for entry in discovered]
    known = set(versions) | set(migrate.SCRIPT_ONLY_MIGRATIONS)
    stamped = sorted(applied & set(versions))
    return MigrationState(
        dbname=dbname,
        tracked=bool(applied),
        latest=stamped[-1] if stamped else None,
        pending=[entry for entry in versions if entry not in applied],
        unknown=sorted(applied - known),
    )


_POSTGRES_REMEDIATION = (
    "Start PostgreSQL, or set [api.database] host, port and user (or PGHOST, "
    "PGPORT, PGUSER) to a server and role that accept this connection."
)


def _check_postgres_reachable(ctx: ReadinessContext) -> Outcome:
    """Connect to the maintenance database exactly as the runtime connects."""
    import psycopg2

    from nexus.database import connection_kwargs
    from nexus.util.secret_manager import MissingSecretError, SecretStoreAccessError

    try:
        params = connection_kwargs(MAINTENANCE_DATABASE)
    except SecretStoreAccessError as exc:
        return _failed(exc.failure, exc.remediation)
    except (ValueError, RuntimeError, MissingSecretError) as exc:
        return _failed(
            one_line(exc),
            "Correct [api.database] in nexus.toml or the PG* environment.",
        )
    label = _target_label(params)
    try:
        with closing(psycopg2.connect(**params)) as conn:
            conn.set_session(readonly=True)
            with conn.cursor() as cur:
                cur.execute("SHOW server_version")
                server_version = cur.fetchone()[0]
    except psycopg2.Error as exc:
        return _failed(f"{label}: {one_line(exc)}", _POSTGRES_REMEDIATION)
    return _passed(f"{label}: PostgreSQL {server_version}")


def _check_postgres_extensions(ctx: ReadinessContext) -> Outcome:
    """The server offers every extension the migrations create."""
    import psycopg2

    try:
        with closing(read_only_connection(MAINTENANCE_DATABASE)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, default_version FROM pg_available_extensions "
                    "WHERE name = ANY(%s)",
                    (list(REQUIRED_EXTENSIONS),),
                )
                available = dict(cur.fetchall())
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    found = [
        f"{name} {available[name]}" for name in REQUIRED_EXTENSIONS if name in available
    ]
    missing = [name for name in REQUIRED_EXTENSIONS if name not in available]
    if missing:
        return _failed(
            "; ".join(found + [f"missing {', '.join(missing)}"]),
            "Install the missing extension packages for this PostgreSQL server "
            "(pgvector provides vector, PostGIS provides postgis).",
        )
    return _passed(", ".join(found))


def _check_template_present(ctx: ReadinessContext) -> Outcome:
    """The canonical fresh-slot image exists on the server."""
    import psycopg2

    from scripts.migrate import TEMPLATE_DB

    try:
        with closing(read_only_connection(MAINTENANCE_DATABASE)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (TEMPLATE_DB,)
                )
                present = cur.fetchone() is not None
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    if not present:
        return _failed(
            f"{TEMPLATE_DB} does not exist",
            f"Restore {TEMPLATE_DB} from a known-good slot (CLAUDE.md, Refreshing "
            "the Template); new slots are cloned from it.",
        )
    return _passed(f"{TEMPLATE_DB} exists")


_STALE_CHECKOUT = (
    "update this checkout (git pull): the database has migrations it lacks"
)


def _discovered_migrations() -> tuple[list[tuple[str, str, Path]], Optional[Outcome]]:
    """Return the migration tree, or the failure a malformed tree produces."""
    from scripts import migrate

    try:
        return migrate.discover_migrations(), None
    except RuntimeError as exc:
        return [], _failed(one_line(exc), "Fix the migrations/ entry the error names.")


def _check_template_migrations(ctx: ReadinessContext) -> Outcome:
    """NEXUS_template is stamped through exactly this checkout's migrations."""
    import psycopg2

    from scripts.migrate import TEMPLATE_DB

    discovered, malformed = _discovered_migrations()
    if malformed is not None:
        return malformed
    try:
        state = database_migration_state(TEMPLATE_DB, discovered)
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    if state.current:
        return _passed(state.describe())
    steps = []
    if state.pending or not state.tracked:
        steps.append("python scripts/migrate.py --template")
    if state.unknown:
        steps.append(_STALE_CHECKOUT)
    return _failed(state.describe(), "; ".join(steps))


def _check_slot_migrations(ctx: ReadinessContext) -> Outcome:
    """Each probed slot that exists is stamped through this checkout."""
    import psycopg2

    from nexus.api.save_slots import is_slot_locked
    from nexus.api.slot_utils import slot_dbname

    slots = ctx.require_runtime().readiness.slots
    names = {slot: slot_dbname(slot) for slot in slots}
    discovered, malformed = _discovered_migrations()
    if malformed is not None:
        return malformed
    observations: list[str] = []
    steps: list[str] = []
    try:
        with closing(read_only_connection(MAINTENANCE_DATABASE)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                    (list(names.values()),),
                )
                existing = {row[0] for row in cur.fetchall()}
        for slot, dbname in names.items():
            if dbname not in existing:
                observations.append(f"{dbname} absent")
                continue
            state = database_migration_state(dbname, discovered)
            observations.append(state.describe())
            if state.pending or not state.tracked:
                command = f"python scripts/migrate.py --slot {slot}"
                if is_slot_locked(slot):
                    command += " --write-locked-slot"
                steps.append(command)
            if state.unknown and _STALE_CHECKOUT not in steps:
                steps.append(_STALE_CHECKOUT)
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    observed = "; ".join(observations)
    if steps:
        return _failed(observed, "; ".join(steps))
    return _passed(observed)


# The migration that creates memory_idf_corpora and seeds both corpus rows.
IDF_MIGRATION = "114"


def _idf_corpora() -> tuple[str, ...]:
    """The corpus rows a database past migration 114 holds, in lock order."""
    from nexus.agents.memnon.utils.idf_dictionary import IDFDictionary

    return tuple(sorted(IDFDictionary.CORPUS_KINDS))


def _named_corpora(label: str, kinds: Sequence[str]) -> str:
    """Name corpus kinds under a label: ``missing corpus narrative``."""
    noun = "corpus" if len(kinds) == 1 else "corpora"
    return f"{label} {noun} {' and '.join(kinds)}"


@dataclass(frozen=True)
class AnalyzerState:
    """One database's IDF corpus rows against the live server's analyzer key.

    ``tracked`` is false when ``memory_idf_corpora`` does not exist;
    ``migration_pending`` then says whether migration 114, which creates it
    and seeds both corpus rows, is still unapplied. ``corpora`` maps each
    corpus row to its stored key. Only exactly the ``narrative`` and
    ``retrograde_summary`` rows, each at the server's key, are current.
    """

    dbname: str
    server_key: str
    tracked: bool
    corpora: dict[str, str]
    migration_pending: bool = False

    @property
    def missing(self) -> list[str]:
        """The expected corpora that have no row."""
        return [kind for kind in _idf_corpora() if kind not in self.corpora]

    @property
    def unexpected(self) -> list[str]:
        """The corpus rows no trigger or reader serves."""
        expected = _idf_corpora()
        return sorted(kind for kind in self.corpora if kind not in expected)

    @property
    def stale(self) -> dict[str, str]:
        """The expected corpora whose key differs from the server's."""
        expected = _idf_corpora()
        return {
            kind: key
            for kind, key in self.corpora.items()
            if kind in expected and key != self.server_key
        }

    @property
    def current(self) -> bool:
        """Whether exactly the expected corpus rows exist, each at the server's key."""
        return (
            self.tracked and not self.missing and not self.unexpected and not self.stale
        )

    @property
    def damaged(self) -> bool:
        """Whether ``memory_idf_corpora`` is gone although migration 114 is stamped.

        Only hand damage produces this; neither the rebuild nor the migration
        runner can recreate the table.
        """
        return not self.tracked and not self.migration_pending

    def describe(self) -> str:
        """Summarize the state in one clause."""
        if self.current:
            return f"{self.dbname} at {self.server_key}"
        if not self.tracked:
            if self.migration_pending:
                return (
                    f"{self.dbname}: no memory_idf_corpora table "
                    f"(migration {IDF_MIGRATION} pending)"
                )
            missing = _named_corpora("missing", self.missing)
            return (
                f"{self.dbname}: no memory_idf_corpora table though migration "
                f"{IDF_MIGRATION} is applied ({missing})"
            )
        parts = []
        if self.missing:
            parts.append(_named_corpora("missing", self.missing))
        if self.unexpected:
            parts.append(_named_corpora("unexpected", self.unexpected))
        if self.stale:
            listed = ", ".join(f"{kind} {key}" for kind, key in self.stale.items())
            parts.append(f"{listed} (server {self.server_key})")
        return f"{self.dbname}: " + ", ".join(parts)


def _migration_stamped(cur: Any, version: str) -> bool:
    """Whether ``schema_migrations`` records ``version``; false without the table."""
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = 'schema_migrations' AND column_name = 'version'"
    )
    if cur.fetchone() is None:
        return False
    cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
    return cur.fetchone() is not None


def database_analyzer_state(dbname: str) -> AnalyzerState:
    """Read ``dbname``'s IDF corpus rows and the server's key, read-only.

    When ``memory_idf_corpora`` is absent it also reads whether migration 114
    is stamped: pending, the migration runner installs the table; stamped,
    only hand damage removed it.
    """
    from nexus.agents.memnon.utils.idf_dictionary import ANALYZER_KEY_SQL

    with closing(read_only_connection(dbname)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {ANALYZER_KEY_SQL}, "
                "to_regclass('public.memory_idf_corpora') IS NOT NULL"
            )
            server_key, tracked = cur.fetchone()
            corpora: dict[str, str] = {}
            migration_pending = False
            if tracked:
                cur.execute(
                    "SELECT corpus_kind, analyzer_version FROM memory_idf_corpora "
                    "ORDER BY corpus_kind"
                )
                corpora = dict(cur.fetchall())
            else:
                migration_pending = not _migration_stamped(cur, IDF_MIGRATION)
    return AnalyzerState(dbname, server_key, bool(tracked), corpora, migration_pending)


def _damaged_idf_remediation(dbname: str) -> str:
    """Say what a stamped database without ``memory_idf_corpora`` needs."""
    return (
        f"memory_idf_corpora is absent from {dbname} although migration "
        f"{IDF_MIGRATION} is stamped, which only hand damage produces: restore "
        f"{dbname} from a backup or recreate it"
    )


def idf_analyzer_outcome(
    targets: Sequence[tuple[str, str, str]], *, absent: Sequence[str] = ()
) -> Outcome:
    """Compare each target's IDF corpus rows with the server's key and name the fix.

    Each target is ``(dbname, rebuild_command, migrate_command)``: the command
    that rebuilds the corpora (seeding a missing row) and the one that applies
    migration 114 where it is pending. A database stamped with 114 but without
    ``memory_idf_corpora`` must be restored or recreated; no command repairs
    it. Only exactly the two corpus rows, each at the server's key, pass.
    ``absent`` databases are reported, not failed.
    """
    import psycopg2

    observations: list[str] = []
    steps: list[str] = []
    try:
        for dbname, rebuild_command, migrate_command in targets:
            state = database_analyzer_state(dbname)
            observations.append(state.describe())
            if state.migration_pending:
                steps.append(migrate_command)
            elif state.damaged:
                steps.append(_damaged_idf_remediation(dbname))
            elif not state.current:
                steps.append(rebuild_command)
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    observations.extend(f"{dbname} absent" for dbname in absent)
    observed = "; ".join(observations)
    if steps:
        return _failed(observed, "; ".join(steps))
    return _passed(observed)


def _check_template_idf_analyzer(ctx: ReadinessContext) -> Outcome:
    """NEXUS_template's IDF corpus keys match the live server's analyzer."""
    from nexus.agents.memnon.utils.idf_dictionary import REBUILD_COMMAND
    from scripts.migrate import TEMPLATE_DB

    return idf_analyzer_outcome(
        [
            (
                TEMPLATE_DB,
                f"{REBUILD_COMMAND} --template",
                "python scripts/migrate.py --template",
            )
        ]
    )


def slot_idf_targets(
    names: Mapping[int, str], existing: Collection[str], locked: Collection[int]
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Build the slot IDF check's targets and absent databases.

    ``names`` maps each probed slot to its database, ``existing`` holds the
    databases the server has, and ``locked`` the slots whose database is
    locked. Each target is ``(dbname, rebuild_command, migrate_command)`` as
    :func:`idf_analyzer_outcome` takes it; a locked slot's commands carry
    ``--write-locked-slot``.
    """
    from nexus.agents.memnon.utils.idf_dictionary import REBUILD_COMMAND

    targets: list[tuple[str, str, str]] = []
    absent: list[str] = []
    for slot, dbname in names.items():
        if dbname not in existing:
            absent.append(dbname)
            continue
        override = " --write-locked-slot" if slot in locked else ""
        targets.append(
            (
                dbname,
                f"{REBUILD_COMMAND} --slot {slot}{override}",
                f"python scripts/migrate.py --slot {slot}{override}",
            )
        )
    return targets, absent


def slot_idf_outcome(names: Mapping[int, str]) -> Outcome:
    """Check each named slot database's IDF corpus keys against the server.

    ``names`` maps each slot number to its database. A database the server
    lacks is reported as absent; a locked one's remediation carries
    ``--write-locked-slot``.
    """
    import psycopg2

    from nexus.api.save_slots import is_slot_locked

    try:
        with closing(read_only_connection(MAINTENANCE_DATABASE)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                    (list(names.values()),),
                )
                existing = {row[0] for row in cur.fetchall()}
        locked = {
            slot
            for slot, dbname in names.items()
            if dbname in existing and is_slot_locked(slot, dbname)
        }
    except psycopg2.Error as exc:
        return _failed(one_line(exc), _POSTGRES_REMEDIATION)
    targets, absent = slot_idf_targets(names, existing, locked)
    return idf_analyzer_outcome(targets, absent=absent)


def _check_slot_idf_analyzer(ctx: ReadinessContext) -> Outcome:
    """Each probed slot that exists has IDF corpus keys matching the server."""
    from nexus.api.slot_utils import slot_dbname

    slots = ctx.require_runtime().readiness.slots
    return slot_idf_outcome({slot: slot_dbname(slot) for slot in slots})


# ---------------------------------------------------------------------------
# Host files and tools
# ---------------------------------------------------------------------------


def find_postgres_tool(
    name: str, search_paths: Sequence[str]
) -> tuple[Optional[str], str]:
    """Locate a PostgreSQL client tool as slot initialization does.

    The runtime ``PATH`` wins; ``[api.database].tool_search_paths`` supplements
    it for launches that do not inherit an interactive shell's ``PATH``
    (``scripts/new_story_setup.py``). Returns the executable, or ``None``,
    and where it was looked for.
    """
    found = shutil.which(name)
    if found:
        return found, "PATH"
    extra = os.pathsep.join(str(Path(path).expanduser()) for path in search_paths)
    if extra:
        found = shutil.which(name, path=extra)
        if found:
            return found, "[api.database].tool_search_paths"
    return None, f"PATH and [api.database].tool_search_paths {list(search_paths)}"


def _check_pg_dump(ctx: ReadinessContext) -> Outcome:
    """pg_dump, which clones slots from the template, resolves for this process."""
    settings = ctx.require_settings()
    if settings.api is None:
        return _failed(
            "nexus.toml has no [api.database]",
            "Restore the [api.database] section in nexus.toml.",
        )
    executable, where = find_postgres_tool(
        "pg_dump", settings.api.database.tool_search_paths
    )
    if executable is None:
        return _failed(
            f"pg_dump not found on {where}",
            "Install the PostgreSQL client tools, or add their directory to "
            "[api.database].tool_search_paths in nexus.toml.",
        )
    return _passed(f"{executable} (via {where})")


def _check_ui_bundle(ctx: ReadinessContext) -> Outcome:
    """The built client bundle the gateway serves exists."""
    index = ctx.ui_dist_dir / "index.html"
    if not index.is_file():
        return _failed(f"{index} missing", "Build it: npm --prefix ui run build")
    return _passed(str(ctx.ui_dist_dir))


def _check_seat_secrets(ctx: ReadinessContext) -> Outcome:
    """Every key the model seats in use read is present (never printed).

    An account whose store cannot be read is ``unreadable``, never
    ``missing``; any unreadable account fails the check with the first one's
    remediation, since storing a key cannot help while the store is shut.
    """
    from nexus.api.secrets_endpoints import (
        SeatRequirementError,
        required_secret_accounts,
    )
    from nexus.util.secret_manager import (
        MissingSecretError,
        SecretStoreAccessError,
        get_secret,
    )

    try:
        required = required_secret_accounts(ctx.require_settings())
    except SeatRequirementError as exc:
        return _failed(
            one_line(exc),
            "Point the named seat at a model in [global.model.api_models].",
        )
    if not required:
        return _passed("no seat in use reads a stored key")
    env_only = os.environ.get("NEXUS_KEYRING_DISABLE") == "1"
    present: list[str] = []
    missing: list[str] = []
    unreadable: list[str] = []
    access_errors: list[SecretStoreAccessError] = []
    for account in sorted(required):
        try:
            get_secret(account)
        except MissingSecretError:
            missing.append(account)
        except SecretStoreAccessError as exc:
            unreadable.append(account)
            access_errors.append(exc)
        else:
            present.append(account)

    def listed(accounts: list[str]) -> str:
        return "; ".join(
            f"{account} ({', '.join(seat.seat for seat in required[account])})"
            for account in accounts
        )

    parts = [f"present: {listed(present)}"] if present else []
    if missing:
        parts.append(f"missing: {listed(missing)}")
    if unreadable:
        parts.append(f"unreadable: {listed(unreadable)}")
    source = (
        "environment only, NEXUS_KEYRING_DISABLE=1"
        if env_only
        else "platform secret store"
    )
    observed = f"{' | '.join(parts)} [{source}]"
    if access_errors:
        return _failed(observed, access_errors[0].remediation)
    if not missing:
        return _passed(observed)
    if env_only:
        variables = ", ".join(f"{account.upper()}_API_KEY" for account in missing)
        return _failed(
            observed,
            f"Export {variables}, or unset NEXUS_KEYRING_DISABLE to read the "
            "platform store.",
        )
    return _failed(
        observed,
        "Store the missing keys in the settings pane's API KEYS card "
        "(docs/runtime.md, Required Keys and Headless Hosts).",
    )


# ---------------------------------------------------------------------------
# Owner client
# ---------------------------------------------------------------------------


def _check_gateway_reachable(ctx: ReadinessContext) -> Outcome:
    """GET /runtime/status from the gateway this profile names, with its auth."""
    import requests  # type: ignore[import-untyped]

    from nexus.runtime.remote_auth import build_runtime_request_auth
    from nexus.runtime.supervisor import RuntimeError_, Supervisor
    from nexus.util.secret_manager import MissingSecretError, SecretStoreAccessError

    settings = ctx.require_settings()
    runtime = ctx.require_runtime()
    try:
        # A copy: the supervisor applies NEXUS_GATEWAY_PORT to its settings.
        supervisor = Supervisor(
            settings.model_copy(deep=True), ctx.require_home().config_path
        )
    except RuntimeError_ as exc:
        return _failed(one_line(exc), "Correct [runtime] in nexus.toml.")
    url = supervisor.gateway_url() + RUNTIME_STATUS_PATH
    remote = runtime.remote if runtime.profile == "remote" else None
    start = {
        "local": "Start the runtime: nexus up",
        "external": "Start the gateway [runtime.external].gateway_url names.",
        "remote": "Check [runtime.remote].base_url and run nexus status on the host.",
    }[runtime.profile]
    try:
        auth = build_runtime_request_auth(url, remote)
    except SecretStoreAccessError as exc:
        return _failed(exc.failure, exc.remediation)
    except MissingSecretError as exc:
        return _failed(
            one_line(exc),
            "Store the Cloudflare Access service token accounts that "
            "[runtime.remote.cloudflare_access] names.",
        )
    except ValueError as exc:
        return _failed(
            f"{url}: {one_line(exc)}",
            "Reach the runtime over HTTPS or loopback while NEXUS_AUTH is set.",
        )
    try:
        response = requests.get(
            url,
            timeout=runtime.readiness.gateway_timeout_seconds,
            headers=auth.headers,
            allow_redirects=auth.allow_redirects,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return _failed(f"{url}: {_innermost_cause(exc)}", start)
    if not isinstance(payload, dict):
        return _failed(f"{url} answered {type(payload).__name__}, not an object", start)
    ctx.runtime_status = payload
    state = "ok" if payload.get("ok") is True else "not ok"
    return _passed(
        f"{url} answered (profile {payload.get('profile')}, runtime {state})"
    )


def _check_gateway_version(ctx: ReadinessContext) -> Outcome:
    """This client and the runtime run the same NEXUS version."""
    if ctx.runtime_status is None:
        raise RuntimeError("gateway.reachable has not passed in this readiness run")
    client = runtime_version()
    runtime = ctx.runtime_status.get("version")
    observed = f"client {client}, runtime {runtime}"
    if client == "unknown" or runtime in (None, "unknown"):
        return _failed(
            observed,
            "Install the nexus package on both machines (poetry install) so each "
            "reports its version.",
        )
    if client != runtime:
        return _failed(
            observed,
            "Update the older side (git pull, poetry install), then restart the "
            "runtime with nexus restart.",
        )
    return _passed(f"client and runtime {client}")


# ---------------------------------------------------------------------------
# CI runner
# ---------------------------------------------------------------------------


def _check_reachability_gate(ctx: ReadinessContext) -> Outcome:
    """The static import-reachability gate passes on this checkout."""
    script = ctx.checkout / "scripts" / "check_reachability.py"
    command = "python -S scripts/check_reachability.py"
    if not script.is_file():
        return _failed(
            f"{script} missing",
            "Run the ci-runner checks from a NEXUS checkout.",
        )
    limit = ctx.require_runtime().readiness.reachability_timeout_seconds
    try:
        completed = subprocess.run(
            [sys.executable, "-S", str(script)],
            cwd=ctx.checkout,
            capture_output=True,
            text=True,
            timeout=limit,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(
            f"{command} exceeded {limit:g}s",
            "Raise [runtime.readiness].reachability_timeout_seconds for this runner.",
        )
    try:
        summary = json.loads(completed.stdout)
    except json.JSONDecodeError:
        lines = completed.stderr.strip().splitlines()
        return _failed(
            f"exit {completed.returncode}: {lines[-1] if lines else 'no output'}",
            f"Run {command} and fix the error it prints.",
        )
    findings = {
        key: len(value)
        for key, value in summary.items()
        if isinstance(value, list) and value
    }
    if completed.returncode != 0 or findings:
        listed = ", ".join(f"{key} ({count})" for key, count in findings.items())
        return _failed(
            f"exit {completed.returncode}: {listed or 'no findings listed'}",
            f"Run {command}; record an intended change with --write-baseline "
            "--reason.",
        )
    production = summary["reachable_by_kind"]["production"]
    return _passed(f"{production} production modules reachable, no findings")


# ---------------------------------------------------------------------------
# Registry and runner
# ---------------------------------------------------------------------------

_HOST: tuple[Target, ...] = ("owner-host",)

REGISTRY: tuple[CheckSpec, ...] = (
    CheckSpec("config.valid", TARGETS, (), _check_config, gateway_evaluable=True),
    CheckSpec(
        "postgres.reachable", _HOST, ("config.valid",), _check_postgres_reachable
    ),
    CheckSpec(
        "postgres.extensions",
        _HOST,
        ("postgres.reachable",),
        _check_postgres_extensions,
    ),
    CheckSpec(
        "template.present", _HOST, ("postgres.reachable",), _check_template_present
    ),
    CheckSpec(
        "template.migrations_current",
        _HOST,
        ("template.present",),
        _check_template_migrations,
    ),
    CheckSpec(
        "slots.migrations_current",
        _HOST,
        ("template.present",),
        _check_slot_migrations,
    ),
    CheckSpec(
        "template.idf_analyzer_current",
        _HOST,
        ("template.present",),
        _check_template_idf_analyzer,
    ),
    CheckSpec(
        "slots.idf_analyzer_current",
        _HOST,
        ("template.present",),
        _check_slot_idf_analyzer,
    ),
    CheckSpec(
        "tools.pg_dump",
        _HOST,
        ("config.valid",),
        _check_pg_dump,
        gateway_evaluable=True,
    ),
    CheckSpec("ui.bundle", _HOST, (), _check_ui_bundle, gateway_evaluable=True),
    CheckSpec("secrets.seat_providers", _HOST, ("config.valid",), _check_seat_secrets),
    CheckSpec(
        "gateway.reachable",
        ("owner-client",),
        ("config.valid",),
        _check_gateway_reachable,
    ),
    CheckSpec(
        "gateway.version",
        ("owner-client",),
        ("gateway.reachable",),
        _check_gateway_version,
    ),
    CheckSpec(
        "reachability.gate",
        ("ci-runner",),
        ("config.valid",),
        _check_reachability_gate,
    ),
)


def validate_registry(registry: Sequence[CheckSpec]) -> None:
    """Reject a registry whose order or scope cannot be evaluated as written.

    IDs are unique; every dependency is registered earlier, serves every
    target of its dependent (so it always runs first in the same report),
    and is gateway-evaluable whenever its dependent is.
    """
    seen: dict[str, CheckSpec] = {}
    for spec in registry:
        if spec.id in seen:
            raise ValueError(f"Duplicate readiness check ID {spec.id!r}")
        if not spec.targets or set(spec.targets) - set(TARGETS):
            raise ValueError(f"{spec.id} has invalid targets {spec.targets!r}")
        for dependency in spec.depends_on:
            parent = seen.get(dependency)
            if parent is None:
                raise ValueError(
                    f"{spec.id} depends on {dependency!r}, which is not "
                    "registered before it"
                )
            if set(spec.targets) - set(parent.targets):
                raise ValueError(
                    f"{spec.id} serves a target its dependency {dependency} "
                    "does not serve"
                )
            if spec.gateway_evaluable and not parent.gateway_evaluable:
                raise ValueError(
                    f"{spec.id} is gateway-evaluable but {dependency} is not"
                )
        seen[spec.id] = spec


validate_registry(REGISTRY)


def run_readiness(
    target: Target,
    context: Optional[ReadinessContext] = None,
    *,
    gateway_only: bool = False,
    registry: Sequence[CheckSpec] = REGISTRY,
) -> ReadinessReport:
    """Evaluate ``target``'s checks in registry order and report every one.

    A check runs only when each dependency passed; otherwise it is skipped
    and names the check that failed at the root of the chain. Once
    ``config.valid`` has resolved the active configuration, later checks run
    inside its settings scope, so nested readers (the connection contract,
    seat resolution) load that same file.
    """
    if target not in TARGETS:
        raise ValueError(f"Unknown readiness target {target!r}; choose from {TARGETS}")
    validate_registry(registry)
    ctx = context if context is not None else ReadinessContext()
    selected = [spec for spec in registry if target in spec.targets]
    omitted = [
        spec.id for spec in selected if gateway_only and not spec.gateway_evaluable
    ]
    results: list[CheckResult] = []
    status: dict[str, CheckStatus] = {}
    root_failure: dict[str, str] = {}
    for spec in selected:
        if spec.id in omitted:
            continue
        blocked = next(
            (
                dependency
                for dependency in spec.depends_on
                if status[dependency] != "pass"
            ),
            None,
        )
        if blocked is not None:
            cause = root_failure.get(blocked, blocked)
            root_failure[spec.id] = cause
            outcome_status: CheckStatus = "skip"
            observed = f"{cause} failed"
            remediation: Optional[str] = f"Resolve {cause} first."
        else:
            scope = (
                settings_path_scope(ctx.home.config_path)
                if ctx.home is not None
                else nullcontext()
            )
            with scope:
                outcome = spec.run(ctx)
            outcome_status = "pass" if outcome.passed else "fail"
            observed = outcome.observed
            remediation = outcome.remediation
        status[spec.id] = outcome_status
        results.append(
            CheckResult(
                id=spec.id,
                targets=list(spec.targets),
                status=outcome_status,
                observed=observed,
                depends_on=list(spec.depends_on),
                remediation=remediation,
            )
        )
    return ReadinessReport(
        target=target,
        ok=all(result.status != "fail" for result in results),
        checks=results,
        omitted=omitted,
    )


def gateway_readiness() -> ReadinessReport:
    """The owner-host checks the gateway answers in-process, for /runtime/status."""
    return run_readiness("owner-host", gateway_only=True)


def render_report(report: ReadinessReport) -> list[str]:
    """One line per check: status, ID, observation, and a failure's remediation."""
    width = max((len(result.id) for result in report.checks), default=0)
    lines = []
    for result in report.checks:
        line = f"{result.status:<4}  {result.id:<{width}}  {result.observed}"
        if result.status == "fail" and result.remediation:
            line += f"  -> {result.remediation}"
        lines.append(line)
    return lines

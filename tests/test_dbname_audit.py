"""The owner-connection audit refuses owner targets and fails their sessions.

Each case runs a nested pytest session over a generated test file under
``tmp_path`` (outside ``tests/``, so the suite never collects it). The child
environment is an allowlist: no libpq variable (``PGHOSTADDR``, ``PGSERVICE``,
and the rest) reaches it unless a case sets one. The clean session connects to
a disposable database through every hooked driver path. The owner session
names ``save_01`` through ``save_05`` and ``NEXUS_template`` in every spelling
the plugin parses, with ``PGHOST`` a missing Unix-socket directory and hosts
under RFC 2606 ``.invalid``; the audit refuses each call before libpq or
asyncpg is entered, so no owner connection is ever attempted.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from tests import dbname_audit
from tests.pg_fixtures import connect, disposable_database

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DATABASE_ENV = "NEXUS_DBNAME_AUDIT_TEST_DATABASE"
MISSING_SOCKET_DIR = "/nonexistent/nexus-dbname-audit"

# Everything a nested session inherits; libpq variables are never on the list.
CHILD_ENVIRONMENT_ALLOWLIST = (
    "PATH",
    "HOME",
    "PYTHONPATH",
    "LANG",
    # The secret-store guard's env-only mode and the test-provider tripwire.
    "NEXUS_KEYRING_DISABLE",
    "NEXUS_TEST_PROVIDER_ONLY",
)

CLEAN_SESSION = """
import asyncio
import os

import asyncpg
import psycopg2
import psycopg2.extensions

from nexus.database import connection_kwargs
from tests import dbname_audit
from tests.pg_fixtures import asyncpg_kwargs, connect

DBNAME = os.environ["NEXUS_DBNAME_AUDIT_TEST_DATABASE"]


def test_every_driver_path_is_recorded():
    conn = connect(DBNAME)
    conn.close()
    assert "psycopg2" in dbname_audit.recorded()[DBNAME]

    dsn = psycopg2.extensions.make_dsn(**connection_kwargs(DBNAME))
    direct = psycopg2.extensions.connection(dsn)
    assert isinstance(direct, psycopg2.extensions.connection)
    direct.close()
    assert "psycopg2.extensions.connection" in dbname_audit.recorded()[DBNAME]

    async def open_and_close():
        conn = await asyncpg.connect(**asyncpg_kwargs(DBNAME))
        await conn.close()

    asyncio.run(open_and_close())
    assert "asyncpg" in dbname_audit.recorded()[DBNAME]
    assert dbname_audit.owner_targets() == {}
"""

# Loaded with ``-p`` ahead of the audit, so the audit wraps these recorders:
# any call that reaches libpq's connect or asyncpg's socket is listed.
LIBPQ_SPY = """
import psycopg2
from asyncpg import connect_utils
from psycopg2 import _psycopg

ENTRIES = []
_libpq_connect = psycopg2._connect
_connect_addr = connect_utils._connect_addr


def spied_connect(dsn, *args, **kwargs):
    ENTRIES.append(("libpq", dsn))
    return _libpq_connect(dsn, *args, **kwargs)


async def spied_connect_addr(*args, **kwargs):
    ENTRIES.append(("asyncpg socket", kwargs.get("addr")))
    return await _connect_addr(*args, **kwargs)


psycopg2._connect = spied_connect
_psycopg._connect = spied_connect
connect_utils._connect_addr = spied_connect_addr
"""

OWNER_SESSION = f"""
import asyncio
import os

import asyncpg
import psycopg2
import psycopg2.extensions
import pytest

import libpq_spy
from tests import dbname_audit

MISSING = "{MISSING_SOCKET_DIR}"
Refused = dbname_audit.OwnerDatabaseConnectionRefused
NODE = "test_nested_session.py::test_owner_targets_in_every_spelling"


def test_owner_targets_in_every_spelling(monkeypatch):
    # The parent's allowlist let through no libpq variable but this one.
    assert sorted(k for k in os.environ if k.startswith("PG")) == ["PGHOST"]
    assert os.environ["PGHOST"] == MISSING

    with pytest.raises(Refused, match="'save_01' from " + NODE):
        psycopg2.connect("dbname=save_01 connect_timeout=1")
    with pytest.raises(Refused, match="'save_02'"):
        psycopg2.connect("postgresql://audit.invalid/save_02?connect_timeout=1")
    with pytest.raises(Refused, match="'save_03'"):
        psycopg2.connect(dbname="save_03", connect_timeout=1)
    with pytest.raises(Refused, match="'save_04'"):
        psycopg2.extensions.connection("dbname=save_04")
    with pytest.raises(Refused, match="'NEXUS_template'"):
        asyncio.run(asyncpg.connect(database="NEXUS_template", host=MISSING))
    with pytest.raises(Refused, match="'save_05'"):
        asyncio.run(
            asyncpg.connect(dsn="postgresql://audit.invalid/save_05", timeout=5)
        )
    monkeypatch.setenv("PGDATABASE", "save_01")
    with pytest.raises(Refused, match="'save_01'"):
        psycopg2.connect("connect_timeout=1")

    # Every refusal came before libpq or asyncpg opened anything.
    assert libpq_spy.ENTRIES == []
"""
OWNER_TARGETS = (
    "NEXUS_template",
    "save_01",
    "save_02",
    "save_03",
    "save_04",
    "save_05",
)

# Imported with ``-p`` before the audit configures: a cached constructor and a
# preloaded subclass, the two paths a module-attribute swap alone missed.
EARLY_CONSTRUCTORS = """
import psycopg2.extensions
import psycopg2.extras
from psycopg2.extensions import connection as cached_connection
from psycopg2.extras import LoggingConnection
"""

PRELOADED_SESSION = f"""
import io
import os

import psycopg2.extensions
import pytest

import early_constructors as early
from nexus.database import connection_kwargs
from tests import dbname_audit

DBNAME = os.environ["NEXUS_DBNAME_AUDIT_TEST_DATABASE"]
MISSING = "{MISSING_SOCKET_DIR}"
Refused = dbname_audit.OwnerDatabaseConnectionRefused
LOGGING = "psycopg2.extensions.connection (psycopg2.extras.LoggingConnection)"


def test_preloaded_constructors_are_recorded_and_refused():
    dsn = psycopg2.extensions.make_dsn(**connection_kwargs(DBNAME))

    cached = early.cached_connection(dsn)
    cached.close()
    assert "psycopg2.extensions.connection" in dbname_audit.recorded()[DBNAME]

    logged = early.LoggingConnection(dsn)
    logged.initialize(io.StringIO())
    logged.cursor().execute("SELECT 1")
    logged.close()
    assert LOGGING in dbname_audit.recorded()[DBNAME]

    for name in (
        "LoggingConnection",
        "DictConnection",
        "RealDictConnection",
        "NamedTupleConnection",
    ):
        assert "psycopg2.extras." + name not in dbname_audit.unaudited()

    with pytest.raises(Refused, match="'save_01'"):
        early.cached_connection(f"dbname=save_01 host={{MISSING}}")
    with pytest.raises(Refused, match="'save_02'"):
        early.LoggingConnection(f"dbname=save_02 host={{MISSING}}")
"""


def _child_environment(
    inherited: Mapping[str, str], environment: Mapping[str, str], tmp_path: Path
) -> dict[str, str]:
    """Build a nested session's environment from the allowlist alone."""

    env = {
        name: inherited[name]
        for name in CHILD_ENVIRONMENT_ALLOWLIST
        if name in inherited
    }
    env.update(environment)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(tmp_path), str(REPO_ROOT), env.get("PYTHONPATH")])
    )
    return env


@pytest.fixture(scope="module")
def audit_database() -> Iterator[str]:
    """One empty disposable database for the clean nested session."""

    with disposable_database("qa640_dbname_audit") as dbname:
        yield dbname


def _nested_session(
    tmp_path: Path,
    source: str,
    *,
    activation: list[str],
    environment: dict[str, str],
    modules: Mapping[str, str] | None = None,
    inherited: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``source`` as its own pytest session with the audit loaded.

    ``modules`` are written beside the test file and importable with ``-p``;
    ``inherited`` stands in for this process's environment.
    """

    for name, text in (modules or {}).items():
        (tmp_path / f"{name}.py").write_text(text)
    test_file = tmp_path / "test_nested_session.py"
    test_file.write_text(source)
    env = _child_environment(
        os.environ if inherited is None else inherited, environment, tmp_path
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *activation,
            "--rootdir",
            str(tmp_path),
            str(test_file),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _owner_failure_line(output: str) -> str:
    """Return the single session-end line that names the owner targets."""

    failure_lines = [
        line
        for line in output.splitlines()
        if line.startswith("dbname audit: FAILED: owner targets: ")
    ]
    assert len(failure_lines) == 1, output
    return failure_lines[0]


def _owner_session(
    tmp_path: Path,
    activation: list[str],
    environment: dict[str, str],
    inherited: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the owner session with the libpq spy loaded ahead of the audit."""

    return _nested_session(
        tmp_path,
        OWNER_SESSION,
        activation=["-p", "libpq_spy", *activation],
        environment={"PGHOST": MISSING_SOCKET_DIR, **environment},
        modules={"libpq_spy": LIBPQ_SPY},
        inherited=inherited,
    )


def _assert_owner_session_failed(result: subprocess.CompletedProcess[str]) -> None:
    """The refusals all passed, and the session still failed naming each one."""

    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "1 passed" in output, output
    failure_line = _owner_failure_line(output)
    for target in OWNER_TARGETS:
        assert f"{target} (" in failure_line, output
    assert "test_nested_session.py::test_owner_targets_in_every_spelling" in (
        failure_line
    )


@pytest.mark.requires_postgres
def test_session_on_a_disposable_database_passes(
    audit_database: str, tmp_path: Path
) -> None:
    """Every hooked driver records the clone; no owner target, exit 0."""

    result = _nested_session(
        tmp_path,
        CLEAN_SESSION,
        activation=["-p", "tests.dbname_audit"],
        environment={AUDIT_DATABASE_ENV: audit_database},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "1 passed" in output, output
    assert "dbname audit: owner targets: none" in output, output
    assert "qa640_dbname_audit_*" in output, output


# The owner session dials no server, so it runs in the offline gate too. The
# repository conftest's offline tripwire would replace psycopg2.connect before
# the audit saw the call, so the nested session opts in to PostgreSQL.
@pytest.mark.parametrize(
    ("activation", "environment"),
    [
        (["-p", "tests.dbname_audit"], {"NEXUS_RUN_POSTGRES": "1"}),
        (
            ["-p", "tests.conftest"],
            {dbname_audit.ENVIRONMENT_FLAG: "1", "NEXUS_RUN_POSTGRES": "1"},
        ),
    ],
    ids=["plugin-flag", "environment-flag"],
)
def test_session_naming_an_owner_is_refused_and_fails(
    tmp_path: Path, activation: list[str], environment: dict[str, str]
) -> None:
    """Each owner call raises before connecting; the session still fails."""

    _assert_owner_session_failed(_owner_session(tmp_path, activation, environment))


def _owner_sessions_started() -> dict[str, int]:
    """Read ``pg_stat_database.sessions`` for each owner database.

    A fresh connection to the ``postgres`` maintenance database per read, so
    no cached statistics snapshot carries over.
    """

    conn = connect("postgres")
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT datname, sessions FROM pg_stat_database "
                "WHERE datname = ANY(%s)",
                (list(OWNER_TARGETS),),
            )
            return {name: int(sessions) for name, sessions in cur.fetchall()}
    finally:
        conn.close()


# Other clients move these counters too: a running NEXUS app polls
# ``save_01`` every few seconds, and a concurrent gate's template clones run
# ``pg_dump`` against ``NEXUS_template``. The child names every owner database
# on every run, so a child that reached one would move that database's counter
# in every bracket; one bracket in which a database stayed still clears it.
SESSION_BRACKET_ATTEMPTS = 5


@pytest.mark.requires_postgres
def test_owner_session_starts_no_owner_backend(tmp_path: Path) -> None:
    """Poisoned libpq transport settings never reach the child or a server.

    The parent environment here carries ``PGHOSTADDR``, ``PGPORT``,
    ``PGDATABASE``, and ``PGSERVICE`` that would steer libpq at this server;
    the allowlist drops them, the child asserts none arrived, the audit
    refuses every owner call before libpq, and each owner database's session
    counter stays still across at least one run of the child.
    """

    poisoned = {
        **os.environ,
        "PGHOSTADDR": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "save_01",
        "PGSERVICE": "nexus-dbname-audit",
        "PGSSLMODE": "disable",
    }
    uncleared = set(OWNER_TARGETS)
    brackets: list[dict[str, int]] = []
    for attempt in range(SESSION_BRACKET_ATTEMPTS):
        attempt_path = tmp_path / f"attempt_{attempt}"
        attempt_path.mkdir()
        before = _owner_sessions_started()
        assert sorted(before) == sorted(OWNER_TARGETS), before
        result = _owner_session(
            attempt_path,
            ["-p", "tests.dbname_audit"],
            {"NEXUS_RUN_POSTGRES": "1"},
            inherited=poisoned,
        )
        # A backend adds its session to the statistics by the time it exits;
        # give any backend the child started time to finish exiting.
        time.sleep(0.5)
        after = _owner_sessions_started()
        _assert_owner_session_failed(result)
        delta = {name: after[name] - before[name] for name in OWNER_TARGETS}
        brackets.append(delta)
        uncleared -= {name for name, moved in delta.items() if moved == 0}
        if not uncleared:
            return
    pytest.fail(
        f"session counters moved in every bracket for {sorted(uncleared)}: "
        f"{brackets}"
    )


@pytest.mark.requires_postgres
def test_constructors_imported_before_the_audit_are_audited(
    audit_database: str, tmp_path: Path
) -> None:
    """A cached ``connection`` and a preloaded ``LoggingConnection`` both record.

    Both reach a disposable database and are recorded; an owner target through
    either raises; and the session fails with both owner targets named.
    """

    result = _nested_session(
        tmp_path,
        PRELOADED_SESSION,
        activation=["-p", "early_constructors", "-p", "tests.dbname_audit"],
        environment={AUDIT_DATABASE_ENV: audit_database},
        modules={"early_constructors": EARLY_CONSTRUCTORS},
    )
    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "1 passed" in output, output
    failure_line = _owner_failure_line(output)
    assert "save_01 (psycopg2.extensions.connection)" in failure_line, output
    assert (
        "save_02 (psycopg2.extensions.connection "
        "(psycopg2.extras.LoggingConnection))" in failure_line
    ), output
    assert "qa640_dbname_audit_*" in output, output
    assert (
        "dbname audit: unaudited connection classes: "
        "psycopg2.extensions.ReplicationConnection" in output
    ), output


@pytest.mark.parametrize(
    ("name", "owner"),
    [
        ("save_01", True),
        ("save_05", True),
        ("NEXUS_template", True),
        ("postgres", False),
        ("template0", False),
        ("qa640_mig091_0123456789ab", False),
        ("qa640_save_05_clone", False),
        ("nexus_template", False),
    ],
)
def test_owner_filter_matches_whole_names_only(name: str, owner: bool) -> None:
    """Only an exact slot or template name is an owner target."""

    assert dbname_audit.is_owner_target(name) is owner

"""The owner-connection audit passes clean sessions and fails owner ones.

Each case runs a nested pytest session over a generated test file under
``tmp_path`` (outside ``tests/``, so the suite never collects it). The clean
session connects to a disposable database through every hooked driver path.
The owner session names ``save_01`` through ``save_05`` and ``NEXUS_template``
in every spelling the plugin parses, but dials a missing Unix-socket directory
or an RFC 2606 ``.invalid`` host, so no owner connection ever opens.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import dbname_audit
from tests.pg_fixtures import disposable_database

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DATABASE_ENV = "NEXUS_DBNAME_AUDIT_TEST_DATABASE"

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

MISSING_SOCKET_DIR = "/nonexistent/nexus-dbname-audit"
OWNER_SESSION = f"""
import asyncio

import asyncpg
import psycopg2
import psycopg2.extensions
import pytest

MISSING = "{MISSING_SOCKET_DIR}"


def test_owner_targets_in_every_spelling():
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(f"dbname=save_01 host={{MISSING}} connect_timeout=1")
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(
            "postgresql://audit.invalid/save_02?connect_timeout=1"
        )
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(dbname="save_03", host=MISSING, connect_timeout=1)
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.extensions.connection(f"dbname=save_04 host={{MISSING}}")
    with pytest.raises(OSError):
        asyncio.run(asyncpg.connect(database="NEXUS_template", host=MISSING))
    with pytest.raises(OSError):
        asyncio.run(
            asyncpg.connect(dsn="postgresql://audit.invalid/save_05", timeout=5)
        )
"""
OWNER_TARGETS = (
    "NEXUS_template",
    "save_01",
    "save_02",
    "save_03",
    "save_04",
    "save_05",
)


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
) -> subprocess.CompletedProcess[str]:
    """Run ``source`` as its own pytest session with the audit loaded."""

    test_file = tmp_path / "test_nested_session.py"
    test_file.write_text(source)
    env = {**os.environ, **environment}
    env.pop(dbname_audit.ENVIRONMENT_FLAG, None)
    env.update(environment)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")])
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
def test_session_naming_an_owner_fails_with_each_target_named(
    tmp_path: Path, activation: list[str], environment: dict[str, str]
) -> None:
    """Passing tests still fail the run when any owner target was named."""

    result = _nested_session(
        tmp_path, OWNER_SESSION, activation=activation, environment=environment
    )
    output = result.stdout + result.stderr
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "1 passed" in output, output
    failure_lines = [
        line
        for line in output.splitlines()
        if line.startswith("dbname audit: FAILED: owner targets: ")
    ]
    assert len(failure_lines) == 1, output
    for target in OWNER_TARGETS:
        assert f"{target} (" in failure_lines[0], output
    assert "test_nested_session.py::test_owner_targets_in_every_spelling" in (
        failure_lines[0]
    )


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

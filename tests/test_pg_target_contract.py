"""Offline guard: tests reach PostgreSQL only through the connection contract.

Test code resolves its server through ``nexus.database`` or ``tests.pg_fixtures``,
which delegates to it, so both honor ``[api.database]`` ahead of the PG*
environment. A literal loopback endpoint bypasses the contract, so an isolated
lane dials the owner's default server instead of its private cluster (issue
#804). Placeholder URLs that must never connect name an RFC 2606 ``.invalid``
host instead of a loopback one.
"""

from __future__ import annotations

import getpass
import re
from pathlib import Path
from typing import Any

import psycopg2
import pytest
import tomlkit

from nexus.database import (
    asyncpg_kwargs,
    connection_kwargs,
    connection_target,
    url_connection_kwargs,
)
from tests import pg_fixtures

TESTS_ROOT = Path(__file__).resolve().parent
SCANNED_SUFFIXES = frozenset({".py", ".json"})

_LOOPBACK = r"(?:localhost|127\.0\.0\.1|\[::1\])"
OWNER_TARGET_PATTERNS = {
    "loopback host on port 5432": re.compile(_LOOPBACK + r":5432\b"),
    "port pinned to 5432": re.compile(
        r"""(?:["']port["']\s*[:,]|\bport\s*=)\s*["']?5432\b"""
    ),
    "PostgreSQL URL naming a loopback host": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://(?:[^@/\s\"']*@)?" + _LOOPBACK + r"(?![\w.-])"
    ),
}


def _owner_targets(text: str) -> list[str]:
    """Name each owner-endpoint pattern that ``text`` contains."""
    return [
        name for name, pattern in OWNER_TARGET_PATTERNS.items() if pattern.search(text)
    ]


# Known-bad spellings are split so this file stays inside its own scan.
@pytest.mark.parametrize(
    "line",
    [
        'DSN = "postgresql://pythagor@' + "localhost" + ':5432/save_01"',
        '    "port"' + ": 5432",
        "port=db_config.get('port', " + "5432)",
        "psycopg2.connect(host='127.0.0.1', port=" + "5432)",
        'db_url="postgresql://test@' + 'localhost/disposable"',
        '"postgresql+psycopg2://' + '[::1]/save_02"',
    ],
)
def test_guard_recognizes_owner_endpoint_spellings(line: str) -> None:
    """Each historical hardcoded-target form trips at least one pattern."""
    assert _owner_targets(line)


@pytest.mark.parametrize(
    "line",
    [
        'port=os.environ.get("PGPORT", "5432"),',
        "return database_url(dbname)",
        'db_url="postgresql://test@fixture.invalid/disposable"',
        'API = f"http://localhost:{port}"',
        "PGHOST=127.0.0.1 PGPORT=55432",
        '"pid": 54321',
    ],
)
def test_guard_allows_contract_and_non_postgres_spellings(line: str) -> None:
    """Environment-resolved ports, placeholders, and HTTP URLs stay legal."""
    assert _owner_targets(line) == []


def test_tests_never_hardcode_the_owner_postgres_endpoint() -> None:
    """No test source or JSON fixture names the owner's loopback endpoint."""
    violations = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{number}: {name}: {line.strip()}"
        for path in sorted(TESTS_ROOT.rglob("*"))
        if path.suffix in SCANNED_SUFFIXES and path.is_file()
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        for name in _owner_targets(line)
    ]
    assert violations == [], (
        "Resolve PostgreSQL through nexus.database.database_url(), "
        "nexus.database.connection_kwargs(), or tests.pg_fixtures.connect(); "
        "use a .invalid host for URLs that never connect:\n" + "\n".join(violations)
    )


# A second resolver in the shared fixtures reads PG* itself; the contract owns it.
DIRECT_PG_ENVIRONMENT = re.compile(
    r"""(?:\benviron(?:\.\w+)?|\bgetenv)\s*[\[(]\s*["']PG[A-Z]*["']"""
)


@pytest.mark.parametrize(
    "line",
    [
        '"port": os.environ.get("PGPORT", "55432"),',
        'user = os.environ["PGUSER"]',
        'host = os.getenv("PGHOST")',
    ],
)
def test_fixture_guard_recognizes_direct_pg_environment_reads(line: str) -> None:
    """Each way of reading a PG* variable directly trips the fixture guard."""
    assert DIRECT_PG_ENVIRONMENT.search(line)


@pytest.mark.parametrize(
    "line",
    [
        'if story_pin is None and os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":',
        "explicit ``[api.database]`` values, then the PG* environment,",
        "env=subprocess_env(),",
    ],
)
def test_fixture_guard_allows_contract_spellings(line: str) -> None:
    """Other variables, prose about PG*, and the contract's own env stay legal."""
    assert DIRECT_PG_ENVIRONMENT.search(line) is None


def test_pg_fixtures_reads_no_pg_environment_itself() -> None:
    """The shared fixtures take host, port, and user from nexus.database only."""
    source = TESTS_ROOT / "pg_fixtures.py"
    reads = [
        f"{source.relative_to(TESTS_ROOT.parent)}:{number}: {line.strip()}"
        for number, line in enumerate(source.read_text().splitlines(), start=1)
        if DIRECT_PG_ENVIRONMENT.search(line)
    ]
    assert reads == [], (
        "Derive fixture connections from nexus.database.connection_kwargs():\n"
        + "\n".join(reads)
    )


FIXTURE_DATABASE = "qa804_fixture_target"
_LIBPQ_ENVIRONMENT = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGCONNECT_TIMEOUT",
    "PGOPTIONS",
)


@pytest.fixture
def runtime_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the runtime at an isolated nexus.toml copy with no PG* overrides."""
    for key in _LIBPQ_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "nexus.toml"
    path.write_text((TESTS_ROOT.parent / "nexus.toml").read_text())
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path


def _configure_database(path: Path, *, host: str, port: int, user: str) -> None:
    """Name a server in ``[api.database]``, which outranks the PG* environment."""
    document: Any = tomlkit.parse(path.read_text())
    database = document["api"]["database"]
    database["host"] = host
    database["port"] = port
    database["user"] = user
    path.write_text(tomlkit.dumps(document))


@pytest.mark.parametrize(
    ("configured", "environment", "expected"),
    [
        pytest.param(
            None,
            {
                "PGHOST": "environment.invalid",
                "PGPORT": "55442",
                "PGUSER": "environment_role",
                "PGPASSWORD": "environment-secret",
                "PGOPTIONS": "-c statement_timeout=1000",
            },
            {"host": "environment.invalid", "port": 55442, "user": "environment_role"},
            id="pg-environment-only",
        ),
        pytest.param(
            {"host": "configured.invalid", "port": 55443, "user": "configured_role"},
            {
                "PGHOST": "environment.invalid",
                "PGPORT": "55444",
                "PGUSER": "environment_role",
            },
            {"host": "configured.invalid", "port": 55443, "user": "configured_role"},
            id="toml-outranks-pg-environment",
        ),
        pytest.param(
            None,
            {},
            {"host": "", "user": getpass.getuser()},
            id="libpq-socket-and-os-user-defaults",
        ),
    ],
)
def test_fixture_clients_resolve_the_runtime_contract(
    runtime_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured: dict[str, Any] | None,
    environment: dict[str, str],
    expected: dict[str, Any],
) -> None:
    """Every pg_fixtures client carries exactly the runtime's parameters."""
    if configured is not None:
        _configure_database(runtime_config, **configured)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    contract = connection_kwargs(FIXTURE_DATABASE)
    target = connection_target(contract)
    assert {key: target[key] for key in expected} == expected
    assert target["dbname"] == FIXTURE_DATABASE
    assert url_connection_kwargs(pg_fixtures.sqlalchemy_url(FIXTURE_DATABASE)) == (
        contract
    )
    assert pg_fixtures.asyncpg_kwargs(FIXTURE_DATABASE) == asyncpg_kwargs(
        FIXTURE_DATABASE
    )
    assert pg_fixtures.connection_parameters(FIXTURE_DATABASE) == contract


@pytest.mark.requires_postgres
def test_fixture_connect_dials_the_configured_server(
    runtime_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """connect() dials the ``[api.database]`` port even when PG* names another.

    Both loopback ports are closed, so libpq refuses at once and names the
    port it dialed. No server is needed, but the default tier forbids any
    connection attempt, so this runs in the PostgreSQL tier.
    """
    _configure_database(runtime_config, host="127.0.0.1", port=1, user="configured")
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "2")
    monkeypatch.setenv("PGUSER", "environment_role")
    with pytest.raises(psycopg2.OperationalError) as refused:
        pg_fixtures.connect(FIXTURE_DATABASE)
    message = str(refused.value)
    assert re.search(r"\bport 1\b", message), message
    assert not re.search(r"\bport 2\b", message), message

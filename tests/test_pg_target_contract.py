"""Offline guard: tests reach PostgreSQL only through the connection contract.

Test code resolves its server through ``nexus.database`` or ``tests.pg_fixtures``,
which delegates to it, so both honor ``[api.database]`` ahead of the PG*
environment. A literal loopback endpoint bypasses the contract, so an isolated
lane dials the owner's default server instead of its private cluster (issue
#804). So does a target assembled from PG* by hand: it honors the environment
but not a configured ``[api.database]`` server. Placeholder URLs that must
never connect name an RFC 2606 ``.invalid`` host instead of a real one.
"""

from __future__ import annotations

import ast
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


def _tree_sources(suffixes: frozenset[str]) -> list[Path]:
    """Return every test file with one of ``suffixes``, in a stable order."""
    return sorted(
        path
        for path in TESTS_ROOT.rglob("*")
        if path.suffix in suffixes and path.is_file()
    )


def _line_number(text: str, offset: int) -> int:
    """Return the 1-based line of ``offset`` in ``text``."""
    return text.count("\n", 0, offset) + 1


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
        'port=os.environ.get("' + 'PGPORT", "5432"),',
        "return database_url(dbname)",
        'db_url="postgresql://test@fixture.invalid/disposable"',
        'API = f"http://localhost:{port}"',
        "PGHOST=127.0.0.1 PGPORT=55432",
        '"pid": 54321',
    ],
)
def test_guard_allows_contract_and_non_postgres_spellings(line: str) -> None:
    """Only literal owner endpoints trip these patterns; PG* reads are below."""
    assert _owner_targets(line) == []


def test_tests_never_hardcode_the_owner_postgres_endpoint() -> None:
    """No test source or JSON fixture names the owner's loopback endpoint."""
    violations = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{number}: {name}: {line.strip()}"
        for path in _tree_sources(SCANNED_SUFFIXES)
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        for name in _owner_targets(line)
    ]
    assert violations == [], (
        "Resolve PostgreSQL through nexus.database.database_url(), "
        "nexus.database.connection_kwargs(), or tests.pg_fixtures.connect(); "
        "use a .invalid host for URLs that never connect:\n" + "\n".join(violations)
    )


# A test that reads PG* itself builds a second resolver: it follows the
# environment but skips a configured [api.database] server. Writing the
# contract's inputs through monkeypatch.setenv stays legal. Scanned over whole
# files, so a call split across lines is still caught.
DIRECT_PG_ENVIRONMENT = re.compile(
    r"""(?:\benviron(?:\.\w+)?|\bgetenv)\s*[\[(]\s*["']PG[A-Z]*["']"""
)


# Samples are split before the name so this file stays inside its own scan.
@pytest.mark.parametrize(
    "line",
    [
        '"port": os.environ.get("' + 'PGPORT", "55432"),',
        'user = os.environ["' + 'PGUSER"]',
        'host = os.getenv("' + 'PGHOST")',
        'password=os.environ.get(\n    "' + 'PGPASSWORD"\n)',
        "f\"{os.environ.get('" + "PGHOST', 'db')}:\"",
    ],
)
def test_environment_guard_recognizes_direct_pg_reads(line: str) -> None:
    """Each way of reading a PG* variable directly trips the guard."""
    assert DIRECT_PG_ENVIRONMENT.search(line)


@pytest.mark.parametrize(
    "line",
    [
        'if story_pin is None and os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":',
        "explicit ``[api.database]`` values, then the PG* environment,",
        "env=subprocess_env(),",
        'monkeypatch.setenv("PGPORT", "1")',
        'assert subprocess_env()["PGHOST"] == "configured.example"',
    ],
)
def test_environment_guard_allows_contract_spellings(line: str) -> None:
    """Other variables, prose, contract output, and setenv inputs stay legal."""
    assert DIRECT_PG_ENVIRONMENT.search(line) is None


def test_tests_never_read_the_pg_environment_directly() -> None:
    """No test module, fixture included, resolves host, port, or user from PG*."""
    reads = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{_line_number(text, match.start())}:"
        f" {match.group(0)}"
        for path in _tree_sources(frozenset({".py"}))
        for text in [path.read_text()]
        for match in DIRECT_PG_ENVIRONMENT.finditer(text)
    ]
    assert reads == [], (
        "Resolve PostgreSQL through tests.pg_fixtures.connect(), "
        "nexus.database.connection_kwargs(), database_url(), or "
        "tests.pg_fixtures.asyncpg_kwargs(); give subprocesses subprocess_env():\n"
        + "\n".join(reads)
    )


# A URL that names a server (or a database on libpq's default server) is a
# hand-built target. Only a bare scheme, for a SQLAlchemy engine whose creator
# connects through the contract, and a portless RFC 2606 .invalid placeholder
# are legal.
POSTGRES_URL = re.compile(
    r"""postgres(?:ql)?(?:\+\w+)?://(?:[^@/\s"']*@)?(?P<host>[^/:?#\s"'@]*)"""
    r"""(?::(?P<port>[^/?#\s"']*))?(?P<path>/[^?#\s"']+)?"""
)


def _hand_built_urls(text: str) -> list[tuple[int, str]]:
    """Return ``(offset, url)`` for each PostgreSQL URL that names a target."""
    found = []
    for match in POSTGRES_URL.finditer(text):
        host = match["host"]
        if host:
            legal = host.endswith(".invalid") and match["port"] is None
        else:
            legal = match["port"] is None and match["path"] is None
        if not legal:
            found.append((match.start(), match.group(0)))
    return found


@pytest.mark.parametrize(
    "line",
    [
        'f"postgresql://' + '{user}@{host}:{port}/{dbname}"',
        "db_url='postgresql://" + "unused'",
        '"postgresql+psycopg2://' + 'db.example/save_02"',
        '"postgresql://' + 'pythagor@/save_01"',
        '"postgres://' + 'save_01"',
        '"postgresql://' + 'fixture.invalid:5432/save_01"',
    ],
)
def test_url_guard_recognizes_hand_built_urls(line: str) -> None:
    """A URL naming any server, or a database without one, trips the guard."""
    assert _hand_built_urls(line)


@pytest.mark.parametrize(
    "line",
    [
        'create_engine("postgresql+psycopg2://", creator=lambda: connect(db))',
        '"postgresql://fixture.invalid/"',
        'db_url="postgresql://test@fixture.invalid/disposable"',
        "engine = create_engine(database_url(dbname))",
    ],
)
def test_url_guard_allows_contract_and_placeholder_urls(line: str) -> None:
    """Bare schemes, .invalid placeholders, and contract URLs stay legal."""
    assert _hand_built_urls(line) == []


def test_tests_never_spell_a_postgres_url_with_a_target() -> None:
    """No test source or JSON fixture writes a PostgreSQL URL naming a server."""
    violations = [
        f"{path.relative_to(TESTS_ROOT.parent)}:{_line_number(text, offset)}: {url}"
        for path in _tree_sources(SCANNED_SUFFIXES)
        for text in [path.read_text()]
        for offset, url in _hand_built_urls(text)
    ]
    assert violations == [], (
        "Build PostgreSQL URLs with nexus.database.database_url(); "
        "use a .invalid host for URLs that never connect:\n" + "\n".join(violations)
    )


# Driver calls whose target is spelled out in keywords bypass the contract even
# when every value is a variable. The contract's own adapters supply these
# keywords through ``**`` unpacking, which the scan does not count.
DRIVER_CALLS = (
    "psycopg2.connect",
    "asyncpg.connect",
    "asyncpg.create_pool",
    "make_dsn",
    "URL.create",
)
TARGET_KEYWORDS = frozenset(
    {"host", "hostaddr", "port", "user", "username", "password", "dbname", "database"}
)
# Both files start two disposable clusters and dial each one by its explicit
# host and port: the conflicting environment is the point of the proof that
# the contract picks the configured cluster. Nothing else may spell a target.
DRIVER_TARGET_ALLOWLIST = frozenset(
    {"tests/test_database_contract.py", "tests/test_connection_lifecycle.py"}
)


def _dotted_name(node: ast.expr) -> str:
    """Spell an attribute chain such as ``psycopg2.extensions.make_dsn``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _driver_targets(source: str) -> list[tuple[int, str]]:
    """Return ``(line, call)`` for each driver call that names its own target."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if not any(name == call or name.endswith("." + call) for call in DRIVER_CALLS):
            continue
        keywords = sorted(
            keyword.arg for keyword in node.keywords if keyword.arg in TARGET_KEYWORDS
        )
        if keywords:
            spelled = ", ".join(f"{keyword}=" for keyword in keywords)
            found.append((node.lineno, f"{name}({spelled})"))
    return found


@pytest.mark.parametrize(
    "source",
    [
        "psycopg2.connect(dbname=TEST_DBNAME)",
        'psycopg2.connect(dbname=dbname, user="pythagor")',
        "await asyncpg.connect(database=name, host=host, port=port)",
        "psycopg2.extensions.make_dsn(dbname=name, **params)",
        'URL.create("postgresql+psycopg2", username=user, database=name)',
    ],
)
def test_driver_guard_recognizes_hand_written_targets(source: str) -> None:
    """Each driver call that names a database or server trips the guard."""
    assert _driver_targets(source)


@pytest.mark.parametrize(
    "source",
    [
        "psycopg2.connect(**connection_kwargs(dbname))",
        "psycopg2.connect(get_slot_db_url(slot=2), cursor_factory=RealDictCursor)",
        "await asyncpg.connect(**asyncpg_kwargs(dbname))",
        "pg_fixtures.connect(dbname, cursor_factory=RealDictCursor)",
        "make_dsn(**connection_kwargs('NEXUS_template'))",
    ],
)
def test_driver_guard_allows_contract_calls(source: str) -> None:
    """Contract-derived parameters and the fixture helpers stay legal."""
    assert _driver_targets(source) == []


def test_tests_never_hand_a_driver_its_own_target() -> None:
    """Driver calls in tests take their target from the contract."""
    violations = [
        f"{relative}:{line}: {call}"
        for path in _tree_sources(frozenset({".py"}))
        for relative in [path.relative_to(TESTS_ROOT.parent).as_posix()]
        if relative not in DRIVER_TARGET_ALLOWLIST
        for line, call in _driver_targets(path.read_text())
    ]
    assert violations == [], (
        "Pass **nexus.database.connection_kwargs(dbname) or "
        "**tests.pg_fixtures.asyncpg_kwargs(dbname), or call "
        "tests.pg_fixtures.connect(dbname):\n" + "\n".join(violations)
    )


def test_driver_allowlist_names_only_current_exceptions() -> None:
    """Each allowlisted file exists and still needs its exception."""
    for relative in sorted(DRIVER_TARGET_ALLOWLIST):
        path = TESTS_ROOT.parent / relative
        assert path.is_file(), f"{relative} is gone; drop it from the allowlist"
        needed = _driver_targets(path.read_text())
        assert needed, f"{relative} no longer spells a target; drop the exception"


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

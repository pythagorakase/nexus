"""Offline guard: tests reach PostgreSQL only through the connection contract.

Test code resolves its server through ``nexus.database`` or ``tests.pg_fixtures``,
which honor ``[api.database]`` and the PG* environment. A literal loopback
endpoint bypasses both, so an isolated lane dials the owner's default server
instead of its private cluster (issue #804). Placeholder URLs that must never
connect name an RFC 2606 ``.invalid`` host instead of a loopback one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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

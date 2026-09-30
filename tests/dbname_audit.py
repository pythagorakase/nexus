"""Opt-in pytest plugin that fails a session which connects to an owner database.

Load it with ``-p tests.dbname_audit``, or set ``NEXUS_DBNAME_AUDIT=1`` before
pytest starts (``tests/conftest.py`` reads the variable once and loads this
plugin). Once configured, it records the database named by every PostgreSQL
connection this pytest process attempts:

- psycopg2: every ``psycopg2.connect`` call, including a ``connect`` imported
  before the plugin loaded, SQLAlchemy engines, and ``psycopg2.pool``, through
  ``psycopg2._connect``, which ``connect`` resolves at call time; and direct
  construction of ``psycopg2.extensions.connection``, which bypasses
  ``connect``. The ``dbname`` in the DSN string or URL is recorded before the
  connection opens, and the name the server reports after it opens.
- asyncpg: every ``asyncpg.connect``, pool, and SQLAlchemy asyncpg connection,
  through ``asyncpg.connect_utils._parse_connect_arguments``, which resolves
  the ``database`` keyword, a DSN URL, and the defaults to one name before any
  socket opens.

At session end the plugin lists every target and **fails the run** (exit
status 1, whatever the tests did) when any target is ``NEXUS_template`` or a
save slot (``save_NN``). ``postgres``, ``template0``, and disposable databases
are allowed. Child processes are not audited: ``pg_dump``, ``psql``, a routed
gateway, and a nested pytest each need their own audit.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

import pytest

ENVIRONMENT_FLAG = "NEXUS_DBNAME_AUDIT"
OWNER_TARGET = re.compile(r"save_\d+|NEXUS_template")
_DISPOSABLE_SUFFIX = re.compile(r"_[0-9a-f]{12}$")
_OUTSIDE_TESTS = "<outside a test>"

# target -> {"drivers": set of driver labels, "nodes": set of node ids}
_TARGETS: dict[str, dict[str, set[str]]] = {}
_current_node = _OUTSIDE_TESTS
_restore: list[Callable[[], None]] = []


def is_owner_target(dbname: str) -> bool:
    """Whether ``dbname`` names the owner's template or a save slot."""

    return OWNER_TARGET.fullmatch(dbname) is not None


def enabled_by_environment() -> bool:
    """Whether ``NEXUS_DBNAME_AUDIT=1`` asks ``tests/conftest.py`` to load this."""

    return os.environ.get(ENVIRONMENT_FLAG) == "1"


def recorded() -> dict[str, frozenset[str]]:
    """Return each recorded target with the drivers that named it."""

    return {name: frozenset(entry["drivers"]) for name, entry in _TARGETS.items()}


def owner_targets() -> dict[str, frozenset[str]]:
    """Return each recorded owner target with the test nodes that opened it."""

    return {
        name: frozenset(entry["nodes"])
        for name, entry in _TARGETS.items()
        if is_owner_target(name)
    }


def _record(dbname: str | None, driver: str) -> None:
    if not dbname:
        return
    entry = _TARGETS.setdefault(dbname, {"drivers": set(), "nodes": set()})
    entry["drivers"].add(driver)
    entry["nodes"].add(_current_node)


def _dsn_dbname(dsn: Any) -> str | None:
    """Return the database a libpq DSN string or URL names, if it names one."""

    from psycopg2.extensions import parse_dsn

    if dsn is None:
        return None
    try:
        parsed = parse_dsn(str(dsn))
    except Exception:
        # The driver rejects the same string itself; nothing is opened.
        return None
    name = parsed.get("dbname")
    return str(name) if name else None


def _connected_dbname(conn: Any) -> str | None:
    """Return the database an open psycopg2 connection actually reached."""

    info = getattr(conn, "info", None)
    return getattr(info, "dbname", None)


def _install_psycopg2() -> None:
    import psycopg2
    import psycopg2.extensions
    from psycopg2 import _psycopg

    # Typed as Any: the hooks replace private attributes the stubs omit.
    package: Any = psycopg2
    extensions: Any = psycopg2.extensions
    c_module: Any = _psycopg
    original_connect = getattr(package, "_connect", None)
    if not callable(original_connect):
        raise pytest.UsageError(
            "dbname audit: psycopg2._connect is missing; the psycopg2 hook "
            "cannot record connections"
        )

    def audited_connect(dsn: Any, *args: Any, **kwargs: Any) -> Any:
        _record(_dsn_dbname(dsn), "psycopg2")
        conn = original_connect(dsn, *args, **kwargs)
        _record(_connected_dbname(conn), "psycopg2")
        return conn

    original_class: Any = extensions.connection

    class _AuditedConnectionType(type):
        """Keep ``isinstance`` checks against the replaced class truthful."""

        def __instancecheck__(cls, instance: Any) -> bool:
            if cls is AuditedConnection:
                return isinstance(instance, original_class)
            return type.__instancecheck__(cls, instance)

        def __subclasscheck__(cls, subclass: type) -> bool:
            if cls is AuditedConnection:
                return issubclass(subclass, original_class)
            return type.__subclasscheck__(cls, subclass)

    class AuditedConnection(original_class, metaclass=_AuditedConnectionType):
        """``psycopg2.extensions.connection`` that records its target."""

        def __init__(self, dsn: Any, *args: Any, **kwargs: Any) -> None:
            _record(_dsn_dbname(dsn), "psycopg2.extensions.connection")
            super().__init__(dsn, *args, **kwargs)
            _record(_connected_dbname(self), "psycopg2.extensions.connection")

    AuditedConnection.__name__ = original_class.__name__
    AuditedConnection.__qualname__ = original_class.__qualname__

    package._connect = audited_connect
    c_module._connect = audited_connect
    extensions.connection = AuditedConnection
    c_module.connection = AuditedConnection

    def restore() -> None:
        package._connect = original_connect
        c_module._connect = original_connect
        extensions.connection = original_class
        c_module.connection = original_class

    _restore.append(restore)


def _install_asyncpg() -> None:
    from asyncpg import connect_utils  # type: ignore[import-untyped]

    original_parse = getattr(connect_utils, "_parse_connect_arguments", None)
    if not callable(original_parse):
        raise pytest.UsageError(
            "dbname audit: asyncpg.connect_utils._parse_connect_arguments is "
            "missing; the asyncpg hook cannot record connections"
        )

    def audited_parse(*args: Any, **kwargs: Any) -> Any:
        _record(kwargs.get("database"), "asyncpg")
        dsn = kwargs.get("dsn")
        if dsn:
            _record(_dsn_dbname(dsn), "asyncpg")
        result = original_parse(*args, **kwargs)
        _record(getattr(result[1], "database", None), "asyncpg")
        return result

    connect_utils._parse_connect_arguments = audited_parse

    def restore() -> None:
        connect_utils._parse_connect_arguments = original_parse

    _restore.append(restore)


def pytest_configure(config: pytest.Config) -> None:
    """Install the driver hooks for the whole session."""

    if _restore:
        return
    _install_psycopg2()
    _install_asyncpg()


def pytest_unconfigure(config: pytest.Config) -> None:
    """Put the drivers back as they were."""

    while _restore:
        _restore.pop()()


def pytest_runtest_logstart(nodeid: str, location: Any) -> None:
    """Attribute connections to the test that opens them."""

    global _current_node
    _current_node = nodeid


def pytest_runtest_logfinish(nodeid: str, location: Any) -> None:
    """Connections between tests belong to no test."""

    global _current_node
    _current_node = _OUTSIDE_TESTS


def _collapsed_targets() -> list[str]:
    """Name each target, folding uniquely suffixed clones into one prefix."""

    counts: dict[str, int] = {}
    for name in _TARGETS:
        key = _DISPOSABLE_SUFFIX.sub("_*", name)
        counts[key] = counts.get(key, 0) + 1
    return [
        key if count == 1 else f"{key} x{count}"
        for key, count in sorted(counts.items())
    ]


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run when any recorded target is an owner database."""

    if owner_targets() and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Report every target and any owner target by the test that opened it."""

    terminalreporter.write_line(
        f"dbname audit: {len(_TARGETS)} targets: "
        + (", ".join(_collapsed_targets()) or "none")
    )
    owners = owner_targets()
    if not owners:
        terminalreporter.write_line("dbname audit: owner targets: none")
        return
    terminalreporter.write_line(
        "dbname audit: FAILED: owner targets: "
        + "; ".join(
            f"{name} ({', '.join(sorted(_TARGETS[name]['drivers']))}) "
            f"from {', '.join(sorted(nodes))}"
            for name, nodes in sorted(owners.items())
        ),
        red=True,
        bold=True,
    )

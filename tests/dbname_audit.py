"""Opt-in pytest plugin that refuses and fails owner-database connections.

Load it with ``-p tests.dbname_audit``, or set ``NEXUS_DBNAME_AUDIT=1`` before
pytest starts (``tests/conftest.py`` reads the variable once and loads this
plugin). Once configured, it records the database named by every PostgreSQL
connection this pytest process attempts:

- psycopg2: every ``psycopg2.connect`` call, including a ``connect`` imported
  before the plugin loaded, SQLAlchemy engines, and ``psycopg2.pool``, through
  ``psycopg2._connect``, which ``connect`` resolves at call time; and direct
  construction of ``psycopg2.extensions.connection``, which bypasses
  ``connect``. At configure time the plugin replaces that class with a
  recording subclass in every loaded module that holds it (a constructor
  imported before the plugin loaded included) and rebinds ``__bases__`` of
  each Python-level subclass whose direct base is the original class
  (``psycopg2.extras.LoggingConnection``, ``DictConnection``,
  ``RealDictConnection``, ``NamedTupleConnection``, and any other it finds)
  to the recording subclass. The ``dbname`` in the DSN string, URL, or
  keywords (or ``PGDATABASE`` when they name neither a database nor a
  service) is recorded before
  connecting, and libpq's resolved ``dbname`` (``conn.info.dbname``, a
  client-side value, not one the server reports) after connecting.
- asyncpg: every ``asyncpg.connect``, pool, and SQLAlchemy asyncpg connection,
  through ``asyncpg.connect_utils._parse_connect_arguments``. The database is
  read in asyncpg's own order (the ``database`` keyword, else the DSN's
  database, else ``PGDATABASE``) and again from asyncpg's resolved connection
  parameters, both before any socket opens.

An owner target is ``NEXUS_template`` or a save slot (``save_NN``);
``postgres``, ``template0``, and disposable databases are allowed. The plugin
refuses an owner target at connect time: it raises
``OwnerDatabaseConnectionRefused``, naming the target and the test, before
libpq or asyncpg opens a connection. A ``dbname`` that only a libpq service
file supplies is known only after libpq connects; the plugin then closes that
connection at once and raises the same refusal. At session end the plugin
lists every target and **fails the run** (exit status 1, whatever the tests
did) when any target is an owner database, so a refusal that a test caught
and ignored still fails the session.

Outside the audit: a subprocess that connects on its own (``pg_dump``,
``psql``, a routed gateway, a nested pytest; each needs its own audit), any
other driver (psycopg 3, pg8000, ``ctypes`` into libpq), and any subclass
whose ``__bases__`` rebind Python refused, with every class built on it;
the summary names each refused class as unaudited
(``psycopg2.extensions.ReplicationConnection``, a C type that
``LogicalReplicationConnection`` and ``PhysicalReplicationConnection``
extend, is one). A reference to the original psycopg2 connection class
captured before the plugin configured outside a module's globals (a default
argument, a class attribute, a closure cell, a container) is not swept; no
such holder exists in the repository today (checked by a garbage-collector
reference scan that also searches the untracked tuples and dicts
``gc.get_referrers`` misses,
``tests/test_dbname_audit.py::test_no_preconfigure_holder_escapes_the_sweep``).
The AST owner-target guard planned for #885 slice B2-9b covers the owner
literals those paths would need.
"""

from __future__ import annotations

import os
import re
import sys
import types
import urllib.parse
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
# Qualified names of connection subclasses whose ``__bases__`` rebind failed.
_UNAUDITED: list[str] = []


class OwnerDatabaseConnectionRefused(RuntimeError):
    """A connection named an owner database while the audit was active."""

    def __init__(self, target: str, driver: str, node: str) -> None:
        self.target = target
        self.driver = driver
        self.node = node
        super().__init__(
            f"dbname audit: refused a {driver} connection to owner database "
            f"{target!r} from {node}; tests connect only to disposable databases"
        )


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


def unaudited() -> tuple[str, ...]:
    """Return the connection subclasses whose ``__bases__`` rebind failed."""

    return tuple(_UNAUDITED)


def _record(dbname: str | None, driver: str) -> None:
    if not dbname:
        return
    entry = _TARGETS.setdefault(dbname, {"drivers": set(), "nodes": set()})
    entry["drivers"].add(driver)
    entry["nodes"].add(_current_node)


def _admit(names: list[str | None], driver: str) -> None:
    """Record every name, then refuse the first owner target among them."""

    for name in names:
        _record(name, driver)
    for name in names:
        if name and is_owner_target(name):
            raise OwnerDatabaseConnectionRefused(name, driver, _current_node)


def _admit_open(conn: Any, driver: str) -> None:
    """Record an open psycopg2 connection's database; close and refuse owners."""

    name = _connected_dbname(conn)
    _record(name, driver)
    if name and is_owner_target(name):
        conn.close()
        raise OwnerDatabaseConnectionRefused(name, driver, _current_node)


def _dsn_dbname(dsn: Any) -> str | None:
    """Return the database a libpq DSN string or URL names, if it names one.

    A DSN that names no database and no service connects to ``PGDATABASE``
    when it is set. A service file's ``dbname`` outranks ``PGDATABASE``, so a
    service leaves the name to the check after connecting.
    """

    import psycopg2
    from psycopg2.extensions import parse_dsn

    if dsn is None:
        return None
    try:
        parsed = parse_dsn(str(dsn))
    except psycopg2.ProgrammingError:
        # The driver rejects the same string itself; nothing is opened.
        return None
    name = parsed.get("dbname")
    if not name and not (parsed.get("service") or os.environ.get("PGSERVICE")):
        name = os.environ.get("PGDATABASE")
    return str(name) if name else None


def _asyncpg_dbname(database: Any, dsn: Any) -> str | None:
    """Return the database asyncpg will connect to, read before it parses.

    asyncpg's own order (``asyncpg.connect_utils._parse_connect_dsn_and_args``):
    an explicit ``database`` keyword; else the DSN's path, then its ``dbname``
    and ``database`` query parameters; else ``PGDATABASE``. asyncpg reads no
    service file. An empty name leaves the choice to the server, which the
    check on asyncpg's resolved parameters then records.
    """

    if database is not None:
        return str(database) or None
    if dsn:
        parsed = urllib.parse.urlparse(str(dsn))
        if parsed.path:
            return urllib.parse.unquote(parsed.path.removeprefix("/")) or None
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("dbname", "database"):
            if key in query:
                return query[key][-1] or None
    return os.environ.get("PGDATABASE") or None


def _connected_dbname(conn: Any) -> str | None:
    """Return libpq's resolved ``dbname`` for an open psycopg2 connection."""

    info = getattr(conn, "info", None)
    return getattr(info, "dbname", None)


def _constructor_label(cls: type, audited: type) -> str:
    """Name the driver path for a direct construction of ``cls``."""

    if cls is audited:
        return "psycopg2.extensions.connection"
    return f"psycopg2.extensions.connection ({cls.__module__}.{cls.__qualname__})"


def _loaded_modules() -> list[types.ModuleType]:
    return [
        module
        for module in list(sys.modules.values())
        if isinstance(module, types.ModuleType)
    ]


def _sweep_constructors(original_class: type, audited_class: type) -> None:
    """Route every loaded reference to ``original_class`` through the recorder.

    Module attributes that are the original class are replaced; each direct
    subclass (from ``__subclasses__`` and from loaded modules) has its
    ``__bases__`` rebound. A refused rebind names the class in ``_UNAUDITED``.
    """

    replaced: list[tuple[types.ModuleType, str]] = []
    subclasses: dict[int, type] = {
        id(cls): cls for cls in original_class.__subclasses__()
    }
    for module in _loaded_modules():
        for name, value in list(vars(module).items()):
            if value is original_class:
                setattr(module, name, audited_class)
                replaced.append((module, name))
            elif isinstance(value, type) and original_class in value.__bases__:
                subclasses[id(value)] = value

    rebound: list[tuple[type, tuple[type, ...]]] = []
    for cls in subclasses.values():
        if cls is audited_class:
            continue
        bases = cls.__bases__
        try:
            cls.__bases__ = tuple(
                audited_class if base is original_class else base for base in bases
            )
        except TypeError:
            pass
        if audited_class in cls.__mro__:
            rebound.append((cls, bases))
        else:
            _UNAUDITED.append(f"{cls.__module__}.{cls.__qualname__}")

    def restore() -> None:
        for cls, bases in rebound:
            cls.__bases__ = bases
        for module, name in replaced:
            if vars(module).get(name) is audited_class:
                setattr(module, name, original_class)
        _UNAUDITED.clear()

    _restore.append(restore)


def _install_psycopg2() -> None:
    import psycopg2
    import psycopg2.extensions
    import psycopg2.extras  # noqa: F401  (its subclasses join the sweep)
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
        _admit([_dsn_dbname(dsn)], "psycopg2")
        conn = original_connect(dsn, *args, **kwargs)
        _admit_open(conn, "psycopg2")
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
        """``psycopg2.extensions.connection`` that records and refuses targets."""

        # No instance dict: the layout matches the original class, so Python
        # accepts this class as the rebound base of existing subclasses.
        __slots__ = ()

        def __init__(self, dsn: Any, *args: Any, **kwargs: Any) -> None:
            label = _constructor_label(type(self), AuditedConnection)
            _admit([_dsn_dbname(dsn)], label)
            super().__init__(dsn, *args, **kwargs)
            _admit_open(self, label)

    AuditedConnection.__name__ = original_class.__name__
    AuditedConnection.__qualname__ = original_class.__qualname__

    package._connect = audited_connect
    c_module._connect = audited_connect

    def restore() -> None:
        package._connect = original_connect
        c_module._connect = original_connect

    _restore.append(restore)
    # Replaces extensions.connection and _psycopg.connection with the rest.
    _sweep_constructors(original_class, AuditedConnection)


def _install_asyncpg() -> None:
    from asyncpg import connect_utils  # type: ignore[import-untyped]

    original_parse = getattr(connect_utils, "_parse_connect_arguments", None)
    if not callable(original_parse):
        raise pytest.UsageError(
            "dbname audit: asyncpg.connect_utils._parse_connect_arguments is "
            "missing; the asyncpg hook cannot record connections"
        )

    def audited_parse(*args: Any, **kwargs: Any) -> Any:
        _admit([_asyncpg_dbname(kwargs.get("database"), kwargs.get("dsn"))], "asyncpg")
        result = original_parse(*args, **kwargs)
        # Resolved parameters; asyncpg opens its socket only after this returns.
        _admit([getattr(result[1], "database", None)], "asyncpg")
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
    """Fail the run when any recorded target is an owner database.

    The connect-time refusal already failed the test that named it unless the
    test caught the exception; this keeps the session failed either way.
    """

    if owner_targets() and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Report every target and any owner target by the test that opened it."""

    terminalreporter.write_line(
        f"dbname audit: {len(_TARGETS)} targets: "
        + (", ".join(_collapsed_targets()) or "none")
    )
    if _UNAUDITED:
        terminalreporter.write_line(
            "dbname audit: unaudited connection classes: "
            + ", ".join(sorted(_UNAUDITED))
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

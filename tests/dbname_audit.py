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
``OwnerDatabaseConnectionRefused``, naming the target, the test, and the
server, before libpq or asyncpg opens a connection.

Identity is endpoint-aware. At configure time, before any fixture overrides
settings, the plugin captures the owner's configured server (host, port, and
socket directory, resolved through ``nexus.database.connection_kwargs``). An
endpoint is normalized so that every socket directory and every spelling of
this machine at one port is one local endpoint: ``localhost``, any loopback
or unspecified address (``127.0.0.2``, ``0.0.0.0``, ``::ffff:127.0.0.1``), and
any host name or address that resolves to one or to an address bound on this
machine (its host name, a LAN or tailnet address). An owner name is admitted
only on a cluster a private-cluster fixture registered with
``register_disposable_cluster``, is recorded as
``name@endpoint``, and is listed with the registrations in the session
report; on the owner's server, on any unregistered server, and wherever the
server is not known before connecting (a libpq service), it is refused. The
owner's own server can never be registered: registration refuses the owner's
endpoint in any spelling, then connects to the candidate and refuses it when
its ``pg_control_system()`` system identifier is the owner server's. A
target that merely differs from the current, mutable configuration is never
admitted for that reason. A ``dbname`` that only a libpq service
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
such holder exists in the modules the scan imports (psycopg2 with its extras
and pool, the SQLAlchemy psycopg2 dialect, ``nexus.database``,
``tests.conftest``, ``tests.pg_fixtures``), checked by a garbage-collector
reference scan that also searches the untracked tuples and dicts
``gc.get_referrers`` misses
(``tests/test_dbname_audit.py::test_no_preconfigure_holder_escapes_the_sweep``);
a holder in a module outside that set is not caught (an annotation that
merely names the class, such as a return annotation, cannot construct one).
The offline AST owner-target guard (``tests/test_owner_target_guard.py``)
covers the spellings in test source that such a path would need: an owner
literal in a connection call or a child process's argument list, and an
int-literal slot passed to a clone or dump helper (``slot_clone(1)``, which
``pg_dump``s ``save_01``) outside a ``requires_corpus`` module. A slot or name
computed at run time, or an owner read inside a helper module outside
``tests/``, is caught by neither.
"""

from __future__ import annotations

import functools
import ipaddress
import os
import re
import socket
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

    def __init__(self, target: str, driver: str, node: str, where: str = "") -> None:
        self.target = target
        self.driver = driver
        self.node = node
        self.where = where
        super().__init__(
            f"dbname audit: refused a {driver} connection to owner database "
            f"{target!r} from {node}"
            + (f" {where}" if where else "")
            + "; tests connect only to disposable databases, or to an owner "
            "name on a registered disposable cluster"
        )


class OwnerEndpointRegistrationRefused(RuntimeError):
    """A fixture tried to register the owner's server as a disposable cluster."""


# A server endpoint. Every Unix-socket directory and every spelling of this
# machine at one port is one endpoint, ``("local", "", port)``: they are
# equivalent spellings of the one server listening on that port here. Any
# other host is ``("tcp", host, port)``.
Endpoint = tuple[str, str, int]
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# libpq's compiled-in default port.
_DEFAULT_PORT = 5432

# The owner's configured server, captured once at configure time (before any
# fixture overrides settings or the PG* environment); ``None`` until the
# plugin configures.
_OWNER_ENDPOINTS: frozenset[Endpoint] | None = None
# The libpq keywords that reach the owner's ``postgres`` database, captured
# with the endpoints; registration reads the owner server's identity with them.
_OWNER_PARAMS: dict[str, Any] | None = None
# The owner server's ``pg_control_system()`` system identifier, read on the
# first registration.
_OWNER_IDENTITY: int | None = None
# Disposable clusters a private-cluster fixture registered: endpoint -> label.
_REGISTERED: dict[Endpoint, str] = {}
# Every registration, for the session report: (label, endpoint, node).
_REGISTRATIONS: list[tuple[str, str, str]] = []
# Owner-named databases admitted on a registered cluster:
# "name@endpoint" -> {"drivers": ..., "nodes": ...}.
_CLUSTER_TARGETS: dict[str, dict[str, set[str]]] = {}


def _is_this_machine_address(address: str, sockaddr: Any, family: int) -> bool:
    """Whether one resolved address reaches this machine.

    Loopback and unspecified addresses (IPv4-mapped ones included) do; so
    does any address a socket can bind here, which is every address assigned
    to one of this machine's interfaces.
    """

    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped
    if parsed.is_loopback or parsed.is_unspecified:
        return True
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind(sockaddr)
    except OSError:
        return False
    return True


@functools.lru_cache(maxsize=256)
def _is_this_machine(host: str) -> bool:
    """Whether a lower-cased TCP host names this machine.

    ``localhost`` does; any other host is resolved (a numeric address without
    a lookup) and names this machine when any address it resolves to does.
    A host that does not resolve names another machine.
    """

    if host in _LOOPBACK_HOSTS:
        return True
    try:
        resolved = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return False
    return any(
        _is_this_machine_address(str(sockaddr[0]), sockaddr, family)
        for family, _type, _proto, _name, sockaddr in resolved
    )


def normalize_endpoint(host: Any, port: Any) -> Endpoint:
    """Return the endpoint a libpq ``host`` and ``port`` spelling reaches.

    An empty host (libpq's default socket directory), any socket directory
    (``/...``, or ``@...`` for an abstract socket), and any host that names
    this machine (``localhost``, a loopback or unspecified address such as
    ``127.0.0.2``, ``0.0.0.0`` or ``::ffff:127.0.0.1``, or a name or address
    that resolves to one or to an address bound here) are one local endpoint
    per port. A trailing dot and IPv6 brackets are dropped. An empty port is
    libpq's default, 5432.
    """

    port_number = int(port) if port not in (None, "") else _DEFAULT_PORT
    text = str(host).strip() if host else ""
    if not text or text.startswith(("/", "@")):
        return ("local", "", port_number)
    name = text.lower().rstrip(".")
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    if _is_this_machine(name):
        return ("local", "", port_number)
    return ("tcp", name, port_number)


def endpoint_label(endpoint: Endpoint) -> str:
    """Spell an endpoint for a report: ``local:5432`` or ``host:port``."""

    kind, host, port = endpoint
    return f"local:{port}" if kind == "local" else f"{host}:{port}"


def _host_port_endpoints(hosts: Any, ports: Any) -> tuple[Endpoint, ...] | None:
    """Pair libpq's comma-separated host and port lists into endpoints.

    One port applies to every host; otherwise the lists pair up. A list libpq
    itself would reject, or a port that is not a number, yields ``None``.
    """

    host_list = str(hosts).split(",") if hosts else [""]
    port_list = str(ports).split(",") if ports not in (None, "") else [""]
    if len(port_list) not in (1, len(host_list)):
        return None
    try:
        return tuple(
            normalize_endpoint(
                host, port_list[index] if len(port_list) > 1 else port_list[0]
            )
            for index, host in enumerate(host_list)
        )
    except ValueError:
        return None


def _libpq_endpoints(params: dict[str, Any]) -> tuple[Endpoint, ...] | None:
    """Return the endpoints a libpq connection with ``params`` may reach.

    Read in libpq's order: the address is ``hostaddr`` (keyword, then
    ``PGHOSTADDR``), else ``host`` (keyword, then ``PGHOST``); the port is
    ``port``, then ``PGPORT``. A service (keyword or ``PGSERVICE``) may supply
    any of them from a file this plugin does not read, so the endpoint is
    unknown (``None``) before connecting.
    """

    if params.get("service") or os.environ.get("PGSERVICE"):
        return None
    hosts = (
        params.get("hostaddr")
        or os.environ.get("PGHOSTADDR")
        or params.get("host")
        or os.environ.get("PGHOST")
        or ""
    )
    ports = params.get("port") or os.environ.get("PGPORT") or ""
    return _host_port_endpoints(hosts, ports)


def _configured_owner_server() -> tuple[frozenset[Endpoint], dict[str, Any]]:
    """Resolve the owner's configured server through the runtime contract.

    ``nexus.database.connection_kwargs`` folds ``[api.database]`` and the PG*
    environment exactly as the runtime does; its host and port are the
    owner's server. Returns the endpoints and the keywords that reach its
    ``postgres`` database. An unresolvable spelling is a usage error.
    """

    from nexus.database import connection_kwargs

    params = connection_kwargs("postgres")
    endpoints = _host_port_endpoints(params.get("host"), params.get("port"))
    if not endpoints:
        raise pytest.UsageError(
            "dbname audit: cannot resolve the owner's configured server from "
            f"host={params.get('host')!r} port={params.get('port')!r}"
        )
    return frozenset(endpoints), dict(params)


def _system_identifier(params: dict[str, Any]) -> int:
    """Read a server's ``pg_control_system()`` system identifier.

    The identifier is fixed when a cluster is initialized, so two spellings
    that reach one server read the same value and two clusters differ.
    """

    import psycopg2

    conn = psycopg2.connect(**params)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT system_identifier FROM pg_control_system()")
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("dbname audit: pg_control_system() returned no row")
    return int(row[0])


def _owner_identity() -> int:
    """Return the owner server's system identifier, read once."""

    global _OWNER_IDENTITY
    if _OWNER_PARAMS is None:
        raise RuntimeError("dbname audit: the owner's server is not captured yet")
    if _OWNER_IDENTITY is None:
        _OWNER_IDENTITY = _system_identifier(_OWNER_PARAMS)
    return _OWNER_IDENTITY


def owner_endpoints() -> frozenset[Endpoint] | None:
    """Return the owner's endpoints captured at configure, or ``None`` before."""

    return _OWNER_ENDPOINTS


def register_disposable_cluster(
    host: Any, port: Any, *, label: str, user: str | None = None
) -> Any:
    """Admit owner-named databases on one private, disposable cluster.

    A fixture that starts its own PostgreSQL cluster (``two_clusters``) calls
    this once per cluster; the audit then admits a database with an owner's
    name (``save_04``) on that cluster's endpoint only, and names every
    registration in the session report. The endpoint is normalized, so the
    cluster's socket and TCP spellings are admitted alike. The owner's own
    server can never be registered: its endpoint in any spelling is refused
    before connecting, and then the candidate's ``postgres`` database is read
    as ``user`` and refused when its system identifier is the owner server's
    (or when it cannot be read, since the check cannot then be made). Each
    refusal raises ``OwnerEndpointRegistrationRefused``; so does registering
    one endpoint twice. Returns a callable that removes the registration,
    which the fixture calls when it stops the cluster.

    Without the plugin configured nothing is audited, so the registration
    only records itself.
    """

    import psycopg2

    endpoint = normalize_endpoint(host, port)
    if _OWNER_ENDPOINTS is not None and endpoint in _OWNER_ENDPOINTS:
        raise OwnerEndpointRegistrationRefused(
            f"dbname audit: refused to register {label!r} at "
            f"{endpoint_label(endpoint)}: that is the owner's server"
        )
    if endpoint in _REGISTERED:
        raise OwnerEndpointRegistrationRefused(
            f"dbname audit: {endpoint_label(endpoint)} is already registered "
            f"as {_REGISTERED[endpoint]!r}"
        )
    if _OWNER_ENDPOINTS is not None:
        candidate: dict[str, Any] = {
            "dbname": "postgres",
            "host": host,
            "port": port,
            "connect_timeout": 5,
        }
        if user is not None:
            candidate["user"] = user
        try:
            identity = _system_identifier(candidate)
        except psycopg2.Error as error:
            raise OwnerEndpointRegistrationRefused(
                f"dbname audit: refused to register {label!r} at "
                f"{endpoint_label(endpoint)}: cannot confirm it is not the "
                f"owner's server ({error})"
            ) from error
        if identity == _owner_identity():
            raise OwnerEndpointRegistrationRefused(
                f"dbname audit: refused to register {label!r} at "
                f"{endpoint_label(endpoint)}: its system identifier "
                f"{identity} is the owner's server's"
            )
    _REGISTERED[endpoint] = label
    _REGISTRATIONS.append((label, endpoint_label(endpoint), _current_node))

    def unregister() -> None:
        if _REGISTERED.get(endpoint) == label:
            del _REGISTERED[endpoint]

    return unregister


def registrations() -> tuple[tuple[str, str, str], ...]:
    """Return every registration as ``(label, endpoint, node)``."""

    return tuple(_REGISTRATIONS)


def cluster_targets() -> dict[str, frozenset[str]]:
    """Return each owner name admitted on a registered cluster, with drivers.

    Keys are ``name@endpoint``, for example ``save_04@local:54321``.
    """

    return {
        name: frozenset(entry["drivers"]) for name, entry in _CLUSTER_TARGETS.items()
    }


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


def _registered_cluster(endpoints: tuple[Endpoint, ...] | None) -> Endpoint | None:
    """Return the registered endpoint every one of ``endpoints`` is, if any.

    Admission needs a known endpoint list whose every entry is one registered
    cluster and none is the owner's server; anything else (an unknown
    endpoint, the owner's server, an unregistered server, or a host list that
    could fall through to another server) returns ``None``.
    """

    if not endpoints or len(set(endpoints)) != 1:
        return None
    (endpoint,) = set(endpoints)
    if _OWNER_ENDPOINTS is None or endpoint in _OWNER_ENDPOINTS:
        return None
    return endpoint if endpoint in _REGISTERED else None


def _refusal_site(endpoints: tuple[Endpoint, ...] | None) -> str:
    """Say where a refused owner name would have connected."""

    if not endpoints:
        return "(its server is not known before connecting)"
    labels = ", ".join(endpoint_label(endpoint) for endpoint in endpoints)
    if _OWNER_ENDPOINTS is not None and any(
        endpoint in _OWNER_ENDPOINTS for endpoint in endpoints
    ):
        return f"on the owner's server ({labels})"
    return f"on an unregistered server ({labels})"


def _record_cluster(dbname: str, endpoint: Endpoint, driver: str) -> None:
    key = f"{dbname}@{endpoint_label(endpoint)}"
    entry = _CLUSTER_TARGETS.setdefault(key, {"drivers": set(), "nodes": set()})
    entry["drivers"].add(driver)
    entry["nodes"].add(_current_node)


def _admit(
    names: list[str | None],
    driver: str,
    endpoints: tuple[Endpoint, ...] | None,
) -> None:
    """Record every name, then refuse the first unadmitted owner target.

    An owner name is admitted only on a registered disposable cluster
    (``register_disposable_cluster``) and recorded as ``name@endpoint``;
    anywhere else, including the owner's server and any server the audit
    cannot resolve before connecting, it is recorded and refused.
    """

    cluster = _registered_cluster(endpoints)
    for name in names:
        if name and is_owner_target(name) and cluster is not None:
            _record_cluster(name, cluster, driver)
        else:
            _record(name, driver)
    if cluster is not None:
        return
    for name in names:
        if name and is_owner_target(name):
            raise OwnerDatabaseConnectionRefused(
                name, driver, _current_node, _refusal_site(endpoints)
            )


def _admit_open(conn: Any, driver: str) -> None:
    """Record an open psycopg2 connection's database; close and refuse owners.

    The endpoint is libpq's resolved host (a socket directory for a socket
    connection) and port for the open connection.
    """

    name = _connected_dbname(conn)
    info = getattr(conn, "info", None)
    try:
        endpoints: tuple[Endpoint, ...] | None = (
            normalize_endpoint(
                getattr(info, "host", None), getattr(info, "port", None)
            ),
        )
    except ValueError:
        endpoints = None
    try:
        _admit([name], driver, endpoints)
    except OwnerDatabaseConnectionRefused:
        conn.close()
        raise


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


def _dsn_endpoints(dsn: Any) -> tuple[Endpoint, ...] | None:
    """Return the endpoints a libpq DSN string or URL may reach, if known."""

    import psycopg2
    from psycopg2.extensions import parse_dsn

    if dsn is None:
        return None
    try:
        parsed = parse_dsn(str(dsn))
    except psycopg2.ProgrammingError:
        return None
    return _libpq_endpoints(parsed)


def _asyncpg_endpoints(addresses: Any) -> tuple[Endpoint, ...] | None:
    """Return the endpoints asyncpg resolved: socket paths or host and port."""

    endpoints: list[Endpoint] = []
    try:
        for address in addresses or ():
            if isinstance(address, str):
                # A Unix socket path, ``<directory>/.s.PGSQL.<port>``.
                endpoints.append(
                    normalize_endpoint(
                        address.rsplit("/", 1)[0] or "/", address.rsplit(".", 1)[1]
                    )
                )
            else:
                host, port = address[0], address[1]
                endpoints.append(normalize_endpoint(host, port))
    except (IndexError, TypeError, ValueError):
        return None
    return tuple(endpoints) or None


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
        _admit([_dsn_dbname(dsn)], "psycopg2", _dsn_endpoints(dsn))
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
            _admit([_dsn_dbname(dsn)], label, _dsn_endpoints(dsn))
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
        requested = _asyncpg_dbname(kwargs.get("database"), kwargs.get("dsn"))
        try:
            result = original_parse(*args, **kwargs)
        except Exception:
            # Unparsed arguments name no endpoint: an owner name is refused.
            _admit([requested], "asyncpg", None)
            raise
        # Resolved addresses and parameters; asyncpg opens its socket only
        # after this returns.
        _admit(
            [requested, getattr(result[1], "database", None)],
            "asyncpg",
            _asyncpg_endpoints(result[0]),
        )
        return result

    connect_utils._parse_connect_arguments = audited_parse

    def restore() -> None:
        connect_utils._parse_connect_arguments = original_parse

    _restore.append(restore)


def pytest_configure(config: pytest.Config) -> None:
    """Install the driver hooks for the whole session."""

    global _OWNER_ENDPOINTS, _OWNER_PARAMS
    if _restore:
        return
    # Captured before any fixture runs, so no fixture's settings or PG*
    # override can move the server the audit treats as the owner's.
    _OWNER_ENDPOINTS, _OWNER_PARAMS = _configured_owner_server()
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
    if _OWNER_ENDPOINTS is not None:
        terminalreporter.write_line(
            "dbname audit: owner server: "
            + ", ".join(sorted(endpoint_label(item) for item in _OWNER_ENDPOINTS))
        )
    if _REGISTRATIONS:
        terminalreporter.write_line(
            "dbname audit: registered disposable clusters: "
            + "; ".join(
                f"{label} at {endpoint} from {node}"
                for label, endpoint, node in _REGISTRATIONS
            )
        )
        terminalreporter.write_line(
            "dbname audit: owner names admitted on registered clusters: "
            + (
                ", ".join(
                    f"{name} ({', '.join(sorted(entry['drivers']))})"
                    for name, entry in sorted(_CLUSTER_TARGETS.items())
                )
                or "none"
            )
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

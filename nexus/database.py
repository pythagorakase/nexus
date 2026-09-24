"""One PostgreSQL target and session policy for every connection technology."""

from __future__ import annotations

import getpass
import logging
import os
import re
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote
from weakref import WeakSet

from sqlalchemy.engine import URL, Engine, make_url

from nexus.config import load_settings
from nexus.util.secret_manager import get_secret


class AmbiguousCommit(RuntimeError):
    """A disconnected commit has an unknown outcome; never replay (docs/database.md)."""


def is_connection_failure(exc: BaseException) -> bool:
    """Recognize connection loss even through driver or domain exception wrappers."""
    import psycopg2

    pending = [exc]
    seen: set[int] = set()
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(
            error, (AmbiguousCommit, psycopg2.OperationalError, psycopg2.InterfaceError)
        ):
            return True
        for inner in (error.__cause__, error.__context__, getattr(error, "orig", None)):
            if isinstance(inner, BaseException):
                pending.append(inner)
    return False


def commit_transaction(conn: Any) -> None:
    """Commit once and make connection loss a terminal, named outcome."""
    import psycopg2

    dbname = conn.info.dbname
    try:
        conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
        conn.close()
        raise AmbiguousCommit(f"Ambiguous commit for database {dbname}: {exc}") from exc


@contextmanager
def transaction(conn: Any) -> Iterator[Any]:
    """Manage a direct transaction without masking or replaying commit failure."""
    try:
        yield conn
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            conn.close()
        raise
    else:
        commit_transaction(conn)


def application_name(role: str) -> str:
    """Label a backend with adapter role and gateway port, or process ID."""
    config = load_settings().api.database
    suffix = os.environ.get("NEXUS_GATEWAY_PORT") or str(os.getpid())
    return f"{config.application_name_prefix}:{role}:{suffix}"


_engines: dict[str, WeakSet] = {}
_engines_lock = threading.RLock()


def create_slot_engine(
    dbname_or_url: str | URL | None = None, **overrides: Any
) -> Engine:
    """Create a registered SQLAlchemy engine with checkout and session policy.

    ``None`` (or an empty string) selects the active slot, exactly as the
    retired ``resolved_database_url(None)`` did for script callers.
    """
    from sqlalchemy import create_engine

    config = load_settings().api.database
    if not dbname_or_url:
        params = connection_kwargs(None)
    elif isinstance(dbname_or_url, URL) or "://" in dbname_or_url:
        params = url_connection_kwargs(dbname_or_url)
    else:
        params = connection_kwargs(dbname_or_url)
    params.update(overrides.pop("connect_args", {}))
    params["options"] = _session_options(params.get("options"), config.session_timezone)
    params["application_name"] = application_name("sqlalchemy")
    options = {
        "pool_size": config.pool_min_connections,
        "max_overflow": config.pool_max_connections - config.pool_min_connections,
        **overrides,
        "pool_pre_ping": True,
    }
    with _engines_lock:
        engine = create_engine(
            URL.create("postgresql+psycopg2", database=params["dbname"]),
            connect_args=params,
            **options,
        )
        _engines.setdefault(params["dbname"], WeakSet()).add(engine)
        return engine


def dispose_database_engines(dbname: str | None = None) -> None:
    """Dispose registered engines; keep live engines registered for later resets."""
    with _engines_lock:
        names = [dbname] if dbname is not None else list(_engines)
        for name in names:
            for engine in list(_engines.get(name, ())):
                engine.dispose()


def connection_kwargs(
    dbname: str | None = None,
    *,
    host: str | None = None,
    port: int | str | None = None,
    user: str | None = None,
    password: str | None = None,
    session_timezone: str | None = None,
    options: str | None = None,
) -> dict[str, Any]:
    """Resolve explicit arguments, TOML, then libpq environment and defaults.

    An explicit database also supports maintenance databases; gameplay entry
    points retain their slot validation. Empty TOML fields defer to libpq.
    Passwords are read from the platform secret store when an account is set.
    """
    from nexus.api.slot_utils import require_slot_dbname
    from nexus.config.settings_models import APIDatabaseSettings

    if "PGHOSTADDR" in os.environ:
        raise ValueError("PGHOSTADDR is unsupported; use host to select the server")
    settings = load_settings()
    if settings.api is None:
        raise RuntimeError("nexus.toml requires [api.database]")
    config = settings.api.database
    timezone = session_timezone or config.session_timezone
    APIDatabaseSettings.validate_session_timezone(timezone)
    resolved_port = int(
        port
        if port is not None
        else config.port
        or os.environ.get("PGPORT")
        or socket.getservbyname("postgresql", "tcp")
    )
    if not 1 <= resolved_port <= 65535:
        raise ValueError("PostgreSQL port must be between 1 and 65535")
    params = {
        "dbname": dbname if dbname is not None else require_slot_dbname(),
        "host": (
            host if host is not None else config.host or os.environ.get("PGHOST", "")
        ),
        "port": resolved_port,
        "user": (
            user
            if user is not None
            else config.user or os.environ.get("PGUSER") or getpass.getuser()
        ),
        "connect_timeout": int(
            os.environ.get("PGCONNECT_TIMEOUT") or config.connect_timeout_seconds
        ),
        "options": _session_options(options, timezone),
        "application_name": application_name("sync"),
    }
    if password is None:
        password = (
            get_secret(config.password_secret)
            if config.password_secret
            else os.environ.get("PGPASSWORD")
        )
    if password is not None:
        params["password"] = password
    return params


def maintenance_connection(
    dbname: str | None = None,
    *,
    db_url: str | None = None,
    write_locked_slot: bool = False,
    operation: str,
) -> Any:
    """Open a maintenance session without changing the database's lock policy."""
    import psycopg2

    params = url_connection_kwargs(db_url) if db_url else connection_kwargs(dbname)
    conn = psycopg2.connect(**params)
    if write_locked_slot:
        try:
            # SET must precede the first work transaction, including FOR UPDATE.
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SET default_transaction_read_only = off")
            conn.autocommit = False
            logging.getLogger(__name__).warning(
                "%s: session write override for %s (--write-locked-slot)",
                params["dbname"],
                operation,
            )
        except BaseException:
            conn.close()
            raise
    return conn


def _option_settings(options: str) -> list[tuple[str, str]]:
    """Parse PostgreSQL -c/-- settings, honoring backslash-escaped whitespace."""
    if re.search(r"(?<!\\)(?:\\\\)*\\$", options):
        raise ValueError("PostgreSQL options end with an incomplete escape")
    tokens = iter(re.findall(r"(?:\\.|[^\s\\])+", options))
    settings = []
    for token in tokens:
        if token == "-c":
            assignment = next(tokens, "")
        elif token.startswith("-c"):
            assignment = token[2:]
        elif token.startswith("--"):
            assignment = token[2:]
        else:
            raise ValueError("Unsupported PostgreSQL option; use -c name=value")
        assignment = re.sub(r"\\(.)", r"\1", assignment)
        name, separator, value = assignment.partition("=")
        if name.lower() == "hostaddr":
            raise ValueError("hostaddr is unsupported; use host to select the server")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
            raise ValueError("Unsupported PostgreSQL option; use -c name=value")
        settings.append((name, value))
    return settings


def _session_options(options: str | None, timezone: str) -> str:
    """Preserve explicit or ambient settings and install the timezone once."""
    base = options if options is not None else os.environ.get("PGOPTIONS", "")
    settings = [
        (name, value)
        for name, value in _option_settings(base)
        if name.lower() != "timezone"
    ]
    settings.append(("TimeZone", timezone))
    return " ".join(
        "-c " + re.sub(r"([\s\\])", r"\\\1", f"{name}={value}")
        for name, value in settings
    )


def _render_libpq_url(url: URL) -> str:
    """Preserve SQLAlchemy component escaping with libpq-safe query encoding."""
    base = url.set(query={}).render_as_string(hide_password=False)
    query = "&".join(
        f"{quote(key, safe='')}={quote(value, safe='')}"
        for key, values in sorted(url.normalized_query.items())
        for value in values
    )
    return f"{base}?{query}" if query else base


def database_url(dbname: str | None = None, **overrides: Any) -> str:
    """Build a URL consumed raw by libpq, psycopg2, and SQLAlchemy.

    The URL also round-trips through url_connection_kwargs(). Asyncpg consumers
    must use asyncpg_kwargs(): its DSN parser cannot express the empty-host
    default with a single port.
    """
    params = connection_kwargs(dbname, **overrides)
    host = params["host"]
    query = {
        "connect_timeout": str(params["connect_timeout"]),
        "options": params["options"],
        "application_name": params["application_name"],
    }
    if host.startswith("/"):
        query["host"] = host
        host = None
    url = URL.create(
        "postgresql",
        username=params["user"],
        password=params.get("password"),
        host=host or None,
        port=params["port"] if host else None,
        database=params["dbname"],
        query={**query, **({"port": str(params["port"])} if not host else {})},
    )
    return _render_libpq_url(url)


def url_connection_kwargs(db_url: str | URL | None) -> dict[str, Any]:
    """Decode a URL and apply the common session policy to direct clients."""
    if not db_url:
        return connection_kwargs()
    url = make_url(db_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("A PostgreSQL database URL is required")
    if any(key.lower() == "hostaddr" for key in url.query):
        raise ValueError("hostaddr is unsupported; use host to select the server")
    params = connection_kwargs(
        url.query.get("dbname", url.database),
        host=url.query.get("host", url.host),
        port=url.query.get("port", url.port),
        user=url.query.get("user", url.username),
        password=url.query.get("password", url.password),
        options=url.query.get("options"),
    )
    # Preserve TLS and other libpq transport options from explicit URLs.
    for key, value in url.query.items():
        if key not in {"host", "port", "user", "password", "dbname", "options"}:
            params[key] = int(value) if key == "connect_timeout" else value
    return params


def asyncpg_kwargs(dbname: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Adapt the contract to asyncpg without passing libpq-only options."""
    params = connection_kwargs(dbname, **overrides)
    params["database"] = params.pop("dbname")
    params["timeout"] = params.pop("connect_timeout")
    params["server_settings"] = dict(_option_settings(params.pop("options")))
    params.pop("application_name")
    params["server_settings"].setdefault(
        "application_name", application_name("asyncpg")
    )
    if not params["host"]:
        params.pop("host")
    return params


def connection_target(params: dict[str, Any]) -> dict[str, Any]:
    """Return only non-secret target fields for preflight and diagnostics."""
    return {key: params[key] for key in ("host", "port", "user", "dbname")}


def verify_database_url(db_url: str, *, dbname: str | None = None) -> str:
    """Reject a foreign schema target before opening a connection or doing DDL.

    The caller's explicitly selected database takes precedence over the active
    slot, just as it does for pooled clients. Server identity always comes from
    the runtime contract. Return a URL with the runtime session policy applied.
    """
    actual = url_connection_kwargs(db_url)
    expected = connection_kwargs(dbname or actual["dbname"])
    if connection_target(actual) != connection_target(expected):
        raise ValueError(
            f"PostgreSQL target mismatch: URL {connection_target(actual)!r}; "
            f"runtime {connection_target(expected)!r}"
        )
    return resolved_database_url(db_url)


def subprocess_env() -> dict[str, str]:
    """Apply the same target/session policy to PostgreSQL command-line tools."""
    params = connection_kwargs("postgres")
    params["application_name"] = application_name("subprocess")
    env = os.environ.copy()
    for key, name in (
        ("host", "PGHOST"),
        ("port", "PGPORT"),
        ("user", "PGUSER"),
        ("password", "PGPASSWORD"),
        ("options", "PGOPTIONS"),
        ("connect_timeout", "PGCONNECT_TIMEOUT"),
        ("application_name", "PGAPPNAME"),
    ):
        if key in params:
            env[name] = str(params[key])
    return env


def resolved_database_url(db_url: str | URL | None = None) -> str:
    """Apply the contract to an explicitly supplied URL or the active slot."""
    if not db_url:
        return database_url()
    params = url_connection_kwargs(db_url)
    normalized = make_url(
        database_url(
            params["dbname"],
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params.get("password"),
        )
    )
    query = {**make_url(db_url).query, **normalized.query}
    query["connect_timeout"] = str(params["connect_timeout"])
    query["options"] = params["options"]
    return _render_libpq_url(normalized.set(query=query))


def main() -> None:
    """Run a PostgreSQL CLI with the configured environment, keeping keys off argv."""
    import subprocess
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m nexus.database <PostgreSQL tool> [args]")
    raise SystemExit(subprocess.call(sys.argv[1:], env=subprocess_env()))


if __name__ == "__main__":
    main()

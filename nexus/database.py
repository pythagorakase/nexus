"""One PostgreSQL target and session policy for every connection technology."""

from __future__ import annotations

import getpass
import os
import re
import socket
from typing import Any

from sqlalchemy.engine import URL, make_url

from nexus.config import load_settings
from nexus.util.secret_manager import get_secret


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


def _session_options(options: str | None, timezone: str) -> str:
    """Replace existing timezone options so repeated normalization is stable."""
    remaining = re.sub(
        r"(?:^|\s)(?:-c\s*timezone=|--timezone=)\S+",
        "",
        options or "",
        flags=re.IGNORECASE,
    ).strip()
    return f"{remaining} -c TimeZone={timezone}".lstrip()


def database_url(dbname: str | None = None, **overrides: Any) -> str:
    """Build an escaped SQLAlchemy/libpq URL including the session policy."""
    params = connection_kwargs(dbname, **overrides)
    host = params["host"]
    query = {
        "connect_timeout": str(params["connect_timeout"]),
        "options": params["options"],
    }
    if host.startswith("/"):
        query["host"] = host
        host = None
    return URL.create(
        "postgresql",
        username=params["user"],
        password=params.get("password"),
        host=host or None,
        port=params["port"] if host else None,
        database=params["dbname"],
        query={**query, **({"port": str(params["port"])} if not host else {})},
    ).render_as_string(hide_password=False)


def url_connection_kwargs(db_url: str | URL | None) -> dict[str, Any]:
    """Decode a URL and apply the common session policy to direct clients."""
    if not db_url:
        return connection_kwargs()
    url = make_url(db_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("A PostgreSQL database URL is required")
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
    params["server_settings"] = {"TimeZone": params.pop("options").split("=", 1)[1]}
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
    env = os.environ.copy()
    for key, name in (
        ("host", "PGHOST"),
        ("port", "PGPORT"),
        ("user", "PGUSER"),
        ("password", "PGPASSWORD"),
        ("options", "PGOPTIONS"),
        ("connect_timeout", "PGCONNECT_TIMEOUT"),
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
    return normalized.set(query=query).render_as_string(hide_password=False)


def main() -> None:
    """Run a PostgreSQL CLI with the configured environment, keeping keys off argv."""
    import subprocess
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m nexus.database <PostgreSQL tool> [args]")
    raise SystemExit(subprocess.call(sys.argv[1:], env=subprocess_env()))


if __name__ == "__main__":
    main()

"""Gateway-side runtime status endpoint (issue #396).

The gateway IS the runtime endpoint: ``GET /runtime/status`` aggregates the
health of everything a client needs — the gateway itself, the active slot's
database, and the mock model server when enabled — plus the runtime profile
and version. ``nexus status`` renders this beside supervisor-side process
state; remote clients hit it directly.

Registered in ``nexus.api.narrative`` BEFORE ``mount_ui(app)`` — the static
SPA mount registers a catch-all route and must come last.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Dict

import requests
from fastapi import FastAPI

from nexus.config import load_settings
from nexus.runtime.contract import (
    NEXUS_AUTH_HEADER,
    RUNTIME_CONFIG_ENV,
    RUNTIME_STATUS_PATH,
)


def _database_status() -> Dict[str, Any]:
    """SELECT 1 against the active slot's database."""
    import psycopg2

    from nexus.api.db_pool import get_connect_timeout_seconds
    from nexus.api.slot_utils import get_active_slot, require_slot_dbname

    try:
        slot = get_active_slot()
        dbname = require_slot_dbname(slot=slot)
    except (RuntimeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        conn = psycopg2.connect(
            host="localhost",
            dbname=dbname,
            user="pythagor",
            connect_timeout=get_connect_timeout_seconds(),
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return {"ok": True, "slot": slot, "dbname": dbname}
    except psycopg2.Error as exc:
        return {"ok": False, "slot": slot, "dbname": dbname, "error": str(exc)}


def build_runtime_status() -> Dict[str, Any]:
    """Aggregate runtime health (sync; called from the async endpoint)."""
    config_path = os.environ.get(RUNTIME_CONFIG_ENV, "nexus.toml")
    settings = load_settings(config_path)
    runtime = settings.runtime

    try:
        nexus_version = version("nexus")
    except PackageNotFoundError:
        nexus_version = "unknown"

    database = _database_status()
    status: Dict[str, Any] = {
        "profile": runtime.profile if runtime else None,
        "version": nexus_version,
        "slot": database.get("slot"),
        "database": database,
        # The gateway answered this request, so it is healthy by construction.
        "services": {"gateway": {"ok": True}},
        "auth": {"header": NEXUS_AUTH_HEADER, "enforced": False},
    }

    if runtime and runtime.profile == "local":
        gateway = runtime.services.get("gateway")
        if gateway:
            status["services"]["gateway"]["port"] = gateway.port
        mock = runtime.services.get("mock_openai")
        test_provider = settings.global_.model.api_models.get("test")
        mock_enabled = (
            mock is not None
            and mock.enabled != "never"
            and not (
                mock.enabled == "auto" and not (test_provider and test_provider.models)
            )
        )
        if mock_enabled:
            url = f"http://{mock.host}:{mock.port}{mock.health_path}"
            try:
                ok = (
                    requests.get(
                        url, timeout=runtime.health.timeout_seconds
                    ).status_code
                    == 200
                )
            except requests.RequestException:
                ok = False
            status["services"]["mock_openai"] = {"ok": ok, "port": mock.port}

    status["ok"] = database["ok"] and all(
        service.get("ok", False) for service in status["services"].values()
    )
    return status


def register_runtime_status(app: FastAPI) -> None:
    """Attach GET /runtime/status to the gateway app."""

    @app.get(RUNTIME_STATUS_PATH)
    async def runtime_status() -> Dict[str, Any]:
        return build_runtime_status()

"""Exercise the real slot-reset route on lane 8017 against a disposable database."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[3]
DB = "qa640_804_endpoint"
CONFIG = ROOT / "temp/804-preflight/endpoint.toml"


def install_guards() -> None:
    """Redirect the one admitted slot before importing endpoint consumers."""
    from nexus.api import slot_utils
    import nexus.database as database

    slot_utils.VALID_DBNAMES = {DB}
    slot_utils.VALID_SLOTS = {4}

    def slot_database(slot: int) -> str:
        if slot != 4:
            raise RuntimeError(f"Endpoint proof refuses slot {slot}")
        return DB

    slot_utils.slot_dbname = slot_database
    original = database.connection_kwargs

    def guarded(dbname: str | None = None, **kwargs: Any) -> dict[str, Any]:
        params = original(dbname, **kwargs)
        if params["dbname"] not in {DB, "postgres", "NEXUS_template"}:
            raise RuntimeError(f"Endpoint proof refuses database {params['dbname']}")
        if params["dbname"] == "NEXUS_template":
            params["options"] += " -c default_transaction_read_only=on"
        return params

    database.connection_kwargs = guarded


def main() -> None:
    """Prepare, launch, or clean up the isolated endpoint proof."""
    assert os.environ["NEXUS_GATEWAY_PORT"] == "8017"
    assert os.environ["NEXUS_API_URL"] == "http://127.0.0.1:8017"
    install_guards()
    from nexus.api.db_pool import dispose_database, get_connection
    from nexus.database import connection_kwargs, create_slot_engine

    mode = sys.argv[1]
    if mode == "prepare":
        source = (ROOT / "nexus.toml").read_text()
        original = 'command = ["{python}", "-m", "uvicorn", "nexus.api.narrative:app", "--host", "{host}", "--port", "{port}"]'
        source = source.replace(
            original,
            'command = ["{python}", "docs/qa/804-connection-preflight/endpoint_probe.py", "gateway"]',
        )
        source = source.replace('enabled = "auto"', 'enabled = "never"')
        CONFIG.write_text(source)
        from scripts.new_story_setup import initialize_slot_database

        initialize_slot_database(DB)
        dispose_database(DB)
        print(json.dumps({"prepared": DB, "config": str(CONFIG)}))
    elif mode == "up":
        from nexus.runtime.supervisor import Supervisor

        supervisor = Supervisor.from_config(CONFIG)
        print(json.dumps(supervisor.up(slot=4), default=str))
    elif mode == "gateway":
        import uvicorn
        from fastapi import FastAPI
        from sqlalchemy import text
        from nexus.api.setup_endpoints import router

        # Actual route + handler + initialization code, without unrelated startup jobs.
        app = FastAPI()
        app.include_router(router)
        engine = create_slot_engine(DB)

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/proof")
        def proof() -> dict[str, Any]:
            query = "SELECT current_database(), oid FROM pg_database WHERE datname = current_database()"
            with get_connection(DB) as conn, conn.cursor() as cur:
                cur.execute(query)
                dbname, pool_oid = cur.fetchone()
                pid = conn.get_backend_pid()
            with engine.connect() as conn:
                _, engine_oid = conn.execute(text(query)).one()
            return {
                "database": dbname,
                "pool_oid": pool_oid,
                "engine_oid": engine_oid,
                "pool_pid": pid,
            }

        uvicorn.run(app, host="127.0.0.1", port=8017)
    elif mode == "cleanup":
        dispose_database(DB)
        conn = psycopg2.connect(**connection_kwargs("postgres"))
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(DB)))
        finally:
            conn.close()
        print(json.dumps({"dropped": DB}))
    else:
        raise ValueError(mode)


if __name__ == "__main__":
    main()

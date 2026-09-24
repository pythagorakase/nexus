"""Bounded work-order 909 launcher and evidence collector; no production edits."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from nexus.api.db_pool import dispose_database

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/909-long-absence-probe/live"
DB = "qa640_909_long_absence"


def save(name: str, value: Any) -> None:
    """Persist exact evidence in the worktree."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def query(dbname: str, statement: str) -> list[dict[str, Any]]:
    """Audit the database identity before each read-only evidence query."""
    from nexus.database import connection_kwargs

    with psycopg2.connect(
        **connection_kwargs(dbname, options="-c default_transaction_read_only=on")
    ) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database()")
            identity = dict(cur.fetchone())
            assert identity["current_database"] == dbname
            cur.execute(statement)
            rows = [dict(row) for row in cur.fetchall()]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "sql.jsonl").open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "database": dbname,
                    "identity": identity,
                    "sql": statement,
                    "rows": rows,
                },
                default=str,
            )
            + "\n"
        )
    return rows


def install_guards() -> None:
    """Admit only the clone for gameplay and read-only maintenance access."""
    from nexus.api import slot_utils
    import nexus.database as database

    slot_utils.VALID_DBNAMES = {DB}
    slot_utils.VALID_SLOTS = {4}

    def clone_slot(slot: int) -> str:
        if slot != 4:
            raise RuntimeError(f"Probe refused slot {slot}")
        return DB

    slot_utils.slot_dbname = clone_slot
    original = database.connection_kwargs

    def guarded(dbname: str | None = None, **kwargs: Any) -> dict[str, Any]:
        params = original(dbname, **kwargs)
        if params["dbname"] not in {DB, "postgres"}:
            raise RuntimeError(f"Probe refused database {params['dbname']!r}")
        if params["dbname"] == "postgres":
            params["options"] += " -c default_transaction_read_only=on"
        return params

    database.connection_kwargs = guarded
    raw_connect = psycopg2.connect

    def checked_connect(*args: Any, **kwargs: Any) -> Any:
        conn = raw_connect(*args, **kwargs)
        actual = conn.info.dbname
        if actual not in {DB, "postgres"}:
            conn.close()
            raise RuntimeError(f"Probe refused actual connection to {actual}")
        if actual == "postgres":
            conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == actual
        conn.rollback()
        return conn

    psycopg2.connect = checked_connect


def install_capture() -> None:
    """Capture actual rendered requests and bound every paid seat attempt."""
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.jobs import gate
    from nexus.telemetry.usage import current_usage_context

    original = LogonUtility._attach_prompt_window_guard

    def capture(
        self: Any, provider: Any, prompt: str, *, seat: str, window: int | None
    ) -> None:
        original(self, provider, prompt, seat=seat, window=window)
        provider.structured_output_retries = 0
        provider.client.max_retries = 0
        run = current_usage_context()[2]
        save(
            f"{run}-{seat}-prompt.json",
            {
                "run": run,
                "seat": seat,
                "model": provider.model,
                "prompt": prompt,
                "system_prompt": provider.system_prompt,
                "payload": self._window_payload,
            },
        )

    LogonUtility._attach_prompt_window_guard = capture
    original_gate = gate.before_provider_call
    lock = threading.Lock()

    def bounded_call() -> None:
        caller = inspect.currentframe().f_back
        provider = caller.f_locals.get("self")
        seat = getattr(provider, "usage_seat", None)
        if seat not in {"skald_writer", "gaia"}:
            raise RuntimeError(
                f"909 authorization excludes auxiliary provider call: {seat}"
            )
        original_gate()
        with lock:
            path = OUT / "paid-attempts.jsonl"
            prior = (
                [json.loads(line) for line in path.read_text().splitlines()]
                if path.exists()
                else []
            )
            if sum(row["seat"] == seat for row in prior) >= 8:
                raise RuntimeError("909 paid-turn cap reached")
            identity = query(
                DB, "SELECT current_database(), count(*), max(id) FROM narrative_chunks"
            )
            with path.open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "seat": seat,
                            "run": current_usage_context()[2],
                            "model": provider.model,
                            "identity": identity,
                        },
                        default=str,
                    )
                    + "\n"
                )

    gate.before_provider_call = bounded_call


def main() -> None:
    """Run the fixed clone, supervisor, or gateway stage of the order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["clone", "up", "gateway"])
    args = parser.parse_args()
    assert Path(__import__("nexus").__file__).is_relative_to(ROOT)
    if args.stage == "clone":
        dispose_database(DB)
        from nexus.database import connection_kwargs
        from scripts.new_story_setup import _postgres_tools
        from psycopg2.extensions import make_dsn

        save(
            "source-before.json",
            query(
                "save_04",
                "SELECT current_database(), count(*), max(id) FROM narrative_chunks",
            ),
        )
        admin = psycopg2.connect(**connection_kwargs("postgres"))
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "postgres"
            cur.execute(f"CREATE DATABASE {DB} TEMPLATE template0")
        admin.close()
        binaries = _postgres_tools("pg_dump", "pg_restore")
        dump = ROOT / ".nexus/909-source.dump"
        dump.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                binaries["pg_dump"],
                "--format=custom",
                "--file",
                str(dump),
                "--dbname",
                make_dsn(
                    **connection_kwargs(
                        "save_04", options="-c default_transaction_read_only=on"
                    )
                ),
            ],
            check=True,
        )
        subprocess.run(
            [
                binaries["pg_restore"],
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                make_dsn(**connection_kwargs(DB)),
                str(dump),
            ],
            check=True,
        )
        print(
            query(
                DB, "SELECT current_database(), count(*), max(id) FROM narrative_chunks"
            )
        )
        dispose_database(DB)
        return
    os.environ["NEXUS_SLOT"] = "4"
    os.environ["NEXUS_GATEWAY_PORT"] = "8018"
    os.environ["NEXUS_API_URL"] = "http://127.0.0.1:8018"
    install_guards()
    print(
        query(DB, "SELECT current_database(), count(*), max(id) FROM narrative_chunks"),
        flush=True,
    )
    if args.stage == "up":
        from nexus.runtime.supervisor import Supervisor

        supervisor = Supervisor.from_config()
        for name, service in supervisor.runtime.services.items():
            if name != "gateway":
                service.enabled = "never"
        supervisor.runtime.services["gateway"].command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "gateway",
        ]
        print(json.dumps(supervisor.up(slot=4), default=str))
    else:
        install_capture()
        import uvicorn

        uvicorn.run("nexus.api.narrative:app", host="127.0.0.1", port=8018)


if __name__ == "__main__":
    main()

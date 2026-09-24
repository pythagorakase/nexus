"""Replay #909 turn 1A through TEST rendering against a disposable frontier clone."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from nexus.api.db_pool import dispose_database

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.api import slot_utils
from nexus.config import load_settings_as_dict
from nexus.config.story_model import StorySettings
from nexus.database import connection_kwargs
from nexus.memory import ContextMemoryManager
from scripts.new_story_setup import _postgres_tools

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/911-passage-limit"
SOURCE = ROOT / (
    "docs/qa/909-long-absence-probe/live/"
    "79b4e65e-39ab-4e90-a28d-86756688ac02-skald_writer-prompt.json"
)


def read_rows(dbname: str, statement: str) -> list[Any]:
    """Read evidence in an explicitly read-only transaction."""
    with psycopg2.connect(
        **connection_kwargs(dbname, options="-c default_transaction_read_only=on")
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == dbname
            cursor.execute(statement)
            return cursor.fetchall()


def main() -> None:
    """Clone without migrations, verify source text, render both caps, and clean up."""
    import nexus

    assert Path(nexus.__file__).is_relative_to(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    dbname = "qa640_911_" + uuid4().hex[:12]
    archive = OUT / "frontier.dump"
    tools = _postgres_tools("pg_dump", "pg_restore")
    frontier_sql = "SELECT count(*), max(id) FROM narrative_chunks"
    evidence: dict[str, Any] = {
        "method": "Recorded 1A assembly replay; real TEST renderer; no generation or ranking intervention",
        "database": dbname,
        "frontier_sql": frontier_sql,
        "source_before": read_rows("save_04", frontier_sql),
        "source_payload": str(SOURCE.relative_to(ROOT)),
    }
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    admin.autocommit = True
    created = False
    original_dbnames = slot_utils.VALID_DBNAMES
    try:
        dispose_database(dbname)
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(dbname)
                )
            )
        created = True
        subprocess.run(
            [
                tools["pg_dump"],
                "--format=custom",
                "--file",
                str(archive),
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
                tools["pg_restore"],
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                make_dsn(**connection_kwargs(dbname)),
                str(archive),
            ],
            check=True,
        )
        dispose_database(dbname)
        evidence["clone_frontier"] = read_rows(dbname, frontier_sql)
        assert evidence["clone_frontier"] == evidence["source_before"] == [(46, 49)]
        payload = json.loads(SOURCE.read_text())["payload"]
        # Prompt capture serializes PostgreSQL Decimal values as JSON strings.
        for relationship in payload["entity_data"]["relationships"]:
            relationship["valence_current"] = Decimal(relationship["valence_current"])
        evidence["replay_type_restoration"] = (
            "Relationship valence strings restored to Decimal"
        )
        text_sql = (
            "SELECT id, raw_text, storyteller_text FROM narrative_chunks ORDER BY id"
        )
        texts = {row[0]: row[1:] for row in read_rows(dbname, text_sql)}
        evidence["passage_sql"] = text_sql
        for passage in payload["retrieved_passages"]["results"]:
            chunk_id = int(passage["chunk_id"])
            raw_text, storyteller_text = texts[chunk_id]
            if chunk_id == 49:
                assert passage["text"].startswith(storyteller_text)
                assert passage["text"].endswith(payload["user_input"])
            else:
                assert passage["text"] == raw_text
        evidence["frontier_input_note"] = (
            "Chunk 49 storyteller text verified; archived 1A player input retained "
            "instead of the source pending choice. All other retrieved texts match exactly."
        )
        assert int(payload["retrieved_passages"]["results"][13]["chunk_id"]) == 25
        evidence["verified_retrieval_ids"] = [
            int(p["chunk_id"]) for p in payload["retrieved_passages"]["results"]
        ]
        evidence["user_input"] = payload["user_input"]
        evidence["runs"] = []
        # Process-local admission, as in #909; production validation is unchanged.
        slot_utils.VALID_DBNAMES = {dbname}
        for cap in (5, 15):
            settings = load_settings_as_dict()
            settings["lore"]["render_limits"]["historical_passages"] = cap
            utility = LogonUtility(
                settings,
                model_override="TEST",
                dbname=dbname,
                story_settings=StorySettings(),
            )
            context = TurnContext(
                turn_id=f"911-cap-{cap}", user_input=payload["user_input"], start_time=0
            )
            context.context_payload = deepcopy(payload)
            context.token_counts = {"total_available": 71000, "apex_window": 75000}
            before = utility.measure_turn_requests(context.context_payload, 75000)
            cycle = TurnCycleManager(
                SimpleNamespace(
                    settings=settings,
                    logon=utility,
                    memory_manager=ContextMemoryManager(settings),
                )
            )
            cycle._enforce_context_payload_budget(context)
            requests = utility._assembly_window_requests
            prompt = utility._format_context_prompt(context.context_payload)
            (OUT / f"cap-{cap}-prompt.txt").write_text(prompt)
            printed = [
                int(p["chunk_id"])
                for p in context.context_payload["retrieved_passages"]["results"][:cap]
            ]
            assert (25 in printed) is (cap == 15)
            assert ("[Chunk 25 |" in prompt) is (cap == 15)
            for request in requests:
                assert request.tokens <= request.target

            def historical_tokens(request: Any) -> int:
                return sum(
                    size
                    for i, ((kind, _), size) in enumerate(
                        zip(request.blocks, request.sizes)
                    )
                    if kind == "historical context" and i not in request.removed
                )

            evidence["runs"].append(
                {
                    "cap": cap,
                    "provider_model": utility.provider.model,
                    "printed_ids": printed,
                    "historical_tokens_before_trim": historical_tokens(before[0]),
                    "historical_tokens_after_trim": historical_tokens(requests[0]),
                    "seats": context.context_payload["window_trimming"]["seats"],
                    "dropped_ids": context.context_payload["window_trimming"][
                        "dropped_chunk_ids"
                    ],
                }
            )
        evidence["source_after"] = read_rows("save_04", frontier_sql)
        assert evidence["source_after"] == evidence["source_before"]
    finally:
        dispose_database(dbname)
        slot_utils.VALID_DBNAMES = original_dbnames
        if created:
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(dbname))
                )
        admin.close()
        archive.unlink(missing_ok=True)
    evidence["clone_dropped"] = True
    (OUT / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()

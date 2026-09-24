"""Bounded work-order 781 launcher and evidence collector; no production edits."""

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

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/qa/781-card-identity/live"
DB = "qa640_781_card_identity"


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
                f"781 authorization excludes auxiliary provider call: {seat}"
            )
        original_gate()
        with lock:
            path = OUT / "paid-attempts.jsonl"
            prior = (
                [json.loads(line) for line in path.read_text().splitlines()]
                if path.exists()
                else []
            )
            if sum(row["seat"] == seat for row in prior) >= 2:
                raise RuntimeError("781 paid-turn cap reached")
            identity = query(
                DB,
                "SELECT current_database(), (SELECT count(*) FROM narrative_chunks) AS narrative_chunks, (SELECT max(id) FROM narrative_chunks) AS max_chunk_id, (SELECT count(*) FROM characters) AS characters",
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


def replay() -> None:
    """Replay the saved paid turn locally; never invoke a model or gateway."""
    import asyncio
    from dataclasses import replace
    import types

    import asyncpg
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.agents.orrery.audit import cognition_trace
    from nexus.agents.orrery.backstage import build_backstage_turn
    from nexus.agents.orrery.cards import proposal_handles, rendered_selection
    from nexus.agents.orrery.events import (
        commit_orrery_tick_async,
        commit_orrery_tick_sync,
        normalize_proposal_adjudications,
        validate_proposal_adjudications,
    )
    from nexus.agents.orrery.resolver import OrreryTickProposal
    from nexus.config import load_settings, load_settings_as_dict
    from nexus.telemetry.prompt_window import (
        LocalRequestCounter,
        local_text_counter,
        measure_blocks,
    )
    from tests.pg_fixtures import (
        asyncpg_kwargs,
        disposable_slot_database,
        sqlalchemy_url,
    )

    draft = json.loads((OUT / "after-draft.json").read_text())[0]
    proposal = OrreryTickProposal.from_dict(draft["orrery_proposal"])
    proposal = replace(
        proposal, rendered_cards=tuple(rendered_selection(proposal.to_dict()))
    )
    handles = proposal_handles(proposal.rendered_cards)
    short = [
        dict(item, proposal_id=handles[item["proposal_id"]])
        for item in draft["orrery_adjudications"]
    ]
    canonical = normalize_proposal_adjudications(proposal, short)
    assert validate_proposal_adjudications(
        proposal, canonical
    ) == validate_proposal_adjudications(proposal, draft["orrery_adjudications"])
    save(
        "replay-reference-mapping.json",
        {
            "handles": handles,
            "rendered_adjudications": short,
            "canonical_adjudications": canonical,
        },
    )
    settings = load_settings_as_dict()
    context = json.loads((OUT / "replay-context.json").read_text())
    context["orrery_rendered_cards"] = list(proposal.rendered_cards)
    context["orrery_anchor_chunk_id"] = proposal.anchor_chunk_id
    baseline = types.ModuleType("card_identity_baseline")
    baseline.__file__ = str(ROOT / "nexus/agents/lore/logon_utility.py")
    sys.modules[baseline.__name__] = baseline
    source = subprocess.check_output(
        ["git", "show", "67bf8527:nexus/agents/lore/logon_utility.py"],
        cwd=ROOT,
        text=True,
    )
    exec(compile(source, baseline.__file__, "exec"), baseline.__dict__)
    # The saved turn identifies the exact paid model; no live provider counting.
    model = draft["generation_model"]
    counter = LocalRequestCounter(
        local_text_counter(load_settings().model_entry(model)), 0
    )
    token_receipt = {
        "model": model,
        "accounting": "#903 local_text_counter and measure_blocks; card blocks only, no system/schema framing",
        "seats": {},
    }
    rendered_prompts = {}
    for seat in ("writer", "gaia"):
        versions = {}
        for version, utility in (
            ("original", baseline.LogonUtility(settings)),
            ("amended", LogonUtility(settings)),
        ):
            blocks = []
            utility._format_context_prompt(
                context,
                seat=seat,
                include_ambient_scene_seeds=seat == "writer",
                rendered_blocks=blocks,
            )
            selected = [
                (kind, value)
                for kind, value in blocks
                if kind
                in {
                    "orrery imminent activity",
                    "orrery scene pressure",
                    "orrery joint beats",
                }
            ]
            counts, total = measure_blocks(selected, counter)
            versions[version] = {"blocks": counts, "total": total}
            if version == "amended":
                rendered_prompts[seat] = (
                    "".join(value for _, value in selected).strip() + "\n"
                )
                (OUT.parent / f"after-{seat}-cards.txt").write_text(
                    rendered_prompts[seat]
                )
        assert versions["amended"]["total"] < versions["original"]["total"]
        token_receipt["seats"][seat] = versions
    assert rendered_prompts["writer"] == rendered_prompts["gaia"]
    (OUT.parent / "after-cards.txt").write_text(rendered_prompts["writer"])
    save("replay-token-counts.json", token_receipt)
    count_sql = "SELECT current_database(), (SELECT count(*) FROM narrative_chunks) AS narrative_chunks, (SELECT max(id) FROM narrative_chunks) AS max_chunk_id, (SELECT count(*) FROM characters) AS characters"
    before = query("save_04", count_sql)
    save("replay-source-before.json", before)

    async def commit_async(dbname: str, chunk: int) -> Any:
        conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
        try:
            async with conn.transaction():
                return await commit_orrery_tick_async(
                    conn,
                    proposal,
                    tick_chunk_id=chunk,
                    adjudications=short,
                    storyteller_state_updates=draft["entity_updates"],
                )
        finally:
            await conn.close()

    for path in ("sync", "async"):
        with disposable_slot_database(
            "qa640_781_replay", source_db="save_04", include_data=True
        ) as dbname:
            engine = create_engine(sqlalchemy_url(dbname))
            try:
                with Session(engine) as session:
                    assert (
                        session.execute(text("SELECT current_database()")).scalar_one()
                        == dbname
                    )
                    chunk = session.execute(
                        text(
                            "INSERT INTO narrative_chunks (raw_text, storyteller_text, state) VALUES (:body, :body, 'accepted') RETURNING id"
                        ),
                        {"body": draft["storyteller_text"]},
                    ).scalar_one()
                    session.execute(
                        text(
                            "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, world_layer, time_delta) SELECT :chunk, season, episode, scene+1, world_layer, interval '1 minute' FROM chunk_metadata WHERE chunk_id=:anchor"
                        ),
                        {"chunk": chunk, "anchor": proposal.anchor_chunk_id},
                    )
                    session.commit()
                    if path == "sync":
                        result = commit_orrery_tick_sync(
                            session.connection().connection.driver_connection,
                            proposal,
                            tick_chunk_id=chunk,
                            adjudications=short,
                            storyteller_state_updates=draft["entity_updates"],
                        )
                        session.commit()
                    else:
                        result = asyncio.run(commit_async(dbname, chunk))
                    exposures = query(
                        dbname,
                        f"SELECT kind, proposal_id, position, card FROM orrery_prompt_exposures WHERE tick_chunk_id={chunk} ORDER BY id",
                    )
                    assert [
                        {"kind": row["kind"], "proposal_id": row["proposal_id"]}
                        for row in exposures
                    ] == list(proposal.rendered_cards)
                    shown_handles = [
                        line.split()[2]
                        for line in rendered_prompts["writer"].splitlines()
                        if line.startswith("- [")
                    ]
                    assert shown_handles == [
                        handles[row["proposal_id"]] for row in exposures
                    ]
                    save(f"replay-{path}-exposures.json", exposures)
                    backstage = build_backstage_turn(session, slot=4, chunk_id=chunk)
                    assert [row.position for row in backstage.orrery.rows] == [
                        0,
                        1,
                        2,
                        3,
                        4,
                        2,
                        10,
                    ]
                    assert [row.position for row in backstage.orrery.inventory] == list(
                        range(23)
                    )
                    save(
                        f"replay-{path}-backstage.json",
                        backstage.model_dump(mode="json"),
                    )
                    for actor in (4, 16):
                        trace = cognition_trace(
                            session,
                            actor,
                            anchor_chunk_id=chunk,
                            orrery_settings=settings["orrery"],
                        )
                        shown = trace["actor_facing"]["prompt_exposure"][
                            "orrery_proposals"
                        ]
                        expected = [
                            (row["kind"], row["proposal_id"])
                            for row in exposures
                            if actor
                            in (
                                row["card"]["bindings"].get("actor"),
                                row["card"]["bindings"].get("target"),
                            )
                        ]
                        assert [
                            (row["kind"], row["proposal_id"]) for row in shown
                        ] == expected
                        save(f"replay-{path}-audit-{actor}.json", trace)
                    activity = query(
                        dbname,
                        "SELECT entity_id, name, current_activity FROM characters WHERE name='Ren Vale'",
                    )
                    assert (
                        activity[0]["current_activity"]
                        == "preparing a qualified status inquiry regarding Dr. Sera Vey"
                    )
                    save(f"replay-{path}-ren.json", activity)
                    save(
                        f"replay-{path}-adjudications.json",
                        query(
                            dbname,
                            f"SELECT proposal_id, action, replacement_state_delta FROM orrery_adjudication_log WHERE tick_chunk_id={chunk} ORDER BY id",
                        ),
                    )
                    print(
                        f"{path}: canonical adjudications accepted; {result.prompt_exposure_count} ordered exposures; Backstage [0, 1, 2, 3, 4, 2, 10]; Ren replacement wins"
                    )
            finally:
                engine.dispose()
    after = query("save_04", count_sql)
    assert before == after
    save("replay-source-after.json", after)
    print(
        f"Card blocks: {token_receipt['seats']['writer']['original']['total']} -> {token_receipt['seats']['writer']['amended']['total']} tokens per seat"
    )
    print(
        "save_04 unchanged: 46 chunks, max 49, 23 characters; disposable replay databases dropped; no provider calls"
    )


def main() -> None:
    """Run the fixed clone, supervisor, or gateway stage of the order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["clone", "up", "gateway", "replay"])
    args = parser.parse_args()
    assert Path(__import__("nexus").__file__).is_relative_to(ROOT)
    if args.stage == "replay":
        replay()
        return
    if args.stage == "clone":
        from nexus.database import connection_kwargs
        from scripts.new_story_setup import _postgres_tools
        from psycopg2.extensions import make_dsn

        save(
            "source-before.json",
            query(
                "save_04",
                "SELECT current_database(), (SELECT count(*) FROM narrative_chunks) AS narrative_chunks, (SELECT max(id) FROM narrative_chunks) AS max_chunk_id, (SELECT count(*) FROM characters) AS characters",
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
        dump = ROOT / ".nexus/781-source.dump"
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
                DB,
                "SELECT current_database(), (SELECT count(*) FROM narrative_chunks) AS narrative_chunks, (SELECT max(id) FROM narrative_chunks) AS max_chunk_id, (SELECT count(*) FROM characters) AS characters",
            )
        )
        return
    os.environ["NEXUS_SLOT"] = "4"
    os.environ["NEXUS_GATEWAY_PORT"] = "8015"
    os.environ["NEXUS_API_URL"] = "http://127.0.0.1:8015"
    install_guards()
    print(
        query(
            DB,
            "SELECT current_database(), (SELECT count(*) FROM narrative_chunks) AS narrative_chunks, (SELECT max(id) FROM narrative_chunks) AS max_chunk_id, (SELECT count(*) FROM characters) AS characters",
        ),
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

        uvicorn.run("nexus.api.narrative:app", host="127.0.0.1", port=8015)


if __name__ == "__main__":
    main()

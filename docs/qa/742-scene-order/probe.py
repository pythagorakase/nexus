"""Capture the actual save_04 frontier through a disposable clone, without inference."""

import asyncio
import argparse
import json
from pathlib import Path
from uuid import uuid4

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility, _retrieval_source_label
from nexus.api import slot_utils
from nexus.config.story_model import read_story_settings
from nexus.memory.context_state import is_retrograde_summary, memory_identity
from nexus.memory.manager import pass2_baseline_config_fingerprint
from tests.pg_fixtures import connect, disposable_slot_database


def main() -> None:
    """Restore the stamped frontier and archive both TEST seat renders."""
    output = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), default="after")
    phase = parser.parse_args().phase
    with disposable_slot_database(
        "qa640_742_scene", source_db="save_04", include_data=True
    ) as dbname:
        slot_utils.VALID_DBNAMES = slot_utils.VALID_DBNAMES | {dbname}
        lore = LORE(enable_logon=False, dbname=dbname, model_override="TEST")
        try:
            with connect(dbname) as conn, conn.cursor() as cur:
                cur.execute("SELECT max(id) FROM narrative_chunks")
                parent = cur.fetchone()[0]
            baseline = lore.memory_manager.restore_pass2_baseline(parent)
            print("FINGERPRINT_RESTORE_PASSED", baseline.config_fingerprint)
            assert baseline.config_fingerprint == pass2_baseline_config_fingerprint(
                lore.settings
            )
            if phase == "after":
                assert (
                    baseline.config_fingerprint
                    == json.loads((output / "before.json").read_text())["fingerprint"]
                )
            result = asyncio.run(
                lore.process_turn(
                    "Ask Kessa Brin what she remembers.",
                    parent_chunk_id=parent,
                    attempt_id=str(uuid4()),
                )
            )
            assert result == "LOGON disabled", result
            payload = lore.turn_context.context_payload
            (output / f"{phase}-payload.json").write_text(
                json.dumps(payload, indent=2, default=str) + "\n"
            )
            utility = LogonUtility(
                lore.settings,
                dbname=dbname,
                model_override="TEST",
                story_settings=read_story_settings(dbname),
            )
            requests = utility.measure_turn_requests(
                payload, lore.turn_context.token_counts["apex_window"]
            )
            from nexus.telemetry.prompt_window import measure_blocks

            evidence = {
                "database": dbname,
                "parent": parent,
                "fingerprint": baseline.config_fingerprint,
                "seats": {},
            }
            before_payload = json.loads((output / "before-payload.json").read_text())
            for request in requests:
                seat = request.budget.seat
                (output / f"{phase}-{seat}.txt").write_text(
                    "".join(value for _, value in request.blocks)
                )
                counts, total = measure_blocks(request.blocks, request.counter)
                memories = (
                    payload["warm_slice"]["chunks"]
                    + payload["retrieved_passages"]["results"]
                )
                by_source = {id(memory): memory for memory in memories}
                lanes = {}
                rendered_tokens = {}
                for index, source in request.sources.items():
                    identity = memory_identity(by_source[source])
                    kind, content = request.blocks[index]
                    lanes.setdefault(kind, []).append(identity)
                    rendered_tokens[identity] = (
                        rendered_tokens.get(identity, 0) + request.sizes[index]
                    )
                evidence["seats"][seat] = {
                    "blocks": counts,
                    "total": total,
                    "lane_ids": lanes,
                }
                if seat == "skald_writer":
                    pending = dict(lore.memory_manager._pending_retrieval_coverage)
                    if phase == "after":
                        old_tokens = {}
                        for memory in before_payload["warm_slice"]["chunks"]:
                            content = memory["text"]
                            if is_retrograde_summary(memory):
                                content = (
                                    f"[{_retrieval_source_label(memory)}] {content}"
                                )
                            old_tokens[memory_identity(memory)] = (
                                request.counter.text_count("\n" + content)
                            )
                        limit = lore.settings["lore"]["render_limits"][
                            "historical_passages"
                        ]
                        for memory in before_payload["retrieved_passages"]["results"][
                            :limit
                        ]:
                            identity = memory_identity(memory)
                            content = (
                                f"\n[{_retrieval_source_label(memory)} | "
                                f"Score: {memory.get('score', 0):.2f}] {memory.get('text', '')}"
                            )
                            old_tokens[identity] = old_tokens.get(
                                identity, 0
                            ) + request.counter.text_count(content)
                        lore.memory_manager._pending_retrieval_coverage = {
                            **pending,
                            "turn_id": lore.turn_context.turn_id + ":before",
                        }
                        lore.memory_manager.record_rendered_coverage(
                            before_payload["warm_slice"]["chunks"], old_tokens
                        )
                        lore.memory_manager._pending_retrieval_coverage = pending
                    lore.memory_manager.record_rendered_coverage(
                        memories, rendered_tokens
                    )
            with connect(dbname) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT kept_chunk_ids, kept_tokens, raw_result_count, coverage, gap_entities FROM retrieval_coverage_log WHERE turn_id = %s",
                    (lore.turn_context.turn_id,),
                )
                row = cur.fetchone()
                evidence["coverage"] = dict(
                    zip(
                        (
                            "kept_chunk_ids",
                            "kept_tokens",
                            "raw_result_count",
                            "coverage",
                            "gap_entities",
                        ),
                        row,
                    )
                )
                if phase == "after":
                    cur.execute(
                        "SELECT kept_chunk_ids, kept_tokens, raw_result_count, coverage, gap_entities FROM retrieval_coverage_log WHERE turn_id = %s",
                        (lore.turn_context.turn_id + ":before",),
                    )
                    evidence["before_coverage"] = dict(
                        zip(evidence["coverage"], cur.fetchone())
                    )
                    assert {
                        k: v
                        for k, v in evidence["coverage"].items()
                        if k != "kept_tokens"
                    } == {
                        k: v
                        for k, v in evidence["before_coverage"].items()
                        if k != "kept_tokens"
                    }
            if phase == "after":
                for section, key in (
                    ("warm_slice", "chunks"),
                    ("retrieved_passages", "results"),
                ):
                    assert {
                        memory_identity(m): m["text"] for m in payload[section][key]
                    } == {
                        memory_identity(m): m["text"]
                        for m in before_payload[section][key]
                    }
                assert [
                    memory_identity(m) for m in payload["retrieved_passages"]["results"]
                ] == [
                    memory_identity(m)
                    for m in before_payload["retrieved_passages"]["results"]
                ]
                before = json.loads((output / "before.json").read_text())
                for seat, data in evidence["seats"].items():
                    data["total_delta"] = data["total"] - before["seats"][seat]["total"]
                print("IDENTITIES_AND_PROSE_UNCHANGED")
            (output / f"{phase}.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence, indent=2))
        finally:
            lore.close()


if __name__ == "__main__":
    main()

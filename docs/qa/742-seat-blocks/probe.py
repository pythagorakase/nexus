"""Capture save_04 frontier prompts on a disposable clone using TEST only."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api import slot_utils
from nexus.config.story_model import read_story_settings
from nexus.memory.manager import pass2_baseline_config_fingerprint
from nexus.telemetry.prompt_window import measure_blocks
from tests.pg_fixtures import connect, disposable_slot_database


def main() -> None:
    """Archive the real two-seat render, counts, and restored fingerprint."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    phase = parser.parse_args().phase
    output = Path(__file__).parent
    with disposable_slot_database(
        "qa640_742_seats", source_db="save_04", include_data=True
    ) as dbname:
        slot_utils.VALID_DBNAMES = slot_utils.VALID_DBNAMES | {dbname}
        lore = LORE(enable_logon=False, dbname=dbname, model_override="TEST")
        try:
            with connect(dbname) as conn, conn.cursor() as cur:
                cur.execute("SELECT max(id) FROM narrative_chunks")
                parent = cur.fetchone()[0]
            baseline = lore.memory_manager.restore_pass2_baseline(parent)
            assert baseline.config_fingerprint == pass2_baseline_config_fingerprint(
                lore.settings
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
            utility = LogonUtility(
                lore.settings,
                dbname=dbname,
                model_override="TEST",
                story_settings=read_story_settings(dbname),
            )
            requests = utility.measure_turn_requests(
                payload, lore.turn_context.token_counts["apex_window"]
            )
            evidence = {
                "database": dbname,
                "parent": parent,
                "fingerprint": baseline.config_fingerprint,
                "seats": {},
            }
            for request in requests:
                seat = request.budget.seat
                prompt = "".join(value for _, value in request.blocks)
                (output / f"{phase}-{seat}.txt").write_text(prompt)
                counts, total = measure_blocks(request.blocks, request.counter)
                evidence["seats"][seat] = {"blocks": counts, "total": total}
            if phase == "after":
                before = json.loads((output / "before.json").read_text())
                assert evidence["fingerprint"] == before["fingerprint"]
                for seat, data in evidence["seats"].items():
                    data["saving"] = before["seats"][seat]["total"] - data["total"]
            (output / f"{phase}.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence, indent=2))
        finally:
            lore.close()
    with connect("postgres") as conn, conn.cursor() as cur:
        cur.execute("SELECT datname FROM pg_database WHERE datname = %s", (dbname,))
        assert cur.fetchone() is None
    print("FRONTIER_PROOF_PASSED: TEST renders; fingerprint verified; clone removed")


if __name__ == "__main__":
    main()

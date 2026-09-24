"""Capture the actual save_04 frontier through a disposable clone, without inference."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api import slot_utils
from nexus.config.story_model import read_story_settings
from tests.pg_fixtures import connect, disposable_slot_database


def main() -> None:
    """Restore the stamped frontier and archive both TEST seat renders."""
    output = Path(__file__).parent
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
            result = asyncio.run(
                lore.process_turn(
                    "Ask Kessa Brin what she remembers.",
                    parent_chunk_id=parent,
                    attempt_id=str(uuid4()),
                )
            )
            assert result == "LOGON disabled", result
            payload = lore.turn_context.context_payload
            (output / "before-payload.json").write_text(
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
            for request in requests:
                seat = request.budget.seat
                (output / f"before-{seat}.txt").write_text(
                    "".join(value for _, value in request.blocks)
                )
                counts, total = measure_blocks(request.blocks, request.counter)
                evidence["seats"][seat] = {"blocks": counts, "total": total}
            (output / "before.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence, indent=2))
        finally:
            lore.close()


if __name__ == "__main__":
    main()

"""Capture both TEST seats from a disposable save_04 frontier clone."""

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
    """Archive renders, dossier token counts, and restored fingerprint proof."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    phase = parser.parse_args().phase
    output = Path(__file__).parent
    with disposable_slot_database(
        "qa640_916_dossier", source_db="save_04", include_data=True
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
            utility = LogonUtility(
                lore.settings,
                dbname=dbname,
                model_override="TEST",
                story_settings=read_story_settings(dbname),
            )
            requests = utility.measure_turn_requests(
                lore.turn_context.context_payload,
                lore.turn_context.token_counts["apex_window"],
            )
            evidence = {
                "database": dbname,
                "parent": parent,
                "fingerprint": baseline.config_fingerprint,
                "seats": {},
            }
            dossiers = []
            for request in requests:
                seat = request.budget.seat
                (output / f"{phase}-{seat}.txt").write_text(
                    "".join(v for _, v in request.blocks)
                )
                dossier = "".join(v for k, v in request.blocks if k == "entity dossier")
                (output / f"{phase}-{seat}-dossier.txt").write_text(dossier)
                dossiers.append(dossier)
                counts, total = measure_blocks(request.blocks, request.counter)
                evidence["seats"][seat] = {"blocks": counts, "total": total}
            assert len(dossiers) == 2 and dossiers[0] == dossiers[1]
            if phase == "after":
                before = json.loads((output / "before.json").read_text())
                assert evidence["fingerprint"] == before["fingerprint"]
                for seat, data in evidence["seats"].items():
                    assert (
                        data["blocks"].keys() == before["seats"][seat]["blocks"].keys()
                    )
                assert "Unknown → Unknown" not in dossiers[0]
                assert "at None" not in dossiers[0]
            (output / f"{phase}.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps(evidence, indent=2))
            print(
                "PASS: restored fingerprint; both seats have identical dossiers; TEST only"
            )
        finally:
            lore.close()


if __name__ == "__main__":
    main()

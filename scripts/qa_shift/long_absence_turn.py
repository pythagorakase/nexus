"""Run one explicitly named 909 turn through the CLI, then accept and archive it."""

import json
import os
import subprocess
import sys

import requests

from scripts.qa_shift.long_absence_probe import DB, OUT, query, save


def main() -> None:
    """Use immutable saved player input and fail before accepting errors."""
    label = sys.argv[1]
    plan = next(
        row
        for row in json.loads((OUT / "inputs.json").read_text())
        if row["turn"] == label
    )
    target = query(
        DB, "SELECT current_database(), count(*), max(id) FROM narrative_chunks"
    )
    save(f"{label}-before.json", target)
    existing = list(OUT.glob(f"{label}-cli.log"))
    if existing:
        raise RuntimeError("Refusing to repeat an already attempted turn")
    env = dict(
        os.environ, NEXUS_GATEWAY_PORT="8018", NEXUS_API_URL="http://127.0.0.1:8018"
    )
    argv = [
        sys.executable,
        "-m",
        "nexus.cli",
        "continue",
        "--slot",
        "4",
        "--user-text",
        plan["user_text"],
    ]
    save(f"{label}-command.json", argv)
    with (OUT / f"{label}-cli.log").open("w") as handle:
        result = subprocess.run(argv, env=env, stdout=handle, stderr=subprocess.STDOUT)
    print((OUT / f"{label}-cli.log").read_text(), flush=True)
    if result.returncode:
        raise RuntimeError(f"CLI failed: {result.returncode}")
    drafts = query(DB, "SELECT * FROM incubator")
    save(f"{label}-draft.json", drafts)
    if len(drafts) != 1 or drafts[0]["user_text"] != plan["user_text"]:
        raise RuntimeError("Turn draft does not match requested input")
    session = str(drafts[0]["session_id"])
    query(DB, "SELECT current_database()")
    response = requests.post(
        "http://127.0.0.1:8018/api/narrative/approve",
        json={"slot": 4, "session_id": session, "commit": True},
        timeout=120,
    )
    save(
        f"{label}-approval.json",
        {"status": response.status_code, "body": response.json()},
    )
    response.raise_for_status()
    save(
        f"{label}-after.json",
        query(DB, "SELECT current_database(), count(*), max(id) FROM narrative_chunks"),
    )
    save(
        f"{label}-accepted.json",
        query(
            DB,
            "SELECT * FROM narrative_chunks WHERE id=(SELECT max(id) FROM narrative_chunks)",
        ),
    )
    save(
        f"{label}-coverage.json",
        query(DB, f"SELECT * FROM retrieval_coverage_log WHERE turn_id='{session}'"),
    )
    chunk = response.json()["chunk_id"]
    for table, column in [
        ("chunk_metadata", "chunk_id"),
        ("chunk_character_references", "chunk_id"),
        ("world_events", "tick_chunk_id"),
        ("orrery_adjudication_log", "tick_chunk_id"),
        ("orrery_prompt_exposures", "tick_chunk_id"),
    ]:
        save(
            f"{label}-{table}.json",
            query(DB, f"SELECT * FROM {table} WHERE {column}={chunk}"),
        )
    print(f"ACCEPTED {label}: {session}", flush=True)


if __name__ == "__main__":
    main()

"""Report pre-mint identity matches against earlier IDs without changing data."""

from __future__ import annotations

import argparse
import json

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.database import connection_kwargs
from nexus.presence.identity import identity_index, resolve_character_declaration


def census(dbname: str) -> dict:
    """Run a read-only, ascending-ID merge-impact census on a disposable clone."""
    if not dbname.startswith("qa640_"):
        raise ValueError("The identity census requires a qa640_ clone")
    with psycopg2.connect(**connection_kwargs(dbname)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, entity_id, summary FROM characters ORDER BY id"
            )
            characters = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT character_id, alias FROM character_aliases")
            aliases = [dict(row) for row in cur.fetchall()]
    results = []
    for position, character in enumerate(characters):
        index = identity_index(characters[:position], aliases)
        result = resolve_character_declaration(character, index)
        if result.status != "novel":
            results.append(
                {
                    "id": character["id"],
                    "name": character["name"],
                    "status": result.status,
                    "existing_id": result.existing_id,
                    "candidates": [entry.model_dump() for entry in result.candidates],
                    "reason": result.reason,
                }
            )
    return {
        "database": dbname,
        "characters": len(characters),
        "resolved_to_earlier": sum(row["status"] == "resolved" for row in results),
        "ambiguous": sum(row["status"] == "ambiguous" for row in results),
        "matches": results,
    }


def main() -> None:
    """Print the strictly read-only census as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dbname")
    args = parser.parse_args()
    print(json.dumps(census(args.dbname), indent=2))


if __name__ == "__main__":
    main()

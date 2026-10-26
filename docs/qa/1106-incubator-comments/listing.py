"""List the incubator comments migration 152 sets, from a migrated qa640_ clone.

Issue #1106. Compares each col_description (and the obj_description of
public.clear_incubator()) with the literal in migration 152, prints the live
text, and exits non-zero on any mismatch. Run from the worktree root with
NEXUS_RUN_POSTGRES=1 and PYTHONPATH set to it.
"""

import re
import sys
from contextlib import closing
from pathlib import Path

from tests.pg_fixtures import connect, disposable_slot_database

COLUMNS = [
    "metadata_updates",
    "entity_updates",
    "reference_updates",
    "status",
    "llm_response_id",
    "authorial_directives",
    "orrery_proposal",
    "parent_chunk_id",
    "choice_object",
    "generation_model",
]
FUNCTION = "clear_incubator()"
COMMENT = re.compile(
    r"COMMENT ON (?:COLUMN public\.incubator\.(\w+)"
    r"|FUNCTION public\.(clear_incubator\(\))) IS\n    '((?:[^']|'')*)';"
)


def main() -> int:
    """Print each comment and whether it equals the migration text."""
    sql = Path("migrations/152_incubator_column_comments.sql").read_text()
    expected = {
        (m.group(1) or m.group(2)): m.group(3).replace("''", "'")
        for m in COMMENT.finditer(sql)
    }
    assert sorted(expected) == sorted([*COLUMNS, FUNCTION]), sorted(expected)
    ok = True
    with disposable_slot_database("qa640_1106_listing") as dbname:
        with closing(connect(dbname)) as conn:
            conn.set_session(readonly=True)
            with conn.cursor() as cur:
                cur.execute("SELECT max(version) FROM schema_migrations")
                version = cur.fetchone()[0]
                print(f"clone qa640_1106_listing_* at schema version {version}")
                actual: dict[str, str | None] = {}
                for column in COLUMNS:
                    cur.execute(
                        "SELECT col_description(a.attrelid, a.attnum) "
                        "FROM pg_attribute a "
                        "WHERE a.attrelid = 'public.incubator'::regclass "
                        "AND a.attname = %s AND NOT a.attisdropped",
                        (column,),
                    )
                    actual[column] = cur.fetchone()[0]
                cur.execute(
                    "SELECT obj_description("
                    "'public.clear_incubator()'::regprocedure, 'pg_proc')"
                )
                actual[FUNCTION] = cur.fetchone()[0]
    for name in [*COLUMNS, FUNCTION]:
        text = actual[name]
        same = text == expected[name]
        ok &= same
        size = len(text.encode()) if text is not None else 0
        print(f"\n{name} (byte-identical to migration text: {same}, {size} bytes)")
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

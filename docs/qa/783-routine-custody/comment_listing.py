"""List the migration-145 comments from a migrated qa640_ clone (issue #783, S1a).

Prints each obj_description/col_description, then compares the listing with
every COMMENT ON literal in migrations/145_routine_anchor_custody.sql and
prints ``<listed> <in migration> equal`` when they match one for one. Run from
the worktree root with NEXUS_RUN_POSTGRES=1 and PYTHONPATH set to it.
"""

import re
import sys
from contextlib import closing
from pathlib import Path

from tests.pg_fixtures import connect, disposable_slot_database

MIGRATION = Path("migrations/145_routine_anchor_custody.sql")
COMMENT = re.compile(r"COMMENT ON (TYPE|TABLE|COLUMN) (\S+) IS\s+'((?:[^']|'')*)';")
LISTING = """
SELECT 'TYPE orrery_routine_anchor_writer' AS object,
       obj_description('orrery_routine_anchor_writer'::regtype, 'pg_type') AS comment
UNION ALL
SELECT 'TABLE character_routine_anchor_log',
       obj_description('character_routine_anchor_log'::regclass, 'pg_class')
UNION ALL
SELECT * FROM (
  SELECT 'COLUMN character_routine_anchor_log.' || a.attname,
         col_description(a.attrelid, a.attnum)
  FROM pg_attribute a
  WHERE a.attrelid = 'character_routine_anchor_log'::regclass
    AND a.attnum > 0 AND NOT a.attisdropped
  ORDER BY a.attnum) cols
UNION ALL
SELECT * FROM (
  SELECT 'COLUMN character_routine_anchors.' || a.attname,
         col_description(a.attrelid, a.attnum)
  FROM pg_attribute a
  WHERE a.attrelid = 'character_routine_anchors'::regclass
    AND a.attname IN ('last_log_id', 'schedule', 'source')
  ORDER BY a.attnum) anchors
"""


def main() -> int:
    """Print the listing and whether it equals the migration text."""

    expected = {
        f"{kind} {name}": text.replace("''", "'")
        for kind, name, text in COMMENT.findall(MIGRATION.read_text())
    }
    with disposable_slot_database("qa640_783s1a_doc") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT max(version) FROM schema_migrations")
            print(f"clone migrated to {cur.fetchone()[0]}")
            cur.execute(LISTING)
            listed = dict(cur.fetchall())
    for name, comment in listed.items():
        print(f"{name} | {comment}")
    same = listed == expected
    verdict = "equal" if same else "DIFFERENT"
    print(f"{len(listed)} {len(expected)} {verdict}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())

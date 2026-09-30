"""List the five view comments from a migrated qa640_ clone (issue #819, slice E).

Compares each obj_description with the literal in migration 137. Run from the
worktree root with NEXUS_RUN_POSTGRES=1 and PYTHONPATH set to it.
"""

import re
import sys
from contextlib import closing
from pathlib import Path

from tests.pg_fixtures import connect, disposable_slot_database

VIEWS = [
    "chunk_entity_references_v",
    "entity_names_v",
    "entity_relationships_v",
    "entity_tags_current",
    "incubator_view",
]
COMMENT = re.compile(r"COMMENT ON VIEW public\.(\w+) IS\n    '((?:[^']|'')*)';")


def main() -> int:
    """Print each view comment and whether it equals the migration text."""
    sql = Path("migrations/137_view_comments.sql").read_text()
    expected = {
        m.group(1): m.group(2).replace("''", "'") for m in COMMENT.finditer(sql)
    }
    assert sorted(expected) == sorted(VIEWS), sorted(expected)
    ok = True
    with disposable_slot_database("qa640_819s1_listing") as dbname:
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT max(version) FROM schema_migrations")
            version = cur.fetchone()[0]
            print(f"clone qa640_819s1_listing_* at schema version {version}")
            for view in VIEWS:
                cur.execute(
                    "SELECT obj_description(%s::regclass, 'pg_class')",
                    (f"public.{view}",),
                )
                actual = cur.fetchone()[0]
                same = actual == expected[view]
                ok &= same
                size = len(actual.encode())
                print(
                    f"\n{view} (byte-identical to migration text: {same}, "
                    f"{size} bytes)"
                )
                print(actual)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

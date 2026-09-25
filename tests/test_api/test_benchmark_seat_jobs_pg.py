"""The enqueue-fence benchmark persists executable seat identities."""

from contextlib import closing

import pytest

from scripts.benchmark_experience_enqueue_fence import _plant_shape
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres


def test_benchmark_jobs_have_resolved_identity():
    """Plant the real 5k/500/10 benchmark shape in a migrated disposable clone."""
    with disposable_slot_database("qa640_814_benchmark") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            _plant_shape(cur)
            cur.execute(
                "SELECT resolved_model, resolved_source, count(*) "
                "FROM character_experience_jobs "
                "WHERE source_digest LIKE 'qa-wt720-benchmark-job-%' "
                "GROUP BY resolved_model, resolved_source"
            )
            assert cur.fetchall() == [("TEST", "request", 500)]

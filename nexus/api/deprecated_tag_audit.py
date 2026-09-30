"""Read-only audit of active entity tags in deprecated registry categories.

``tag_category_registry`` marks a category deprecated and names its
``replacement_categories`` (migrations 043 and 055), but rows bestowed before
the deprecation stay active in ``entity_tags``. This audit reports them per
database, grouped by category and tag, for ``nexus tags audit`` (issue #811).
It never writes: every read runs in one read-only, repeatable-read
transaction, so a locked slot is read like any other and the report is one
consistent snapshot of each database.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, List, Mapping, Optional, Sequence

import psycopg2

from nexus.api.slot_utils import all_slots, slot_dbname
from nexus.database import connection_kwargs

TEMPLATE_DATABASE = "NEXUS_template"

# The migration that creates each table and column the audit statements
# read, named when a database lacks it. Keep this in step with the two
# statements below: the preflight is what keeps a missing column a domain
# failure instead of a PostgreSQL error.
_REQUIRED_TABLES: Mapping[str, str] = {
    "tags": "023_orrery_schema",
    "entity_tags": "023_orrery_schema",
    "tag_category_registry": "037_orrery_tag_category_registry",
}
_REQUIRED_COLUMNS: Mapping[tuple[str, str], str] = {
    ("entity_tags", "entity_id"): "023_orrery_schema",
    ("entity_tags", "tag_id"): "023_orrery_schema",
    ("entity_tags", "cleared_at"): "023_orrery_schema",
    ("tags", "id"): "023_orrery_schema",
    ("tags", "tag"): "023_orrery_schema",
    ("tags", "category"): "023_orrery_schema",
    ("tag_category_registry", "category"): "037_orrery_tag_category_registry",
    ("tag_category_registry", "entity_kind"): "037_orrery_tag_category_registry",
    ("tag_category_registry", "deprecated"): "043_orrery_category_refactor_phase1",
    (
        "tag_category_registry",
        "replacement_categories",
    ): "043_orrery_category_refactor_phase1",
}

_DEPRECATED_REGISTRY_SQL = """
    SELECT category, entity_kind::text AS entity_kind, replacement_categories
    FROM tag_category_registry
    WHERE deprecated
    ORDER BY category, entity_kind::text
"""

_ACTIVE_ROWS_SQL = """
    SELECT t.category,
           t.tag,
           count(*) AS row_count,
           array_agg(et.entity_id ORDER BY et.entity_id) AS entity_ids
    FROM entity_tags et
    JOIN tags t ON t.id = et.tag_id
    WHERE et.cleared_at IS NULL
      AND t.category = ANY(%s::text[])
    GROUP BY t.category, t.tag
    ORDER BY t.category, t.tag
"""


class DeprecatedTagAuditError(RuntimeError):
    """A database the audit cannot read as the registry schema requires."""


def audit_database_names(slot: Optional[int]) -> List[str]:
    """The databases one audit reads: one slot, or the template and every slot."""
    if slot is not None:
        return [slot_dbname(slot)]
    return [TEMPLATE_DATABASE, *(slot_dbname(number) for number in all_slots())]


def _slot_of(dbname: str) -> Optional[int]:
    """The slot number a database serves, or None for the template."""
    for number in all_slots():
        if slot_dbname(number) == dbname:
            return number
    return None


def _require_schema(cur: Any, dbname: str) -> None:
    """Raise, naming the migration, when a table or column the audit reads is absent."""
    for table, migration in _REQUIRED_TABLES.items():
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        if cur.fetchone()[0] is None:
            raise DeprecatedTagAuditError(
                f"{dbname} has no {table} table; apply migration {migration} "
                "(scripts/migrate.py) before auditing it"
            )
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        """,
        (sorted(_REQUIRED_TABLES),),
    )
    present = {(str(table), str(column)) for table, column in cur.fetchall()}
    for (table, column), migration in _REQUIRED_COLUMNS.items():
        if (table, column) not in present:
            raise DeprecatedTagAuditError(
                f"{dbname} has no {table}.{column} column; apply "
                f"migration {migration} (scripts/migrate.py) before auditing it"
            )


def _replacements_by_category(
    registry_rows: Sequence[Sequence[Any]],
) -> Dict[str, List[str]]:
    """Each deprecated category's replacements, in registry order, without repeats.

    A category registered for several entity kinds contributes each kind's
    replacements in turn (kinds sorted), so the report never drops one.
    """
    replacements: Dict[str, List[str]] = {}
    for category, _entity_kind, categories in registry_rows:
        merged = replacements.setdefault(str(category), [])
        for replacement in categories or []:
            if replacement not in merged:
                merged.append(str(replacement))
    return replacements


def audit_database(dbname: str) -> Dict[str, Any]:
    """Report one database's active rows in deprecated categories, read-only."""
    with closing(psycopg2.connect(**connection_kwargs(dbname))) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        try:
            with conn.cursor() as cur:
                _require_schema(cur, dbname)
                cur.execute(_DEPRECATED_REGISTRY_SQL)
                replacements = _replacements_by_category(cur.fetchall())
                cur.execute(_ACTIVE_ROWS_SQL, (sorted(replacements),))
                rows = cur.fetchall()
        finally:
            conn.rollback()
    groups = [
        {
            "category": str(category),
            "tag": str(tag),
            "replacement_categories": replacements[str(category)],
            "row_count": int(row_count),
            "entity_ids": [int(entity_id) for entity_id in entity_ids],
        }
        for category, tag, row_count, entity_ids in rows
    ]
    return {
        "database": dbname,
        "slot": _slot_of(dbname),
        "deprecated_categories": sorted(replacements),
        "active_rows": sum(group["row_count"] for group in groups),
        "groups": groups,
    }

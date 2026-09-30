#!/usr/bin/env python3
"""Report row parity and schema invariants for chunk entity references (#836).

Issue #836 replaces the three chunk junctions (``chunk_character_references``,
``chunk_faction_references``, ``place_chunk_references``) with one typed
``chunk_entity_references`` table. Before any junction or bridging view is
removed, this report proves row-level parity per kind and records every
invariant the junctions enforce.

Expected rows come from each junction joined to its subtype table for
``entity_id``: ``(chunk_id, entity_id, kind, reference_type, evidence)``, where
``kind`` is ``entities.kind`` (not the junction's name), ``reference_type`` is
the role as text or NULL (factions have no role column), and ``evidence`` is
``place_chunk_references.evidence`` or NULL. A junction row whose subtype has
no entity, or whose entity kind differs from the junction's kind, is an
invariant violation.

The target relation (``--target``, default the bridging view
``chunk_entity_references_v``) is compared with the expected rows as a
multiset, on the expected columns the target carries (read from the catalog).
Target rows are attributed to a kind through ``entities.kind`` of their
``entity_id``. An expected column the target does not carry is reported with
``"carried": false`` and the number of expected rows whose value is not NULL;
a column that is not carried does not by itself fail the run, because the
unified table is expected to carry ``kind`` and ``evidence`` and the view is
not.

The report is one JSON document on stdout. The session is read-only by
construction: ``default_transaction_read_only=on`` in a repeatable-read
snapshot, checked before the first query.

Exit status: 0 when every kind has no missing row, no extra row, and no
invariant violation, and no target row lacks an entity; 3 otherwise. Errors
raise (status 1); argument errors exit 2.

Usage:
    python scripts/entity_reference_parity.py --dbname save_01
    python scripts/entity_reference_parity.py --dbname qa640_clone \\
        --target chunk_entity_references --limit 5
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
import json
import logging
import sys
from typing import Any, NamedTuple

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as PGConnection

from nexus.database import connection_kwargs
from scripts.database_targets import metrics_dbname

logger = logging.getLogger("nexus.entity_reference_parity")

SCHEMA_VERSION = 1
EXIT_PARITY = 0
EXIT_MISMATCH = 3
DEFAULT_TARGET = "chunk_entity_references_v"
DEFAULT_LIMIT = 10

# The unified row shape; the order is the comparison order.
EXPECTED_COLUMNS = ("chunk_id", "entity_id", "kind", "reference_type", "evidence")
# Columns without which no row can be matched at all.
REQUIRED_TARGET_COLUMNS = ("chunk_id", "entity_id")
# Compared as integers; every other expected column is compared as text.
INTEGER_COLUMNS = frozenset({"chunk_id", "entity_id"})

# pg_constraint.confupdtype / confdeltype codes.
FK_ACTIONS = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}
RELKINDS = {
    "r": "table",
    "p": "partitioned table",
    "v": "view",
    "m": "materialized view",
    "f": "foreign table",
}


class Junction(NamedTuple):
    """One legacy chunk junction and how its rows map to the unified shape."""

    kind: str
    table: str
    subtype_table: str
    subtype_column: str
    role_column: str | None
    evidence_column: str | None


JUNCTIONS = (
    Junction(
        "character",
        "chunk_character_references",
        "characters",
        "character_id",
        "reference",
        None,
    ),
    Junction(
        "place",
        "place_chunk_references",
        "places",
        "place_id",
        "reference_type",
        "evidence",
    ),
    Junction(
        "faction",
        "chunk_faction_references",
        "factions",
        "faction_id",
        None,
        None,
    ),
)

Row = tuple[Any, ...]


def _one(cur: Any) -> tuple[Any, ...]:
    """Return the single row a query must produce, or raise."""
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Query returned no row: {cur.query!r}")
    return tuple(row)


def open_read_only_connection(dbname: str) -> PGConnection:
    """Open a read-only, repeatable-read session on ``dbname`` or raise.

    The session options make every transaction read-only; the check reads the
    setting back inside the first transaction, so a server or pooler that
    ignored the options fails here, before any report query runs.
    """
    metrics_dbname(dbname)
    conn = psycopg2.connect(
        **connection_kwargs(
            dbname,
            options=(
                "-c default_transaction_read_only=on "
                "-c default_transaction_isolation=repeatable\\ read"
            ),
        )
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('transaction_isolation')"
            )
            read_only, isolation = _one(cur)
        if read_only != "on":
            raise RuntimeError(
                f"Read-only transaction is required on {dbname}; "
                f"transaction_read_only={read_only!r}"
            )
        if isolation != "repeatable read":
            raise RuntimeError(
                f"Repeatable-read isolation is required on {dbname}; "
                f"transaction_isolation={isolation!r}"
            )
    except BaseException:
        conn.close()
        raise
    return conn


def _expected_rows_sql() -> sql.Composed:
    """Build the expected-row query: every junction row in the unified shape.

    Each row also carries its junction kind, its subtype id, and whether the
    subtype resolved to an existing entity, so invariant violations can be
    named without a second query.
    """
    parts = []
    for junction in JUNCTIONS:
        role = (
            sql.SQL("j.{}::text").format(sql.Identifier(junction.role_column))
            if junction.role_column
            else sql.SQL("NULL::text")
        )
        evidence = (
            sql.SQL("j.{}::text").format(sql.Identifier(junction.evidence_column))
            if junction.evidence_column
            else sql.SQL("NULL::text")
        )
        parts.append(
            sql.SQL(
                "SELECT j.chunk_id::bigint, s.entity_id::bigint, e.kind::text, "
                "{role}, {evidence}, {kind}::text, j.{subtype_column}::bigint, "
                "e.id IS NOT NULL "
                "FROM {table} j "
                "LEFT JOIN {subtype_table} s ON s.id = j.{subtype_column} "
                "LEFT JOIN entities e ON e.id = s.entity_id"
            ).format(
                role=role,
                evidence=evidence,
                kind=sql.Literal(junction.kind),
                subtype_column=sql.Identifier(junction.subtype_column),
                table=sql.Identifier(junction.table),
                subtype_table=sql.Identifier(junction.subtype_table),
            )
        )
    return sql.SQL(" UNION ALL ").join(parts)


def _resolve_relation(cur: Any, relation: str) -> dict[str, Any]:
    """Resolve ``relation`` through the catalog, or raise naming it."""
    cur.execute("SELECT to_regclass(%s)::oid", (relation,))
    row = cur.fetchone()
    if row is None or row[0] is None:
        raise LookupError(f"Relation {relation!r} does not exist")
    cur.execute(
        "SELECT n.nspname, c.relname, c.relkind::text "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.oid = %s",
        (row[0],),
    )
    schema, name, relkind = _one(cur)
    return {
        "oid": int(row[0]),
        "schema": schema,
        "name": name,
        "qualified": f"{schema}.{name}",
        "relkind": RELKINDS.get(relkind, relkind),
        "identifier": sql.Identifier(schema, name),
    }


def _columns(cur: Any, oid: int) -> list[dict[str, Any]]:
    """Return a relation's live columns in order, with enum labels if any."""
    cur.execute(
        """
        SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
               CASE WHEN t.typtype = 'e' THEN (
                   SELECT array_agg(el.enumlabel::text ORDER BY el.enumsortorder)
                   FROM pg_enum el WHERE el.enumtypid = t.oid
               ) END
        FROM pg_attribute a
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (oid,),
    )
    return [
        {
            "name": name,
            "type": type_name,
            "not_null": bool(not_null),
            "enum_labels": list(labels) if labels is not None else None,
        }
        for name, type_name, not_null, labels in cur.fetchall()
    ]


def _constraint_columns(cur: Any, oid: int, contype: str) -> list[dict[str, Any]]:
    """Return constraints of one type with their columns in key order."""
    cur.execute(
        """
        SELECT con.conname,
               array_agg(a.attname::text ORDER BY k.ord)
        FROM pg_constraint con
        CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
        WHERE con.conrelid = %s AND con.contype = %s
        GROUP BY con.oid, con.conname
        ORDER BY con.conname
        """,
        (oid, contype),
    )
    return [{"name": name, "columns": list(cols)} for name, cols in cur.fetchall()]


def _foreign_keys(cur: Any, oid: int) -> list[dict[str, Any]]:
    """Return each foreign key with its target and referential actions."""
    cur.execute(
        """
        SELECT con.conname,
               ARRAY(SELECT a.attname::text
                     FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
                     JOIN pg_attribute a
                       ON a.attrelid = con.conrelid AND a.attnum = k.attnum
                     ORDER BY k.ord),
               con.confrelid::regclass::text,
               ARRAY(SELECT a.attname::text
                     FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
                     JOIN pg_attribute a
                       ON a.attrelid = con.confrelid AND a.attnum = k.attnum
                     ORDER BY k.ord),
               con.confupdtype::text, con.confdeltype::text
        FROM pg_constraint con
        WHERE con.conrelid = %s AND con.contype = 'f'
        ORDER BY con.conname
        """,
        (oid,),
    )
    return [
        {
            "name": name,
            "columns": list(columns),
            "references": target,
            "referenced_columns": list(referenced),
            "on_update": FK_ACTIONS[update],
            "on_delete": FK_ACTIONS[delete],
        }
        for name, columns, target, referenced, update, delete in cur.fetchall()
    ]


def _unique_indexes(cur: Any, oid: int) -> list[dict[str, Any]]:
    """Return unique indexes that no primary-key or unique constraint owns."""
    cur.execute(
        """
        SELECT ic.relname, pg_get_indexdef(i.indexrelid)
        FROM pg_index i
        JOIN pg_class ic ON ic.oid = i.indexrelid
        WHERE i.indrelid = %s AND i.indisunique
          AND NOT EXISTS (
              SELECT 1 FROM pg_constraint con WHERE con.conindid = i.indexrelid
          )
        ORDER BY ic.relname
        """,
        (oid,),
    )
    return [{"name": name, "definition": ddl} for name, ddl in cur.fetchall()]


def _count(cur: Any, query: sql.Composable) -> int:
    """Run a single-count query and return its integer result."""
    cur.execute(query)
    return int(_one(cur)[0])


def relation_invariants(
    cur: Any, relation: Mapping[str, Any], role_column: str | None
) -> dict[str, Any]:
    """Read one relation's key, uniqueness, foreign-key, and NULL invariants."""
    columns = _columns(cur, relation["oid"])
    by_name = {column["name"]: column for column in columns}
    primary = _constraint_columns(cur, relation["oid"], "p")
    role = by_name.get(role_column) if role_column else None
    return {
        "relation": relation["qualified"],
        "relkind": relation["relkind"],
        "primary_key": primary[0]["columns"] if primary else None,
        "unique_constraints": _constraint_columns(cur, relation["oid"], "u"),
        "unique_indexes": _unique_indexes(cur, relation["oid"]),
        "foreign_keys": _foreign_keys(cur, relation["oid"]),
        "not_null_columns": [c["name"] for c in columns if c["not_null"]],
        "role_column": (
            {
                "name": role["name"],
                "type": role["type"],
                "enum_labels": role["enum_labels"],
            }
            if role is not None
            else None
        ),
        "columns": columns,
        "row_count": _count(
            cur,
            sql.SQL("SELECT count(*) FROM {}").format(relation["identifier"]),
        ),
    }


def _place_role_records(
    cur: Any, source: sql.Composable, entity_column: str, places_only: bool
) -> dict[str, int]:
    """Count multi-role place pairs and multi-setting chunks (recorded only).

    ``places_only`` limits a unified relation to rows whose entity is a place;
    the place junction holds nothing else.
    """
    place = sql.SQL(
        "EXISTS (SELECT 1 FROM entities e "
        "WHERE e.id = r.entity_id AND e.kind::text = 'place')"
    )
    setting = sql.SQL("r.reference_type::text = 'setting'")
    pair_filter = sql.SQL("WHERE {}").format(place) if places_only else sql.SQL("")
    setting_filter = sql.SQL("WHERE {}").format(
        sql.SQL(" AND ").join([place, setting]) if places_only else setting
    )
    multi_role = _count(
        cur,
        sql.SQL(
            "SELECT count(*) FROM (SELECT 1 FROM {source} r {filter} "
            "GROUP BY r.chunk_id, r.{entity} HAVING count(*) > 1) pairs"
        ).format(
            source=source, filter=pair_filter, entity=sql.Identifier(entity_column)
        ),
    )
    multi_setting = _count(
        cur,
        sql.SQL(
            "SELECT count(*) FROM (SELECT 1 FROM {source} r {filter} "
            "GROUP BY r.chunk_id HAVING count(*) > 1) chunks"
        ).format(source=source, filter=setting_filter),
    )
    return {
        "multi_role_place_pairs": multi_role,
        "chunks_with_multiple_setting_places": multi_setting,
    }


def invariant_specification(
    cur: Any, target: Mapping[str, Any], target_columns: Sequence[str]
) -> dict[str, Any]:
    """Read the machine-readable invariant block for the junctions and target."""
    spec: dict[str, Any] = {}
    for junction in JUNCTIONS:
        relation = _resolve_relation(cur, f"public.{junction.table}")
        block = relation_invariants(cur, relation, junction.role_column)
        if junction.evidence_column:
            block["null_evidence_rows"] = _count(
                cur,
                sql.SQL("SELECT count(*) FROM {} WHERE {} IS NULL").format(
                    relation["identifier"], sql.Identifier(junction.evidence_column)
                ),
            )
        if junction.kind == "place":
            block["recorded_not_enforced"] = _place_role_records(
                cur, relation["identifier"], junction.subtype_column, False
            )
        spec[junction.table] = block
    block = relation_invariants(
        cur, target, "reference_type" if "reference_type" in target_columns else None
    )
    if "evidence" in target_columns:
        block["null_evidence_rows"] = _count(
            cur,
            sql.SQL("SELECT count(*) FROM {} WHERE evidence IS NULL").format(
                target["identifier"]
            ),
        )
    if "reference_type" in target_columns:
        block["recorded_not_enforced"] = _place_role_records(
            cur, target["identifier"], "entity_id", True
        )
    spec["target"] = block
    return spec


def _sort_key(row: Row) -> tuple[Any, ...]:
    """Order rows deterministically with NULLs first in each column."""
    return tuple((value is not None, value) for value in row)


def _examples(
    counter: Counter[Row], columns: Sequence[str], limit: int
) -> list[dict[str, Any]]:
    """Expand a multiset into up to ``limit`` example rows as mappings."""
    examples: list[dict[str, Any]] = []
    for row in sorted(counter, key=_sort_key):
        for _ in range(counter[row]):
            if len(examples) >= limit:
                return examples
            examples.append(dict(zip(columns, row)))
    return examples


def _row_block(
    counter: Counter[Row], columns: Sequence[str], limit: int
) -> dict[str, Any]:
    """Summarize a multiset as its size and example rows."""
    return {
        "count": sum(counter.values()),
        "examples": _examples(counter, columns, limit),
    }


def _project(row: Row, indexes: Iterable[int]) -> Row:
    """Keep the compared columns of a full expected row."""
    return tuple(row[index] for index in indexes)


def build_report(conn: PGConnection, target_name: str, limit: int) -> dict[str, Any]:
    """Read one snapshot and build the parity and invariant report."""
    if limit < 0:
        raise ValueError("limit must not be negative")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT current_database(), current_setting('server_version_num')::int, "
            "(SELECT max(version) FROM schema_migrations)"
        )
        database, server_version, migration_level = _one(cur)
        target = _resolve_relation(cur, target_name)
        target_columns = [column["name"] for column in _columns(cur, target["oid"])]
        missing_required = [
            name for name in REQUIRED_TARGET_COLUMNS if name not in target_columns
        ]
        if missing_required:
            raise ValueError(
                f"Target {target['qualified']} lacks required columns "
                f"{missing_required}; it has {target_columns}"
            )
        compared = [name for name in EXPECTED_COLUMNS if name in target_columns]
        compared_indexes = [EXPECTED_COLUMNS.index(name) for name in compared]

        cur.execute(_expected_rows_sql())
        expected_rows = cur.fetchall()

        target_select = sql.SQL(", ").join(
            sql.SQL("t.{}::{}").format(
                sql.Identifier(name),
                sql.SQL("bigint" if name in INTEGER_COLUMNS else "text"),
            )
            for name in compared
        )
        cur.execute(
            sql.SQL(
                "SELECT {columns}, e.kind::text FROM {target} t "
                "LEFT JOIN entities e ON e.id = t.entity_id"
            ).format(columns=target_select, target=target["identifier"])
        )
        target_rows = cur.fetchall()
        invariants = invariant_specification(cur, target, target_columns)

    kinds = [junction.kind for junction in JUNCTIONS]
    expected_by_kind: dict[str, Counter[Row]] = {kind: Counter() for kind in kinds}
    violations: dict[str, dict[str, Counter[Row]]] = {
        kind: {"subtype_has_no_entity": Counter(), "entity_kind_mismatch": Counter()}
        for kind in kinds
    }
    non_null: dict[str, Counter[str]] = {name: Counter() for name in EXPECTED_COLUMNS}
    for row in expected_rows:
        unified = tuple(row[:5])
        junction_kind, subtype_id, entity_exists = row[5:]
        expected_by_kind[junction_kind][_project(unified, compared_indexes)] += 1
        for index, name in enumerate(EXPECTED_COLUMNS):
            if unified[index] is not None:
                non_null[name][junction_kind] += 1
        detail = (*unified, subtype_id)
        if not entity_exists:
            violations[junction_kind]["subtype_has_no_entity"][detail] += 1
        elif unified[2] != junction_kind:
            violations[junction_kind]["entity_kind_mismatch"][detail] += 1

    target_by_kind: dict[str, Counter[Row]] = {kind: Counter() for kind in kinds}
    unattributed: Counter[Row] = Counter()
    for row in target_rows:
        values, entity_kind = tuple(row[:-1]), row[-1]
        if entity_kind in target_by_kind:
            target_by_kind[entity_kind][values] += 1
        else:
            unattributed[values] += 1

    detail_columns = [*EXPECTED_COLUMNS, "subtype_id"]
    kind_blocks: dict[str, Any] = {}
    parity = not unattributed
    for junction in JUNCTIONS:
        expected = expected_by_kind[junction.kind]
        actual = target_by_kind[junction.kind]
        missing = expected - actual
        extra = actual - expected
        kind_violations = {
            reason: _row_block(rows, detail_columns, limit)
            for reason, rows in violations[junction.kind].items()
        }
        violation_count = sum(block["count"] for block in kind_violations.values())
        kind_parity = not missing and not extra and violation_count == 0
        parity = parity and kind_parity
        kind_blocks[junction.kind] = {
            "junction": junction.table,
            "expected": sum(expected.values()),
            "target": sum(actual.values()),
            "missing": _row_block(missing, compared, limit),
            "extra": _row_block(extra, compared, limit),
            "invariant_violations": {
                "count": violation_count,
                "by_reason": kind_violations,
            },
            "parity": kind_parity,
        }

    column_blocks = {
        name: {
            "carried": name in target_columns,
            "expected_non_null": sum(non_null[name].values()),
            "expected_non_null_by_kind": {kind: non_null[name][kind] for kind in kinds},
        }
        for name in EXPECTED_COLUMNS
    }
    exit_status = EXIT_PARITY if parity else EXIT_MISMATCH
    return {
        "schema_version": SCHEMA_VERSION,
        "database": database,
        "read_only": True,
        "snapshot": {
            "isolation": "repeatable read",
            "server_version_num": server_version,
            "migration_level": migration_level,
        },
        "target": {
            "relation": target["qualified"],
            "relkind": target["relkind"],
            "columns": target_columns,
        },
        "compared_columns": compared,
        "columns": column_blocks,
        "kinds": kind_blocks,
        "unattributed_target_rows": _row_block(unattributed, compared, limit),
        "invariants": invariants,
        "parity": parity,
        "exit_status": exit_status,
    }


def run(
    dbname: str, target: str = DEFAULT_TARGET, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """Open a read-only session on ``dbname`` and return the report."""
    with closing(open_read_only_connection(dbname)) as conn:
        try:
            return build_report(conn, target, limit)
        finally:
            conn.rollback()


def _non_negative(value: str) -> int:
    """Parse a non-negative integer argument."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number


def main(argv: list[str] | None = None) -> int:
    """Print the parity and invariant report as JSON; return the exit status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dbname",
        required=True,
        type=metrics_dbname,
        help="Database to read: save_NN, qa640_*, or ref_*.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=(
            "Relation compared with the junctions (default: %(default)s). "
            "Expected columns it lacks are reported with carried=false and "
            "do not fail the run."
        ),
    )
    parser.add_argument(
        "--limit",
        type=_non_negative,
        default=DEFAULT_LIMIT,
        help="Example rows per list (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    report = run(args.dbname, args.target, args.limit)
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    logger.info(
        "%s vs %s: %s",
        report["database"],
        report["target"]["relation"],
        "parity" if report["parity"] else "MISMATCH",
    )
    return int(report["exit_status"])


if __name__ == "__main__":
    raise SystemExit(main())

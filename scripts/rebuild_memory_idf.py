#!/usr/bin/env python3
"""Rebuild a save database's IDF state under the live PostgreSQL analyzer.

Each IDF corpus row (``memory_idf_corpora``) carries the analyzer key
``pg_catalog.english/v1/<server_version_num>``. Any server version change,
including a patch release that Postgres.app installs by itself, makes the key
stale; narrative and summary writes then fail inside
``sync_memory_idf_document`` and IDF readers raise ``IDFStateError`` until the
corpus is rebuilt. This is that rebuild.

One transaction per database locks the three source tables, locks both corpus
rows, clears the lexeme and document projections, stamps the live key,
advances each corpus epoch, and recomputes every document through the
trigger's own ``sync_memory_idf_document``. It commits only when each corpus's
document count equals its count before the rebuild and each key equals the
live server's; otherwise it rolls back and the command exits non-zero.

Targets mirror ``scripts/migrate.py``: a locked slot is skipped unless
``--write-locked-slot`` is given, and a database that does not exist is
reported and skipped; an explicit ``--dbname`` that does not exist or is
locked without the override fails instead. ``--dry-run`` reads keys and
counts in a read-only session and changes nothing; like the runner's, it
skips a locked slot unless ``--write-locked-slot`` is given.

Usage:
    python scripts/rebuild_memory_idf.py --all --dry-run   # Report; change nothing
    python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot --dry-run
    python scripts/rebuild_memory_idf.py --all             # Template + unlocked slots
    python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
    python scripts/rebuild_memory_idf.py --template
    python scripts/rebuild_memory_idf.py --dbname qa640_clone --json
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.agents.memnon.utils.idf_dictionary import ANALYZER_KEY_SQL  # noqa: E402
from nexus.agents.orrery.reconstruction import (  # noqa: E402
    playable_narrative_predicate,
)
from nexus.database import maintenance_connection  # noqa: E402
from scripts.database_targets import evaluation_dbname  # noqa: E402
from scripts.migrate import (  # noqa: E402
    SLOT_DBS,
    TEMPLATE_DB,
    db_exists,
    get_connection,
    is_db_locked,
)

LOG = logging.getLogger("nexus.rebuild_memory_idf")

# The corpora sync_memory_idf_document serves, in its lock order.
CORPORA: tuple[str, ...] = ("narrative", "retrograde_summary")

# Tables whose rows are the corpora's documents; the rebuild locks all three.
SOURCE_TABLES: tuple[str, ...] = (
    "narrative_chunks",
    "chunk_metadata",
    "retrograde_summaries",
)

# Trigger-owned IDF state installed by migration 114.
IDF_TABLES: tuple[str, ...] = (
    "memory_idf_corpora",
    "memory_idf_documents",
    "memory_idf_lexemes",
)

SYNC_FUNCTION = "sync_memory_idf_document(text, bigint)"

# The recompute. Membership, text, and lexemes come only from the trigger
# function, never from a client-side tokenizer.
RECOMPUTE_SQL = f"""
DO $rebuild$
BEGIN
    PERFORM 1 FROM memory_idf_corpora ORDER BY corpus_kind FOR UPDATE;
    DELETE FROM memory_idf_lexemes;
    DELETE FROM memory_idf_documents;
    UPDATE memory_idf_corpora SET document_count = 0,
        corpus_epoch = corpus_epoch + 1,
        analyzer_version = {ANALYZER_KEY_SQL};
    PERFORM sync_memory_idf_document('narrative', id)
    FROM narrative_chunks ORDER BY id;
    PERFORM sync_memory_idf_document('retrograde_summary', id)
    FROM retrograde_summaries ORDER BY id;
END
$rebuild$
"""


class IDFRebuildError(RuntimeError):
    """The rebuild cannot run or its result breaks an invariant; it rolled back."""


@dataclass(frozen=True)
class CorpusState:
    """One ``memory_idf_corpora`` row."""

    corpus_kind: str
    analyzer_version: str
    document_count: int
    corpus_epoch: int


@dataclass
class CorpusReport:
    """One corpus before, and after a real rebuild, the recompute."""

    corpus_kind: str
    key_before: str
    documents_before: int
    source_documents: int
    stale: bool
    key_after: Optional[str] = None
    documents_after: Optional[int] = None
    # Lexemes added, dropped, or given a new document_frequency; each counts once.
    lexeme_rows_differing: Optional[int] = None


@dataclass
class DatabaseReport:
    """One target database's outcome.

    ``status`` is ``absent`` or ``skipped_locked`` (not touched), ``dry_run``
    (read only), ``empty`` (no corpus rows and no documents: nothing to
    rebuild), ``rebuilt`` (committed), or ``failed`` (rolled back; ``error``
    says why).
    """

    dbname: str
    status: str
    locked: bool = False
    server_key: Optional[str] = None
    corpora: list[CorpusReport] = field(default_factory=list)
    error: Optional[str] = None


def live_key(cur: Any) -> str:
    """Return the analyzer key of the server this session is connected to."""
    cur.execute(f"SELECT {ANALYZER_KEY_SQL}")
    return str(cur.fetchone()[0])


def require_schema(cur: Any, dbname: str) -> None:
    """Fail unless the source tables, IDF tables, and trigger function exist."""
    cur.execute(
        "SELECT name FROM unnest(%s::text[]) AS name "
        "WHERE to_regclass('public.' || name) IS NULL",
        (list(SOURCE_TABLES + IDF_TABLES),),
    )
    missing = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT to_regprocedure(%s) IS NULL", (f"public.{SYNC_FUNCTION}",))
    if cur.fetchone()[0]:
        missing.append(SYNC_FUNCTION)
    if missing:
        raise IDFRebuildError(
            f"{dbname} lacks {', '.join(missing)}; the IDF rebuild needs the "
            "schema of migration 114 (python scripts/migrate.py)"
        )


def corpus_states(cur: Any, *, lock: bool) -> dict[str, CorpusState]:
    """Read the corpus rows, locking them in the trigger's order when asked."""
    cur.execute(
        "SELECT corpus_kind, analyzer_version, document_count, corpus_epoch "
        "FROM memory_idf_corpora ORDER BY corpus_kind" + (" FOR UPDATE" if lock else "")
    )
    return {row[0]: CorpusState(row[0], row[1], row[2], row[3]) for row in cur}


def lexeme_rows(cur: Any) -> dict[str, dict[str, int]]:
    """Return each corpus's ``lexeme -> document_frequency`` rows."""
    rows: dict[str, dict[str, int]] = {kind: {} for kind in CORPORA}
    cur.execute(
        "SELECT corpus_kind, lexeme, document_frequency FROM memory_idf_lexemes"
    )
    for kind, lexeme, frequency in cur:
        rows.setdefault(kind, {})[lexeme] = frequency
    return rows


def differing_lexemes(before: Mapping[str, int], after: Mapping[str, int]) -> int:
    """Count the lexemes added, dropped, or given a new document frequency."""
    return sum(
        1
        for lexeme in before.keys() | after.keys()
        if before.get(lexeme) != after.get(lexeme)
    )


def source_documents(cur: Any) -> dict[str, int]:
    """Count the documents the trigger function admits to each corpus."""
    cur.execute(
        f"""
        SELECT
            (SELECT count(*) FROM narrative_chunks nc
             WHERE EXISTS (SELECT 1 FROM chunk_metadata cm WHERE cm.chunk_id = nc.id)
               AND {playable_narrative_predicate()}),
            (SELECT count(*) FROM retrograde_summaries)
        """
    )
    narrative, summaries = cur.fetchone()
    return {"narrative": narrative, "retrograde_summary": summaries}


def _require_corpora(states: Mapping[str, CorpusState], dbname: str) -> None:
    if set(states) != set(CORPORA):
        raise IDFRebuildError(
            f"{dbname} memory_idf_corpora holds {sorted(states)}; the rebuild "
            f"needs exactly {list(CORPORA)}"
        )


def verify_rebuild(
    cur: Any, before: Mapping[str, CorpusState], server_key: str
) -> dict[str, CorpusState]:
    """Guard a recompute before commit and return the corpus rows it produced.

    Raises ``IDFRebuildError`` when a corpus's document count differs from its
    count before the rebuild, or its key differs from ``server_key``. The
    caller rolls the transaction back.
    """
    after = corpus_states(cur, lock=False)
    problems = []
    for kind in CORPORA:
        was, now = before[kind], after[kind]
        if now.document_count != was.document_count:
            problems.append(
                f"{kind} document_count {was.document_count} -> {now.document_count}"
            )
        if now.analyzer_version != server_key:
            problems.append(
                f"{kind} key {now.analyzer_version} differs from server {server_key}"
            )
    if problems:
        raise IDFRebuildError(
            "IDF rebuild guard failed (rolled back): " + "; ".join(problems)
        )
    return after


def _observe(
    cur: Any, states: Mapping[str, CorpusState], server_key: str
) -> list[CorpusReport]:
    members = source_documents(cur)
    return [
        CorpusReport(
            corpus_kind=kind,
            key_before=states[kind].analyzer_version,
            documents_before=states[kind].document_count,
            source_documents=members[kind],
            stale=states[kind].analyzer_version != server_key,
        )
        for kind in CORPORA
    ]


def _dry_run(dbname: str, report: DatabaseReport) -> None:
    conn = maintenance_connection(dbname, operation="idf_rebuild_dry_run")
    with closing(conn):
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            require_schema(cur, dbname)
            report.server_key = live_key(cur)
            states = corpus_states(cur, lock=False)
            if not states and not any(source_documents(cur).values()):
                report.status = "empty"
                return
            _require_corpora(states, dbname)
            report.corpora = _observe(cur, states, report.server_key)
        conn.rollback()
    report.status = "dry_run"


def _rebuild(dbname: str, report: DatabaseReport, write_locked_slot: bool) -> None:
    conn = maintenance_connection(
        dbname, write_locked_slot=write_locked_slot, operation="idf_rebuild"
    )
    with closing(conn):
        try:
            with conn.cursor() as cur:
                require_schema(cur, dbname)
                cur.execute(
                    f"LOCK TABLE {', '.join(SOURCE_TABLES)} "
                    "IN SHARE ROW EXCLUSIVE MODE"
                )
                report.server_key = live_key(cur)
                before = corpus_states(cur, lock=True)
                if not before and not any(source_documents(cur).values()):
                    conn.rollback()
                    report.status = "empty"
                    return
                _require_corpora(before, dbname)
                corpora = _observe(cur, before, report.server_key)
                lexemes_before = lexeme_rows(cur)
                cur.execute(RECOMPUTE_SQL)
                after = verify_rebuild(cur, before, report.server_key)
                lexemes_after = lexeme_rows(cur)
            for corpus in corpora:
                kind = corpus.corpus_kind
                corpus.key_after = after[kind].analyzer_version
                corpus.documents_after = after[kind].document_count
                corpus.lexeme_rows_differing = differing_lexemes(
                    lexemes_before[kind], lexemes_after[kind]
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    report.corpora = corpora
    report.status = "rebuilt"


def rebuild_database(
    dbname: str, *, dry_run: bool = False, write_locked_slot: bool = False
) -> DatabaseReport:
    """Rebuild (or, with ``dry_run``, inspect) one database's IDF state.

    A missing database is ``absent``; a locked one is ``skipped_locked``
    unless ``write_locked_slot`` is given, even under ``dry_run``. A rebuild
    or schema failure rolls back and is reported as ``failed`` with its error;
    the database is left exactly as it was.
    """
    report = DatabaseReport(dbname=dbname, status="failed")
    if not db_exists(dbname):
        LOG.warning("Database %s does not exist, skipping", dbname)
        report.status = "absent"
        return report
    report.locked = is_db_locked(dbname)
    if report.locked and not write_locked_slot:
        LOG.warning(
            "Database %s is LOCKED (read-only), skipping; rerun with "
            "--write-locked-slot to rebuild it",
            dbname,
        )
        report.status = "skipped_locked"
        return report
    try:
        if dry_run:
            _dry_run(dbname, report)
        else:
            _rebuild(dbname, report, write_locked_slot)
    except (IDFRebuildError, psycopg2.Error) as exc:
        report.status = "failed"
        report.error = " ".join(str(exc).split())
        LOG.error("%s: IDF rebuild FAILED and rolled back: %s", dbname, report.error)
    return report


def render(report: DatabaseReport) -> list[str]:
    """Human-readable lines for one database's report."""
    head = f"{report.dbname}: {report.status}"
    if report.locked:
        head += " [LOCKED]"
    if report.server_key:
        head += f" (server {report.server_key})"
    lines = [head]
    for corpus in report.corpora:
        if corpus.key_after is None:
            line = (
                f"  {corpus.corpus_kind}: key {corpus.key_before}"
                f"{' (stale)' if corpus.stale else ''}, documents "
                f"{corpus.documents_before} (source {corpus.source_documents})"
            )
        else:
            line = (
                f"  {corpus.corpus_kind}: key {corpus.key_before} -> "
                f"{corpus.key_after}, documents {corpus.documents_before} -> "
                f"{corpus.documents_after}, lexeme rows differing "
                f"{corpus.lexeme_rows_differing}"
            )
        lines.append(line)
    if report.error:
        lines.append(f"  error: {report.error}")
    return lines


def run_targets(
    targets: Sequence[str], *, dry_run: bool, write_locked_slot: bool
) -> list[DatabaseReport]:
    """Process each target in order; a failed database does not stop the rest."""
    return [
        rebuild_database(dbname, dry_run=dry_run, write_locked_slot=write_locked_slot)
        for dbname in targets
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, run the targets, print the report, and return the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Rebuild IDF state under the live PostgreSQL analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--all", action="store_true", help="NEXUS_template and every slot"
    )
    target_group.add_argument(
        "--slot", type=int, choices=range(1, 6), metavar="N", help="One slot (1-5)"
    )
    target_group.add_argument(
        "--template", action="store_true", help="NEXUS_template only"
    )
    target_group.add_argument(
        "--dbname",
        type=evaluation_dbname,
        help="An explicitly named qa640_* or ref_* database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report keys and counts in a read-only session; change nothing",
    )
    parser.add_argument(
        "--write-locked-slot",
        action="store_true",
        help="Override read-only policy only for this maintenance session",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the report as JSON on stdout"
    )
    args = parser.parse_args(argv)

    if args.all:
        targets = [TEMPLATE_DB, *SLOT_DBS]
    elif args.slot is not None:
        targets = [f"save_{args.slot:02d}"]
    elif args.template:
        targets = [TEMPLATE_DB]
    else:
        # As scripts/migrate.py does: an explicitly named database must exist
        # (the connection raises otherwise) and a read-only one needs the
        # override, so a typo or a locked name never exits 0 having done nothing.
        with closing(get_connection(args.dbname)) as conn, conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            if cur.fetchone()[0] == "on" and not args.write_locked_slot:
                parser.error(f"Database {args.dbname} is read-only")
        targets = [args.dbname]

    reports = run_targets(
        targets, dry_run=args.dry_run, write_locked_slot=args.write_locked_slot
    )
    failed = [report.dbname for report in reports if report.status == "failed"]
    if args.json:
        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "ok": not failed,
                    "databases": [asdict(report) for report in reports],
                },
                indent=2,
            )
        )
    else:
        for report in reports:
            print("\n".join(render(report)))
    if failed:
        LOG.error("IDF rebuild failed for %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

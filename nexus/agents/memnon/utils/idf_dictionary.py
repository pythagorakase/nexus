"""Commit-current document frequencies owned by the selected PostgreSQL slot."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence

import psycopg2
from psycopg2.extensions import parse_dsn


class IDFStateError(RuntimeError):
    """The requested slot/corpus/analyzer state cannot safely supply weights."""


@dataclass(frozen=True)
class IDFSnapshot:
    """Immutable weights and provenance owned by one database read."""

    corpus_kind: str
    analyzer_version: str
    corpus_epoch: int
    total_docs: int
    weights: Mapping[str, float]

    def score(self, lexeme: str) -> float:
        """Score a lexeme, including a corpus-specific df=0 for unseen terms."""
        return self.weights.get(lexeme, math.log(self.total_docs + 1))


class IDFDictionary:
    """Read transactionally maintained IDF state for one database and corpus.

    Public lookups read committed database state on each call. A caller-owned
    repeatable-read connection can pin query selection to its retrieval snapshot.
    ``idf_dict`` contains only the most recently inspected weights, never a cache.
    """

    CORPUS_KINDS = frozenset({"narrative", "retrograde_summary"})

    def __init__(self, db_url: str, *, corpus_kind: str = "narrative") -> None:
        if corpus_kind not in self.CORPUS_KINDS:
            raise IDFStateError(f"Unsupported IDF corpus kind: {corpus_kind!r}")
        self.db_url = db_url
        self.corpus_kind = corpus_kind
        self._dsn = parse_dsn(db_url)
        self._database = self._dsn.get("dbname")
        if not self._database:
            raise IDFStateError("IDF requires an explicit slot database")
        self.idf_dict: dict[str, float] = {}
        self.total_docs = 0
        self.corpus_epoch: int | None = None
        self.analyzer_version: str | None = None

    def for_corpus(self, corpus_kind: str) -> IDFDictionary:
        """Return an independently scoped reader for another supported corpus."""
        return type(self)(self.db_url, corpus_kind=corpus_kind)

    @contextmanager
    def _cursor(self, connection: Any = None) -> Iterator[Any]:
        try:
            if connection is None:
                with closing(psycopg2.connect(self.db_url)) as conn:
                    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
                    with conn, conn.cursor() as cursor:
                        yield cursor
            else:
                if connection.info.dbname != self._database or any(
                    connection.info.dsn_parameters.get(key) != self._dsn[key]
                    for key in ("host", "hostaddr", "port")
                    if key in self._dsn
                ):
                    raise IDFStateError(
                        "IDF slot mismatch: requested "
                        f"{self._database!r}, received {connection.info.dbname!r}"
                    )
                with connection.cursor() as cursor:
                    yield cursor
        except psycopg2.Error as exc:
            raise IDFStateError(
                f"Database error reading IDF state for {self._database}/{self.corpus_kind}"
            ) from exc

    def _read(
        self,
        terms: Sequence[str] = (),
        *,
        connection: Any = None,
        full_vocabulary: bool = False,
    ) -> tuple[IDFSnapshot, dict[str, list[str]]]:
        if full_vocabulary:
            frequencies_query = """
                SELECT jsonb_object_agg(l.lexeme, l.document_frequency)
                FROM memory_idf_lexemes l WHERE l.corpus_kind = c.corpus_kind
            """
        else:
            # A scalar lookup per input lexeme retains the primary-key access
            # path; an ordinary join can instead scan the complete vocabulary.
            # Unseen lexemes have no row and retain snapshot.score's df=0 rule.
            frequencies_query = """
                SELECT jsonb_strip_nulls(jsonb_object_agg(q.lexeme, (
                    SELECT l.document_frequency FROM memory_idf_lexemes l
                    WHERE l.corpus_kind = c.corpus_kind AND l.lexeme = q.lexeme
                ))) FROM query_lexemes q
            """
        with self._cursor(connection) as cursor:
            # One statement binds the epoch, document count, frequencies and
            # each input's analysis to exactly the same PostgreSQL snapshot.
            # Only explicit diagnostics aggregate the complete vocabulary.
            cursor.execute(
                f"""
                WITH input_terms AS MATERIALIZED (
                    SELECT DISTINCT term,
                        tsvector_to_array(to_tsvector('pg_catalog.english', term))
                            AS lexemes
                    FROM unnest(%s::text[]) AS term
                ), query_lexemes AS (
                    SELECT DISTINCT unnest(lexemes) AS lexeme FROM input_terms
                )
                SELECT c.corpus_kind, c.analyzer_version, c.corpus_epoch,
                    c.document_count,
                    'pg_catalog.english/v1/' || current_setting('server_version_num'),
                    COALESCE(({frequencies_query}), '{{}}'::jsonb),
                    COALESCE((SELECT jsonb_object_agg(term, lexemes)
                        FROM input_terms), '{{}}'::jsonb)
                FROM memory_idf_corpora c WHERE c.corpus_kind = %s
                """,
                (list(terms), self.corpus_kind),
            )
            row = cursor.fetchone()
        if row is None:
            raise IDFStateError(f"Missing IDF corpus state: {self.corpus_kind}")
        kind, analyzer, epoch, total, expected_analyzer, frequencies, analyzed = row
        if kind != self.corpus_kind or analyzer != expected_analyzer:
            raise IDFStateError(
                f"IDF corpus/analyzer mismatch for {self.corpus_kind}; rebuild required"
            )
        if (
            total < 0
            or epoch < 0
            or any(not 0 < frequency <= total for frequency in frequencies.values())
        ):
            raise IDFStateError(f"Invalid IDF counts for corpus {self.corpus_kind}")
        snapshot = IDFSnapshot(
            corpus_kind=kind,
            analyzer_version=analyzer,
            corpus_epoch=epoch,
            total_docs=total,
            weights=MappingProxyType(
                {
                    term: math.log((total + 1) / (frequency + 1))
                    for term, frequency in frequencies.items()
                }
            ),
        )
        # Diagnostics are last-observed only. Callers must score from the local
        # immutable snapshot, because another thread may publish newer state.
        self.total_docs = snapshot.total_docs
        self.corpus_epoch = snapshot.corpus_epoch
        self.analyzer_version = snapshot.analyzer_version
        self.idf_dict = dict(snapshot.weights)
        return snapshot, analyzed

    def build_dictionary(self, force_rebuild: bool = False) -> dict[str, float]:
        """Read current database-owned counts; every call refreshes the snapshot.

        ``force_rebuild`` remains accepted for existing diagnostic callers. It
        does not mutate trigger-owned state or bypass its version checks.
        """
        snapshot, _ = self._read(full_vocabulary=True)
        return dict(snapshot.weights)

    @staticmethod
    def _weight_class(idf: float) -> str:
        if idf > 2.5:
            return "A"
        if idf > 2.0:
            return "B"
        if idf > 1.0:
            return "C"
        return "D"

    def get_idf(self, term: str) -> float:
        """Return the highest IDF among PostgreSQL's lexemes for the term."""
        snapshot, analyzed = self._read([term])
        return max((snapshot.score(lexeme) for lexeme in analyzed[term]), default=0.0)

    def get_idfs(self, terms: Sequence[str]) -> dict[str, float]:
        """Score many source terms against one snapshot and one connection."""
        snapshot, analyzed = self._read(terms)
        return {
            term: max(
                (snapshot.score(lexeme) for lexeme in analyzed[term]), default=0.0
            )
            for term in terms
        }

    def get_weight_class(self, term: str) -> str:
        """Return the diagnostic rarity class for a PostgreSQL-analyzed term."""
        return self._weight_class(self.get_idf(term))

    def generate_weighted_query(
        self,
        query_text: str,
        max_terms: int = 12,
        *,
        connection: Any = None,
        corpus_kind: str | None = None,
    ) -> str:
        """Select rare lexemes and return a safely quoted OR tsquery expression."""
        if corpus_kind is not None and corpus_kind != self.corpus_kind:
            raise IDFStateError(
                f"IDF corpus mismatch: {self.corpus_kind!r} != {corpus_kind!r}"
            )
        if max_terms < 1:
            raise ValueError("max_terms must be positive")
        snapshot, analyzed = self._read([query_text], connection=connection)
        lexemes = analyzed[query_text]
        ranked = sorted(lexemes, key=lambda term: (-snapshot.score(term), term))
        if any(snapshot.score(term) > 3.0 for term in ranked):
            ranked = [term for term in ranked if snapshot.score(term) >= 2.0]
            max_terms = min(max_terms, 5)
        # Quoting keeps compound words, apostrophes and tsquery operators data.
        return " | ".join(
            "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"
            for term in ranked[:max_terms]
        )

    def get_high_idf_terms(
        self,
        query_text: str,
        threshold: float = 2.0,
        stopwords: Sequence[str] = (),
    ) -> list[str]:
        """Return unique lexemes meeting the threshold in the current corpus."""
        snapshot, analyzed = self._read([query_text])
        return [
            term
            for term in analyzed[query_text]
            if term not in stopwords and snapshot.score(term) >= threshold
        ]

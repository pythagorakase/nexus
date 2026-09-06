# PostgreSQL-owned IDF

MEMNON selects rare query lexemes using document frequencies owned by the
selected save database. Migration 114 installs `memory_idf_corpora`,
`memory_idf_documents`, `memory_idf_lexemes`, and transaction-local accounting
triggers. There is no shared pickle or TTL cache.

The narrative corpus contains the rows admitted by the canonical
`playable_narrative_predicate` and the production text search's
`chunk_metadata` join. This excludes the synthetic Retrograde prologue and
rows that have not acquired their retrieval metadata. It deliberately does
not require `state = 'finalized'`: accepted legacy rows also belong. The
separate `retrograde_summary` corpus contains persisted summaries, whose
nonempty text is available to production text search independently of their
embedding readiness. Actor-owned experience recall does not use this IDF
path and is not mixed into either corpus.

Each source insertion, text edit, membership change, deletion, or truncation
updates document counts, unique lexeme frequencies, and a corpus epoch in the
same transaction. Rolled-back edits roll back all accounting. A text edit
advances the epoch even if its lexeme set and highest document ID stay the
same. Before each source statement, both corpus owners are locked in a fixed order,
then row triggers account for changes. This prevents lock-order inversion with
global world-time refresh and transactions writing both corpus kinds. Migration
backfill holds source-table locks until counts and triggers are installed.

Both source documents and query terms use PostgreSQL's `pg_catalog.english`
analyzer. Runtime readers validate the corpus kind, explicit database endpoint,
and stored analyzer version; missing state, invalid counts, and version
mismatches raise `IDFStateError` through retrieval callers. Every lookup reads
current state. Production hybrid retrieval uses one read-only repeatable-read
transaction for IDF selection and both corpus searches, so concurrent commits
cannot mix query weights with a different retrieval snapshot. Query scoring uses
an immutable snapshot local to the request, so overlapping calls on the same
MEMNON instance cannot replace each other's weights. Query-time reads fetch corpus
frequencies only for the PostgreSQL-analyzed input lexemes; unrelated
vocabulary is neither aggregated nor transferred. Diagnostic fields contain the
last-observed weights (a query subset for lookups) and are not used to score queries.

IDF is `log((document_count + 1) / (document_frequency + 1))`, including
`document_frequency = 0` for unseen lexemes. Empty or stopword-only terms score
zero. Query selection retains the existing rare-term thresholds and maximum
term budget, producing safely quoted OR expressions; it does not attach weight
letters to tsquery terms. `get_idfs` analyzes each source keyword independently
and reads the union of its lexemes in one statement and snapshot. The diagnostic
`build_dictionary(force_rebuild=True)` reads all
current counts but does not repair or mutate them.

The analyzer identity includes the exact PostgreSQL version and membership
contract version. An analyzer upgrade or a change to searchable membership
requires an explicit migration that locks the source tables, rebuilds the
projection and counts, and advances the epoch before updating the version.
It must not be repaired implicitly by a retrieval request. Fresh schema-only slot creation initializes empty corpus identities instead
of copying the source story's counts. Existing pickle
files are ignored and can be removed separately.

Validate with:

```sh
NEXUS_RUN_POSTGRES=1 poetry run pytest tests/test_idf_dictionary_pg.py tests/test_presence_boost.py
```

These tests create disposable databases through the shared slot factory; they
exercise migration backfill, cross-slot separation, corpus separation,
concurrent commits, rollback, metadata/prologue membership, edits, deletion,
truncation, analyzer mismatches, production retrieval and PostgreSQL lexemes.
Vocabulary-growth regressions preserve query scores while bounding actual
database output and examined frequency rows by the analyzed input size.

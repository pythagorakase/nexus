# Relationship Entity IDs: Source Checkpoint

Date: 2026-10-08. **Runtime verification is pending.** This is the authorized
source checkpoint for frozen order 836-S6a, based on
`ed5ce5a48409c77b65f0502467ee0c09be4b4a3e` (840-S2's migration 149 and authored
place-point contract). No pytest session, PostgreSQL connection, corpus clone,
fleet survey, migration application, manual replay, gateway, model call, or
owner-service operation was performed for this checkpoint. Black and normal
commit hooks are the only authorized executable checks at this stage; their
results do not establish database correctness.

## Implemented Scope

- Migration 151 refuses stale historical subtype keys before DDL; snapshots
  complete relationship rows and ledger identities; adds six entity-ID columns,
  two composite unique targets, six composite foreign keys and three fill
  triggers; backfills with only the three version triggers disabled; rewrites
  `old_row` additively; and checks row multisets, original ledger values,
  count/nullable maximum, mappings and restored trigger state.
- Replay skips a new relationship entity-ID column only when that key is absent
  from either compared document. Existing relationship keys remain subtype IDs;
  no checkpoint document is migrated.
- Exactly two migration-139 expectations change: the named trigger list gains
  `trg_character_relationships_entity_ids`, and the constraint count rises from
  five to seven. The historical test's rules and other assertions are unchanged.
- `tests/test_relationship_entity_ids_pg.py` authors eleven parametrized cases
  (a source count, not a collection result): five individual migration/writer
  cases, two checkpoint cases, and four corpus cases. Ordinary cases use the
  existing disposable fixture and real seed writers. The stale-key case invokes
  the real wizard transition and proves subtype-ID reuse with new entity IDs
  before requiring migration refusal. It also requires unchanged complete
  snapshots, no stamp, no columns and no rewritten ledger keys after refusal.
- The parity case includes all three tables, a valence UPDATE and a membership
  DELETE. Its oracle compares complete original row multisets and every ledger
  field, preserving count and `max(id)`. An extra empty-ledger case requires
  successful migration with the original `(0, NULL)` ledger identity.
- Corpus cases remain explicitly gated by `requires_corpus`; they request
  `include_data=True` only for the four ordered source slots. They assert every
  live and ledger mapping and require actual checkpoint pairs without drift on
  slots 3 and 4. They have not read any source database.

Source-only frontmatter inventory found no canonical document that declares
any of the four changed source/test paths. No freshness stamp was advanced.
Recompute that closure after merging predecessors. Migration numbers remain
149 (840-S2), 150 (776-S3), and 151 (this lane); 150 is not yet in this checkpoint.
`KNOWN_GAPS` is unchanged. The missing-150 sequence assertion is an expected
future failure only while that predecessor remains absent, never a passed test.

Black was run on the three changed Python files with the shared interpreter,
cleared routing/pytest/runtime opt-ins, exact worktree `PYTHONPATH` and
`nice -n 15`; at one-minute load 4.06 it reported `3 files left unchanged`.
An independent source-only test review found no blocking issue in the named
teardown, full-row parity, writer/constraint cases, real reset, checkpoint
directions or corpus-fixture boundaries. That review performed no imports or
tests. Normal hooks run as part of the enclosing source commit.

## Queued Proof

The [selector list](focused-selectors.txt) contains all 23 frozen focused files,
including card identity, connection lifecycle and character-name replay.
The coordinator owns admission, serial batching/deduplication on the assembled
tree, the full gate and publication. The following are **planned, not run**:

1. Prove `nexus.__file__` points into the admitted worktree using the shared
   interpreter, then run the 23 selectors with `NEXUS_RUN_POSTGRES=1`, exact
   worktree `PYTHONPATH`, `nice -n 15`, and `-p tests.dbname_audit`. Clear inherited
   pytest selection/plugins, libpq routing, runtime/slot/provider/template
   overrides and live/secret-store opt-ins before execution. Keep
   `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset and require
   one-minute load at most 24. Retain every tail, all active guard summaries and
   `dbname audit: owner targets: none`. Any migration-139 test failure is a STOP.
2. Run the same guarded file with `NEXUS_RUN_CORPUS=1` and `-k fleet` only after
   explicit corpus admission. Keep the four cases distinct. The audit covers
   instrumented Python connections; fixture `pg_dump` source reads are outside
   it. A zero owner-target summary is not proof that a corpus dump did not read
   its explicitly named owner source.
3. Run each source-restoring negative control serially, preserving source byte
   hashes before and after and the exact intended failure. Remove only the
   three backfill DISABLE/ENABLE pairs: the populated parity run must fail
   because the migration's ledger count/maximum check refuses extra versions.
   Remove the stale-ledger DO guard: the real-reset test must fail its `(0, 1)`
   refusal requirement. Remove only the replay entity-column map/skip: both
   checkpoint variants must fail on entity-ID drift. Setup errors are not the
   intended control evidence. Restore original bytes before any green proof or
   commit.
4. On four separately owned full-data scratch clones, retain a fresh read-only
   source survey, before/after original-column and `old_row` snapshots, exact
   `cmp` results, migration logs and cleanup evidence. Record real read-only
   checkpoint verdicts before and after for sources 3 and 4, including skipped
   counts and their explanation. Require zero original-data differences and
   zero drift. Stop on stale-key refusal; never repair the ledger.
5. From a migrated disposable clone, retain `obj_description` and
   `col_description` listings and compare all ordered comments byte-for-byte
   with migration 151. Retain standalone migration-comment lint, exception
   dispositions against the admitted main base, document-frontmatter and
   reachability tests, Black, flake8, and mypy with
   `--explicit-package-bases` for the three changed Python files. Compare
   pre-existing-file diagnostics against the same commands on the pinned main
   sources. Normal hooks alone do not satisfy these pending proof requirements.

No test/control tails, current fleet counts, clone comparisons or comments
catalogs are claimed here. The 2026-10-07 migration-143 counts in the SQL header
are explicitly historical; they are not a current survey. The header correctly
names the empty canonical source as `NEXUS_template`, not `template0`.

## Landing Boundary

After all proof and normal predecessor merges, the coordinator applies 151
after 144–150 with no turn in flight, obtains the required backups and restore
proof, runs the ordered fleet migration/locked-slot follow-up and doctor,
then verifies slots 3 and 4 read-only. The frozen reference database remains
excluded. A stale-key refusal is a STOP and cannot authorize historical repair.
The next authorized service startup owes a gateway restart for the replay
change. This lane changes no runtime configuration, UI, relationship key,
writer, reader join, reset cleanup or subtype foreign-key policy.

Codex — GPT-6

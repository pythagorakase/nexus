# 823 operation journal: source checkpoint

Status: implementation and tests authored; runtime proof is pending. No staging
build, sweep, database query, pytest, mypy, provider call, owner operation, service
start or UI build was run for this checkpoint. The coordinator owns the serial
proof slot and the later combined integration gate. This document does not claim
that the earlier nine-lane or current four-lane gate covers this change.

Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. Scope follows the frozen
823-S1 order, including its amendment removing the offline CLI entrypoint
tripwires, and the source refresh for the landed predecessors. The ruled journal,
maintenance target and validation choices are recorded in
[issue 823](https://github.com/pythagorakase/nexus/issues/823#issuecomment-5915951639).
No additional owner choice is required for this slice.

## Change and source review

The existing direct setup paths drop/rebuild a destination before validation and
have no operation journal. `scripts/new_story_setup.py::stage_slot_from_template`
and `stage_slot_clone` instead open and lock a durable JSON operation before
creating a derived staging database. Existing direct initialization and clone
behavior remain, including the direct clone's deliberate lack of migration,
alignment and IDF rebuilding. `tests/test_new_story_setup.py` is byte-identical
to the base. The shared dump helpers retain the original schema selections and
messages; only the two ordered dump-cleanup handlers leave the exception baseline.

`nexus/runtime/slot_operations.py` owns atomic/fsynced journal updates, legal
phase transitions and exact staging-name derivation. `require_authorized`
re-reads filename, operation ID, derived name and phase on every explicit
maintenance checkout. `nexus/api/db_pool.py::get_maintenance_connection` is
unpooled and owns commit, rollback and close. Gameplay admission is unchanged.
Migration and IDF runners revalidate each maintenance connection and retain their
existing behavior with no maintenance target. The IDF runner's existing
`commit_unknown` outcome is preserved; staging accepts only `rebuilt` and never
replays an uncertain commit automatically.

`validate_staging` uses one repeatable-read, read-only database session. It
collects stamp, story, slot, resolved-seat, tail Pass-2 compatibility, IDF analyzer,
replay-invariant and referenced-upload refusals. Missing or invalid story settings
skip only their dependent pin/Pass-2 checks. Database errors propagate. Uploads
remain rooted where the current endpoints serve them, `repo_root() / UPLOADS_DIR`.
A failed/refused database remains until an explicit sweep. Sweep takes the lock,
re-reads ownership and drops only the journal's exact derived name; locked and
unowned matching databases remain untouched.

Landed predecessor contracts retained:

- 822 template staging mints a wizard identity after IDF initialization; clone
  staging forks the copied UUID after migrations/cleanup and removes inherited
  lineage. Direct clone's identity preflight still precedes destination disposal.
- 840's template seed inventory, including Natural Earth, is unchanged. 812's
  template schema copy still includes `public`, `assets` and `ir_eval`; the
  existing full-data clone remains `public` plus `assets` only.
- 810's `require_assets_tables` and ANN behavior are unchanged. The two extension
  allowlist keys now name the extracted helpers, without broadening the allowance.
- 806 receipts, 816 test-provider routing and current model logic are unchanged.
  809's later fresh-NULL pin change must be merged normally and preserved;
  validation resolves precedence without persisting a new pin.
- 811 has not landed at this base. Implementation and runner imports remain in
  `scripts/`; that later move must carry these final helpers and retarget the two
  production-reachable IDF imports described in the coordinator refresh.

Root reviewed the setup extraction, CLI, runners and both test files with no
blocking finding. A second agent independently reviewed journal authorization,
maintenance checkout, validator and sweep with no actionable finding. These are
source reviews, not behavioral proof.

## Source checks completed

The prescribed reachability generator and explanations show exactly four added
production paths: `nexus/runtime/slot_operations.py`,
`scripts/rebuild_memory_idf.py`, `scripts/replay_state.py`, and
`nexus/agents/orrery/replay.py`. The root is `nexus/api/narrative.py:app`; the two
scripts are reclassified as runtime. There are no removed production paths or
changed unreachable exemptions. This is module-import reachability, not proof
that a route invokes staging. Raw generation output is retained privately in
`temp/orders_2026_10_08_codex/coord/823-source-reachability.txt`.

The [canonical closure](canonical-source-closure.json) contains only decision
0040. Its quoted ruling is unchanged and its stamp is refreshed to the base.
The frozen order's statement that no declared source changes is stale because
that decision now declares `scripts/new_story_setup.py`.

Black and normal commit-hook results will be recorded in the checkpoint handoff.
A source follow-up extracts the story, pin and Pass-2 checks plus the lock
attempt into shallow helpers so the disposition headers fit 88 columns. Full
policy prose remains adjacent; marker metadata has no trailing lint suffix.
Aggregate refusal order, the single transaction and propagated database errors
remain unchanged. The uploads comment is split across two lines. No standalone
flake8/mypy or pytest result is claimed here.

## Pending focused proof and controls

Use the shared absolute interpreter, exact worktree `PYTHONPATH`, `nice -n 15`,
load below 24, clean ambient runtime/routing/libpq/PYTEST/live overrides, disabled
Keychain and the normal TEST-provider/receipt/owner guards. Every staging run
must use routed `qa640_` destinations with private journal/uploads directories.
No owner-host staging or sweeping is part of worker authorization.

The required PostgreSQL selection is:

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py tests/test_new_story_setup.py \
  tests/test_postgres_tools.py tests/test_api/test_db_pool_pg.py \
  tests/test_api/test_correspondence_pg.py tests/test_pg_disposable_target.py \
  tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py
```

Add the new journal file, schema-ownership file, current story-identity and
migration/IDF runner consumer tests, reachability and canonical freshness to the
coordinator's deduplicated focused selection. The new real PostgreSQL cases
check unchanged destination OID/marker, source counts/stamps, identities,
pending migration execution, all six refusal categories, post-refusal checkout
revocation, unstamped refusal before migration, stale-IDF rebuild, child-process
journal reuse, held locks, unowned reporting and idempotent sweep. Offline cases
exercise real files/process locks and the exact early CLI errors without mocks.

After focused green, run the two distinct required plants, restoring exact source
bytes between them and before committing proof:

1. Remove only clone staging's `_align_slot_number` call. The played-story clone
   test must refuse with `slot:` because its source is slot 4 and destination is
   slot 5. This corrects the old order's NULL-slot fixture premise.
2. Remove only the validator's Pass-2 check. Both `pass2_missing` and
   `pass2_fingerprint` cases must fail because `StagingRefused` was not raised.

Retain the actual tails, guard/receipt/owner summaries, separate plant hashes and
restoration hashes, static comparisons against the same base, and a real sample
journal from the disposable proof. After fixture cleanup, the read-only postgres
catalog query must return no `qa640_823s1%` database. Broader integration coverage
is coordinator-owned; no separate whole offline gate is claimed.

## Fleet observations and landing

No new owner-fleet survey was performed. The order's October 7 stamp count and
slot-number observations are historical and are not current proof. A fresh
coordinator-admitted read-only survey remains pending; it must name its actual
revision/time and query migration versions, slot numbers, tail baseline schema
and runtime compatibility, and IDF analyzer keys without changing owner data.
Disposable proof uses migrations actually on disk and the script-only 008
exemption rather than a historical count.

No migration, fleet application, config change, UI rebuild or state-surface
regeneration is required by this slice. Owner services remain stopped; the next
authorized gateway startup must load the changed setup/maintenance modules.
There is no replacement/swap, backup policy, automatic quarantine or automatic
routing of current reset/clone/start-setup through staging in this slice.

Codex — GPT-6

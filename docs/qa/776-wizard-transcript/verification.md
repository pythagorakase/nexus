# 776 Slot Wizard Transcript: Verification

Status: the sections down to "Surveys and Landing" are Codex's source checkpoint
at `bf229051`, kept as written except where a bracketed note corrects a claim
that had no recorded command. The executed proof is the
"Integrated-Tree Proof (2026-10-13)" section at the end: the order's PostgreSQL
proof set, the two ordered plants (and a third for the row lock), the PR-time
owner-slot survey, the comment listing from a migrated clone and the static
comparisons, all run on the integrated wave-B tree. The coordinator's steps are
named there. No push, PR, hosted-provider operation or paid call occurred; owner
databases were read only, under `default_transaction_read_only=on`.

Source base: `bf229051e3d046b76ab8d18b34e9ee054a03bbf6` (the 820 source/evidence
prerequisite), with frozen main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`.
[2026-10-13: this checkpoint and `canonical-source-closure.json` still cite
`4ae8b8d2`; the wave-B assembly moved the stamps of decisions 0006, 0022, 0025
and 0053 to `f073b371` (origin/main), and `tests/test_doc_front_matter.py`
passes on the integrated tree below.]
The frozen 776-S3 order and the coordinator's later-migration refresh govern the
change. Migration **150** is fixed: 840 owns 149. The old renumber-to-149 fallback
does not apply, and `KNOWN_GAPS` is unchanged.

## Source Change

At the source base, `nexus/api/conversations.py` selected hosted OpenAI, TEST
memory or state-directory JSON storage by provider. Its create/write/list/delete
paths could not join the cache transaction. `wizard_transcript.py` encoded origin
inside message text, and `new_story_flow.py::switch_wizard_model` copied transcripts
between stores. The introduction claim in `new_story_cache.py` required readers in
`wizard_chat.py`, `setup_endpoints.py` and `slot_endpoints.py` to reconcile separate
transcript and choice commits. The new migration header retains the frozen
file/line references and explicitly dates the historical survey.

`assets.wizard_messages` stores verbatim messages for every provider under one
conversation UUID, with sequence, role, origin and phase recorded at write time.
Both writers lock and validate the cache row first. `record_wizard_reply` inserts
the assistant message and updates its choices on the same cursor and transaction.
The reader skips superseded rows, supports unlimited history and works after the
cache is cleared. It does not lock or depend on that cache. Superseding messages
itself remains the later undo slice.

Starting a wizard mints a UUID; switching its model retains that UUID and all
transcript rows. Model resolution, slot identity and the first-user-message model
lock remain intact. The claim/reconciliation and provider/file/memory store
mechanisms are removed. Welcome and dev/text reply pairs use the atomic writer;
the ordered single-message writes remain single-message writes. A source AST
comparison confirmed `write_wizard_choices`, `repoint_wizard_conversation` and
`test_repoint_commits_model_and_thread_together` remain unchanged. [2026-10-13:
no command was recorded for that comparison; it is now recorded under
"Kept Functions" below.]

Migration 150 creates the table with ten exact table/column comments, discards only
the ruled hosted `conv_` cache case with the existing trait reset, preserves a
UUID cache byte for byte, and refuses retired local/test/NULL identifiers. It makes
no provider call. No existing hosted object is read, copied or deleted.

The obsolete 820 file-store helper, tests, fixture configuration and runtime-doc
clause are removed; Decision 820-Q6 has no remaining subject. Model path anchoring,
raw home-plan values and checksum progress remain intact. The exception baseline
shrinks by exactly the three deleted store-copy cleanup handlers; no marker or
exception-policy fallback is added. No UI, prompt, configuration, CLI, narrative
module, AGENTS or turn-flow source change is included.

## Test Migration and Review

The [source inventory](test-migration-inventory.json) lists each deleted or moved
function and its parameter values. At this source base, **87 source-enumerated
cases leave offline execution: 33 move to PostgreSQL and 54 are deleted because
their storage/claim mechanism is retired**. One additional opt-in live hosted-store
case is deleted; it was not an offline execution. These are source counts, not
collected or executed pytest counts; exact generated parameter IDs remain pending
runtime admission.

New real-store tests cover every registered provider with sockets refused,
verbatim envelope-looking text, origin and phase, sequence/order/limit, superseded
rows, retention after cache clearing, unknown-conversation refusal and one
conversation across model switches. A real `BEFORE UPDATE OF choice_object`
trigger fails after the insert and requires both zero transcript rows and NULL
choices, distinguishing one transaction from split transactions. Further cases
cover duplicate introductions and concurrent committed replies. [2026-10-13:
those cases run one after another and prove only the `choices_recorded` guard,
not the row lock; two-connection lock tests were added, see "Fixes" below.]

Migration tests use independent routed disposable clones, the real migration
runner, complete reset-trait equality, a byte-identical UUID cache, a fresh UUID
restart, all ten comments and complete table/stamp/cache rollback on refusal.
Converted resume/confirmation/conflict tests use real cache and transcript writers.
Only the generation boundary is substituted where the pre-existing test requires
controlled replies. The existing set-designer fixture retains its 816 current-schema
TEST source, routing and owned-process cleanup. Pure cache projections stay offline.

Two fixture values were necessarily adapted to actual PostgreSQL catalog values:
the old `folklore` genre becomes `fantasy`, and the old `duty` trait becomes `allies`.
The partial-character and saved-setting assertions remain. Cache seed helpers use
real writers plus explicit clone-only accepted-checkpoint fields; they do not
replace a cache reader or transcript store.

[2026-10-13: this paragraph originally reported coordinator and peer source
reviews finding no actionable defect, a Black run, a clean reachability report
and hook results in the coordinator handoff, none with a recorded command or
output in this directory. What is known: the later independent Opus review
confirmed eight findings, fixed below; Black, flake8, mypy, the reachability
test and the hooks are recorded with their output in the Integrated-Tree Proof.]

The [canonical closure](canonical-source-closure.json) is decisions 0006, 0022,
0025 and 0053. Quoted rulings and statuses remain unchanged. The first three stamps
move to frozen main; 0053 already carries that stamp from 820 and was reverified.
Recompute freshness after normal predecessor merges rather than restoring old
source or stamps. [2026-10-13: all four now carry `f073b371`, set by the
assembly; the closure file still cites `4ae8b8d2`.]

## Pending Proof

[2026-10-13: superseded by the Integrated-Tree Proof below, which ran everything
this section lists except the coordinator's steps it names.]

The coordinator admits one serial proof session, using the shared interpreter,
the exact worktree import path, `nice -n 15`, load at most 24, private receipts,
denied Keychain/paid access and cleared runtime/routing/libpq/PYTEST/live overrides.
Every PostgreSQL piece includes `-p tests.dbname_audit` and must finish with the
secret-store, receipt and owner-target guard summaries. The source-expanded
selection is recorded in [focused-selectors.json](focused-selectors.json).

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_conversations.py tests/test_api/test_wizard_*.py \
  tests/test_api/test_set_designer_failure.py tests/test_api/test_slot_settings.py \
  tests/test_api/test_slot_mutation_guard.py tests/test_api/test_genesis_ledger_pg.py \
  tests/test_api/test_provider_guard_consumers.py tests/test_config/test_provider_guard.py \
  tests/test_new_story_cache.py tests/test_wizard_opening_presence_pg.py \
  tests/test_cli_wizard_confirmation.py tests/test_new_story_setup.py \
  tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py \
  tests/test_pg_disposable_target.py tests/test_owner_target_guard.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
```

Include the changed runtime-home, canonical freshness and reachability consumers
in the deduplicated coordinator selection. Split at file boundaries as needed;
there is no independent whole-tree/offline-suite rerun claim. The coordinator owns
the combined whole-tree gate. Migration 149 is absent at this isolated source base;
the sequence gate must run again after its predecessor merge. No failure or skip
has been observed or classified in advance.

After actual green proof, run and restore both ordered plants: split the atomic
reply across two connections and require the commit-together test to fail; remove
the migration's cache `DELETE` and require the discard test to fail. Retain exact
failure reasons, byte-identical restoration and the migrated clone's comment
listing. Black, flake8 and sanctioned mypy comparisons against frozen main,
exception-baseline checks, migration-comment check, doc freshness and reachability
are required before publication; permitted source hooks are not substitutes for
the pending behavioral or baseline proof.

## Surveys and Landing

The October 7 save_05 cache observation in the frozen order is historical. There
is no current affected-slot assertion. The coordinator must survey all six owner
targets read-only at PR preparation and immediately before merge, naming each
reset/refusal case and applying the recorded locked-slot rule. Any newly observed
state is evaluated under that ruling; it is not assumed disposable.

Merge after 149 lands. Preserve 776-S1b claim/resume changes, S6 derivation status
and 809 fresh-NULL pin behavior through normal merges. Coordinator migration and
doctor proof precede any gateway start. Owner services remain stopped; the next
authorized startup must use the new gateway. No UI build or state-surface capture
is owed by this slice. Other #776 slices and Cancel policy remain open; eventual
publication says `Refs #776`.

Codex — GPT-6

## Integrated-Tree Proof (2026-10-13)

Fixer: Claude Opus 5.5, worktree `.claude/worktrees/fix-776-s3`, branch
`claude/waveb-fix-776-s3`, cut from integration head `a563203a` (origin/main
`f073b371` plus the wave-B lanes). Scratch files are under the session
scratchpad in `fix-waveb-r3-776-S3/`. Every test command ran with `nice -n 15`,
the shared interpreter and `PYTHONPATH` set to the worktree; the import check
printed `/Users/pythagor/nexus/.claude/worktrees/fix-776-s3/nexus/__init__.py`.
Every PostgreSQL run read the one-minute load first and waited while it was 24
or more; no run had to wait (the highest reading before a run was 23.63, before
plant 2). No connection timeout or lane collision occurred, so no file was
rerun for those reasons.

### Fixes

- `f2c8a395`: migration 150's header cites the facts the order listed and the
  checkpoint left out, at `bf229051` line numbers (hosted `OpenAIProvider`
  client, the state-dir file store, the claim readers and machinery, the
  dev-mode reply split, the old `thread_id` comment); `start_setup`'s docstring
  says it mints a conversation UUID; the chat endpoint raises
  `WizardStateConflict("The saved wizard is missing its conversation.")` (409)
  for a wizard with no conversation ID, before any transcript write, which also
  types `thread_id` as `str` for both `record_wizard_reply` calls; and
  `build_message_history` takes `Sequence[Mapping[str, Any]]`, so the store's
  `WizardMessage` TypedDict type-checks. These clear the three mypy diagnostics
  the lane introduced in `nexus/api/wizard_chat.py`.
- `b669db55`: two two-connection tests in
  `tests/test_api/test_wizard_confirmation_pg.py`.
  `test_introduction_waits_on_the_cache_row_lock`: connection A holds
  `SELECT 1 FROM assets.new_story_creator WHERE id FOR UPDATE`; a thread calls
  `record_wizard_reply(..., introduction=True)`; `pg_stat_activity` shows it
  waiting on a lock; A inserts the winning assistant row, writes
  `choice_object` and commits; the thread raises "already introduced" and one
  assistant row remains. `test_concurrent_messages_take_consecutive_seqs`: two
  `add_wizard_message` calls queue behind A and take seq 1 and 2 with no
  unique violation. The stale-character test now takes `offline_gate_db` and
  asserts `SELECT count(*) FROM assets.wizard_messages` is 0 after its 409.
  `test_setup_endpoint_passes_omitted_model_to_core` asserts the welcome row
  (`[{"role": "assistant", "content": <welcome_message>, "phase": "setting"}]`)
  beside its choices. The sequential tests' docstrings no longer claim lock
  coverage.
- `d7969d47`: `visible_wizard_messages` takes `Sequence[WizardMessage]`
  (clears the resume endpoint's `reversed()` diagnostic); the lock-test holder
  is typed `Any`.

### Runner Used for Every PostgreSQL Piece

`fix-waveb-r3-776-S3/run_pg.sh` (called with a log name and the pytest
arguments):

```sh
#!/bin/zsh
S=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/fix-waveb-r3-776-S3
log=$S/$1; shift
cd /Users/pythagor/nexus/.claude/worktrees/fix-776-s3
n=0
until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ] || [ $n -ge 40 ]; do sleep 30; n=$((n+1)); done
{ echo "uptime: $(uptime)"; echo "head: $(git rev-parse HEAD)"; echo "load-wait loops: $n"; } > $log
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit "$@" >> $log 2>&1
echo "exit=$?" >> $log
```

### Order's PostgreSQL Proof Set (Green, on `d7969d47`)

The order's set (776-S3.md, Proof Expected), with the `test_wizard_*.py` glob
expanded, in three pieces at file boundaries. Piece A1:

```sh
run_pg.sh pg_final_A1.log tests/test_api/test_conversations.py tests/test_api/test_wizard_chat_conflicts.py tests/test_api/test_wizard_chat_validation.py tests/test_api/test_wizard_confirmation_pg.py tests/test_api/test_wizard_confirmation.py tests/test_api/test_wizard_messages_migration_pg.py tests/test_api/test_wizard_model_resolution.py tests/test_api/test_wizard_model_switch.py tests/test_api/test_wizard_resume.py tests/test_api/test_wizard_weird_level.py
```

```text
uptime: 17:25  up 6 days,  4:04, 5 users, load averages: 7.12 11.90 12.26
head: d7969d477911f9822c9c25b18546b0e480226ac0
load-wait loops: 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 77 targets: postgres, qa640_776_hosted_*, qa640_776_uuid_*, qa640_offline_gate_* x74
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
155 passed, 5 warnings in 189.13s (0:03:09)
exit=0
```

Piece A2:

```sh
run_pg.sh pg_final_A2.log tests/test_api/test_set_designer_failure.py tests/test_api/test_slot_settings.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_provider_guard_consumers.py tests/test_config/test_provider_guard.py tests/test_new_story_cache.py tests/test_wizard_opening_presence_pg.py tests/test_cli_wizard_confirmation.py
```

```text
uptime: 17:28  up 6 days,  4:08, 5 users, load averages: 23.44 18.10 14.85
head: d7969d477911f9822c9c25b18546b0e480226ac0
load-wait loops: 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 44 targets: postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa640_offline_gate_* x30, qa655_wizard_0a30e2347c, qa655_wizard_448e4b8ed6, qa655_wizard_4e41543729, qa655_wizard_60eb837c57, qa655_wizard_616bf0e24d, qa655_wizard_cdd2b905f4, qa838_genesis_weird_*, qa838_weird_level_*, test_slot_guard_b62113c7b61146dd8748e3e540b44b6a
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
192 passed, 9 warnings in 154.91s (0:02:34)
exit=0
```

Piece B (includes `tests/test_orrery/test_card_identity.py` and
`tests/test_connection_lifecycle.py`):

```sh
run_pg.sh pg_final_B.log tests/test_new_story_setup.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
```

```text
uptime: 17:31  up 6 days,  4:10, 5 users, load averages: 17.74 18.82 15.78
head: d7969d477911f9822c9c25b18546b0e480226ac0
load-wait loops: 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 31 targets: nexus_m10_fresh_test_26863, nexus_m10_template_test_26863, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_lifecycle_test_provider, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55942 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55943 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55942 (psycopg2), save_04@local:55943 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
281 passed, 2 skipped, 2 warnings in 89.01s (0:01:29)
exit=0
```

The two skips are `tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False]`
and `[True]`, the `requires_corpus` tests (`NEXUS_RUN_CORPUS` unset); listed by
`pytest -q --co -m requires_corpus` over the same files. Migration 149 is on this
tree, so `tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`
passes; no expected failure remains. The same three pieces had also passed on
`b669db55` (155, 192 and 281 passed with 2 skipped; guard and
`owner targets: none` lines present); `d7969d47` changed only
`visible_wizard_messages`'s annotation and a test helper's annotation, and the
pieces were rerun anyway.

### Ordered Plants (Red, on `b669db55`, Restored Byte for Byte)

Each plant is a script in `fix-waveb-r3-776-S3/plants/`; the original file was
copied there first and copied back after the run. In the commands below and in
the later sections, `$S` is the scratch directory
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/fix-waveb-r3-776-S3`,
`$PY` is `/Users/pythagor/nexus/.venv/bin/python`, and the working directory is
the worktree root. Before the plants, `shasum -a 256` gave
`d79d7781…9b091c` for `nexus/api/new_story_cache.py` and `0f80ae95…f36811` for
`migrations/150_wizard_messages.sql`; each restoration is proved by
`git diff --quiet` on that path.

Plant 1, `plant_split_reply.py`: `record_wizard_reply` closes its first
`_cache_connection` block after the transcript INSERT and runs the
`choice_object` UPDATE in a second `_cache_connection` block.

```sh
/Users/pythagor/nexus/.venv/bin/python $S/plants/plant_split_reply.py && git diff --stat; env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit "tests/test_api/test_wizard_confirmation_pg.py::test_reply_and_choices_commit_together" > $S/plant1.log 2>&1; echo exit=$?; cp $S/plants/new_story_cache.py.orig nexus/api/new_story_cache.py; git diff --quiet -- nexus/api/new_story_cache.py && echo "restored: git diff --quiet nexus/api/new_story_cache.py exit 0"
```

```text
 nexus/api/new_story_cache.py | 2 ++
 1 file changed, 2 insertions(+)
exit=1
restored: git diff --quiet nexus/api/new_story_cache.py exit 0
>           assert cur.fetchone()[0] == 0
E           assert 1 == 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_api/test_wizard_confirmation_pg.py::test_reply_and_choices_commit_together[False]
FAILED tests/test_api/test_wizard_confirmation_pg.py::test_reply_and_choices_commit_together[True]
2 failed, 5 warnings in 4.95s
```

Both parameters fail on the transcript count: the INSERT committed although the
proof trigger refused the choices.

Plant 2, `plant_drop_delete.py`: removes
`DELETE FROM assets.new_story_creator WHERE id = TRUE;` from migration 150's
`DO` block.

```sh
/Users/pythagor/nexus/.venv/bin/python $S/plants/plant_drop_delete.py && git diff --stat; env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit "tests/test_api/test_wizard_messages_migration_pg.py::test_migration_150_discards_only_hosted_thread_wizards" > $S/plant2.log 2>&1; echo exit=$?; cp $S/plants/150_wizard_messages.sql.orig migrations/150_wizard_messages.sql; git diff --quiet -- migrations/150_wizard_messages.sql && echo "restored: git diff --quiet migrations/150_wizard_messages.sql exit 0"
```

```text
 migrations/150_wizard_messages.sql | 1 -
 1 file changed, 1 deletion(-)
exit=1
restored: git diff --quiet migrations/150_wizard_messages.sql exit 0
>               assert _cache_bytes(hosted) is None
E               assert '{"id":true,"thread_id":"conv_776_disposable_hosted","target_slot":5,"setting_genre":null,"setting_secondary_genres":n...ult":null,"setting_confirmed":false,"character_confirmed":false,"character_revision_pending":false,"weird_level":null}' is None
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_776_hosted_*, qa640_776_uuid_*
dbname audit: owner targets: none
FAILED tests/test_api/test_wizard_messages_migration_pg.py::test_migration_150_discards_only_hosted_thread_wizards
1 failed, 5 warnings in 4.83s
```

Plant 3 (added for the row-lock finding), `plant_drop_lock.py`: both transcript
writers call `read_cache_cursor(cur, lock=False)`.

```sh
/Users/pythagor/nexus/.venv/bin/python $S/plants/plant_drop_lock.py && git diff --stat; env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit "tests/test_api/test_wizard_confirmation_pg.py::test_introduction_waits_on_the_cache_row_lock" "tests/test_api/test_wizard_confirmation_pg.py::test_concurrent_messages_take_consecutive_seqs" > $S/plant3.log 2>&1; echo exit=$?; cp $S/plants/new_story_cache.py.orig nexus/api/new_story_cache.py; git diff --quiet -- nexus/api/new_story_cache.py && echo "restored: git diff --quiet nexus/api/new_story_cache.py exit 0"
```

```text
 nexus/api/new_story_cache.py | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
exit=1
restored: git diff --quiet nexus/api/new_story_cache.py exit 0
>                   late.result(timeout=30)
E       psycopg2.errors.DeadlockDetected: deadlock detected
E       CONTEXT:  while updating tuple (0,1) in relation "new_story_creator"
E                       Failed: 2 writer(s) never waited on the cache row lock
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_api/test_wizard_confirmation_pg.py::test_introduction_waits_on_the_cache_row_lock
FAILED tests/test_api/test_wizard_confirmation_pg.py::test_concurrent_messages_take_consecutive_seqs
2 failed, 5 warnings in 36.00s
```

Without the lock, the late introduction does not wait: it writes seq 1 and then
deadlocks against the holder instead of being refused, and the two message
writers never queue.

### PR-Time Owner-Slot Survey (Read-Only, 2026-10-13 17:14 CDT)

```sh
for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do echo "== $db"; PGOPTIONS='-c default_transaction_read_only=on' psql -d $db -Atc "SELECT thread_id, setting_confirmed, updated_at FROM assets.new_story_creator" 2>&1; done
```

```text
== NEXUS_template
== save_01
== save_02
== save_03
== save_04
== save_05
conv_6ab3f072abc081948e94e1f5c8b8c0be000d0e6233839786|f|2026-09-23 14:04:12.670662-04
```

Supporting reads under the same read-only setting: every database's highest
numeric `schema_migrations` version is 148, none has a `150` stamp or an
`assets.wizard_messages` table; `save_05` has 0 narrative chunks, 0 characters,
0 `genesis_runs` rows, NULL `global_variables.setting` and `base_timestamp`, and
model `gpt-6-astra`.

Verdict under Decision 776-Q1: migration 150 would discard exactly one wizard,
`save_05`'s (`conv_6ab3…`, unconfirmed setting, 2026-09-23), which matches the
order's October 7 observation; it would refuse no database. `NEXUS_template` and
`save_01` to `save_04` have no cache row and are left unchanged, so the locked
`save_01` needs no exception. The ruling's second survey, immediately before
merge, is the coordinator's step.

### Comment Listing From a Migrated Clone (on `b669db55`)

```sh
DB=qa640_776s3_cols; createdb -T NEXUS_template $DB && echo created && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -c "
from nexus.maintenance.migrate import migrate_database
print(migrate_database('$DB', skip_locked=False))
"
psql -d $DB -Atc "SELECT version FROM schema_migrations WHERE version IN ('149','150','151') ORDER BY 1"
psql -d $DB -At -F ' | ' -c "SELECT 'TABLE assets.wizard_messages', obj_description('assets.wizard_messages'::regclass, 'pg_class') UNION ALL SELECT * FROM (SELECT 'COLUMN assets.wizard_messages.' || a.attname, col_description(a.attrelid, a.attnum) FROM pg_attribute a WHERE a.attrelid = 'assets.wizard_messages'::regclass AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum) c UNION ALL SELECT 'COLUMN assets.new_story_creator.thread_id', col_description('assets.new_story_creator'::regclass, (SELECT attnum FROM pg_attribute WHERE attrelid = 'assets.new_story_creator'::regclass AND attname = 'thread_id'))"
```

```text
created
(3, 0)
149
150
151
TABLE assets.wizard_messages | Wizard transcript for every provider, one row per message, keyed by the conversation UUID that assets.new_story_creator.thread_id names; add_wizard_message and record_wizard_reply write it under the wizard cache row lock. Rows are kept after the wizard cache is cleared.
COLUMN assets.wizard_messages.conversation_id | Conversation UUID minted by start_setup; assets.new_story_creator.thread_id holds it as text while the wizard runs.
COLUMN assets.wizard_messages.seq | Position in the conversation from 1, assigned as one more than the highest seq while the writer holds the wizard cache row lock.
COLUMN assets.wizard_messages.role | user for player or wizard-control input; assistant for a wizard reply.
COLUMN assets.wizard_messages.origin | Provenance of a user message: user for player text, wizard_control for a message the client sends for the player. NULL exactly for assistant messages.
COLUMN assets.wizard_messages.content | Model-facing message text, stored verbatim.
COLUMN assets.wizard_messages.phase | WizardCache.current_phase() in the writing transaction (setting, character, seed or ready); written at message time and never recomputed.
COLUMN assets.wizard_messages.created_at | Operational wall-clock insert time; never story time.
COLUMN assets.wizard_messages.superseded_at | NULL in migration 150; the #776 undo slice (Decision 776-Q2: mark superseded) writes it. Transcript readers skip rows where it is set.
COLUMN assets.new_story_creator.thread_id | Wizard conversation UUID as text, written by start_setup; assets.wizard_messages holds its transcript. Migration 150 removed rows that named a hosted OpenAI conversation (conv_ prefix).
```

Byte comparison (`fix-waveb-r3-776-S3/compare_comments.py`: extracts each
`COMMENT ON ... IS '...'` literal from the migration, undoubles `''`, compares it
with the catalog value, and checks it appears verbatim in backticks in the
order):

```sh
PYTHONPATH= /Users/pythagor/nexus/.venv/bin/python -I $S/compare_comments.py qa640_776s3_cols migrations/150_wizard_messages.sql /Users/pythagor/nexus/temp/orders_2026_10_07/776-S3.md
```

```text
assets.wizard_messages: catalog==migration True; verbatim in order True
assets.wizard_messages.conversation_id: catalog==migration True; verbatim in order True
assets.wizard_messages.seq: catalog==migration True; verbatim in order True
assets.wizard_messages.role: catalog==migration True; verbatim in order True
assets.wizard_messages.origin: catalog==migration True; verbatim in order True
assets.wizard_messages.content: catalog==migration True; verbatim in order True
assets.wizard_messages.phase: catalog==migration True; verbatim in order True
assets.wizard_messages.created_at: catalog==migration True; verbatim in order True
assets.wizard_messages.superseded_at: catalog==migration True; verbatim in order True
assets.new_story_creator.thread_id: catalog==migration True; verbatim in order True
10 comments; all equal: True
```

`dropdb qa640_776s3_cols` printed `dropped`, and a `pg_database` query for
`qa640_776s3%` returned no row.

### Static and Repository Checks

Files: every `.py` file the lane changed plus the two this fix changed
(`nexus/api/pydantic_ai_utils.py`, `tests/test_api/test_wizard_model_resolution.py`),
22 in all, listed in `fix-waveb-r3-776-S3/pyfiles.txt`. Baseline: the same paths
from `git archive origin/main nexus scripts tests pyproject.toml .flake8`
(`f073b371`) in `fix-waveb-r3-776-S3/base_tree/`.

- Black, on `d7969d47`: `nice -n 15 $PY -m black --check $(cat pyfiles.txt)` →
  `All done! ✨ 🍰 ✨` / `22 files would be left unchanged.`
- flake8, on `d7969d47`: head 27 diagnostics, origin/main 29 (run with the
  worktree's `.flake8`). Compared without line numbers, head has none that
  origin/main lacks; origin/main's two extra are `wizard_chat.py` E501 lines the
  lane deleted. The one text difference is the pre-existing
  `tests/test_api/test_provider_guard_consumers.py` F811 `mock_openai_server`,
  whose "from line" moved from 13 to 11.
- mypy, on `d7969d47`:
  `$PY -m mypy --explicit-package-bases $(cat pyfiles.txt)` →
  `Found 132 errors in 7 files (checked 22 source files)`; origin/main →
  `Found 157 errors in 7 files (checked 21 source files)`. Compared without line
  numbers, the only head-only line is
  `tests/test_api/test_wizard_confirmation_pg.py: error: Argument "artifact_token" to "confirm_artifact" has incompatible type "str | None"; expected "str"`
  at line 477, an unchanged line: the same diagnostic exists on origin/main at
  line 473 with the type text `"str | Any | None"` (head has 4 + 1, origin/main
  5, of this diagnostic). The lane's three new `wizard_chat.py` diagnostics
  (`record_wizard_reply` `expected_thread_id` at 577 and 758,
  `build_message_history` at 553) are gone; `wizard_chat.py` went from 23
  diagnostics on the integrated head `a563203a` to 10.
- `PYTHONPATH=$PWD $PY scripts/check_migration_comments.py` (on `b669db55`) →
  `OK: every object created after migration 129 has a comment.`
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
  (on `b669db55`) → `OK: exception disposition coverage and shrink-only baseline verified.`
  `git diff d59b2fca 2b11b961 -- config/exception_disposition_baseline.json`
  removes exactly three entries: `ConversationsClient.delete_thread` and two
  `_remove_partial_copy` handlers. No marker was added.
- `$PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py`
  (on `d7969d47`) → `120 passed, 5 warnings in 19.11s`, with the guard line.
- Pre-commit hooks on each fix commit: regenerate-orrery-catalog Passed,
  validate-config Passed, check-migration-comments Passed (`f2c8a395`; skipped
  with no migration staged on the others), check-exception-dispositions Passed.

### Kept Functions

```sh
/Users/pythagor/nexus/.venv/bin/python -I $S/ast_unchanged.py d59b2fca 2b11b961; /Users/pythagor/nexus/.venv/bin/python -I $S/ast_unchanged.py d59b2fca HEAD
```

```text
nexus/api/new_story_cache.py::write_wizard_choices unchanged d59b2fca..2b11b961: True
nexus/api/new_story_cache.py::repoint_wizard_conversation unchanged d59b2fca..2b11b961: True
tests/test_api/test_wizard_model_switch.py::test_repoint_commits_model_and_thread_together unchanged d59b2fca..2b11b961: True
nexus/api/new_story_cache.py::write_wizard_choices unchanged d59b2fca..HEAD: True
nexus/api/new_story_cache.py::repoint_wizard_conversation unchanged d59b2fca..HEAD: True
tests/test_api/test_wizard_model_switch.py::test_repoint_commits_model_and_thread_together unchanged d59b2fca..HEAD: True
```

(`HEAD` was `d7969d47`; the script compares `ast.dump` of each named function.)

### Offline Suites (on `d7969d47`, `NEXUS_RUN_POSTGRES` Unset)

`run_offline.sh` is `run_pg.sh` without the load loop and `-p tests.dbname_audit`,
with `-u NEXUS_RUN_POSTGRES` and `perl -e 'alarm 580; exec @ARGV'`. A single
`tests --ignore=tests/test_api --ignore=tests/test_orrery` run reached about 10%
in 100 seconds, so it was stopped and split: the top-level `tests/*.py` files in
three lists, then the subdirectories.

| Piece | Tail |
| --- | --- |
| top-level list 1 (52 files) | `706 passed, 161 skipped, 7 warnings, 1 error in 345.23s` |
| top-level list 2 | `695 passed, 188 skipped, 8 warnings in 42.60s` |
| top-level list 3 | `751 passed, 239 skipped, 7 warnings in 85.02s` |
| `tests/config tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util` | `1045 passed, 89 skipped, 7 warnings in 146.68s` |
| `tests/test_api` | `549 passed, 341 skipped, 7 warnings in 31.92s` |
| `tests/test_orrery` | `1 failed, 1363 passed, 1189 skipped, 7 warnings in 12.69s` |

All six tails carry `secret-store guard: active; nexus-api: denied; disposable keychain: denied`.
The one error in list 1 is `ERROR tests/scheduler_helpers.py::test_provider_config`
(`fixture 'base_url' not found`): list 1 named the helper module
`tests/scheduler_helpers.py` explicitly, which a directory run never collects
(pytest's default `python_files`); lists 2 and 3 were filtered to `test_*.py`
and `*_test.py`. The `tests/test_orrery` failure is in a file this lane did not
change and is reported, not fixed:

```text
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
>           OrreryEpistemicsSettings(claim_event_types=["ate"])
E           pydantic_core._pydantic_core.ValidationError: 1 validation error for OrreryEpistemicsSettings
E           claim_event_types
E             Value error, claim_event_types contains event types emitted by background branches: ['ate'] [type=value_error, input_value=['ate'], input_type=list]
E       AssertionError: Regex pattern did not match.
E        Regex: 'without birth-role policies.*ate'
```

The background-branch check in `nexus/config/settings_models.py` now runs
before the birth-role check and `ate` is emitted by a background branch; both
come from `9641f184` ("Author branch attention metadata and Backstage styling",
merged by `28e7070b`, the 777 shell), not from this lane.

### Coordinator's Steps

- The whole-tree PostgreSQL gate on the final union.
- The survey of every owner slot immediately before merge (Decision 776-Q1).
- `scripts/migrate.py --all`, then `--slot 1 --write-locked-slot`, then
  `nexus doctor`, after merge and before any gateway start; a gateway restart
  when the owner's services run again.
- State-surface regeneration is not owed by this slice (no `ui/` change).

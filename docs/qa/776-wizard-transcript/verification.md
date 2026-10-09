# 776 Slot Wizard Transcript: Source Checkpoint

Status: source and tests are authored and independently source-reviewed. All
behavioral proof, PostgreSQL execution, negative controls and current fleet
surveys are pending. This checkpoint is not a completed gate or landing approval.
No push, PR, hosted-provider operation, paid call or owner database access occurred.

Source base: `bf229051e3d046b76ab8d18b34e9ee054a03bbf6` (the 820 source/evidence
prerequisite), with frozen main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`.
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
`test_repoint_commits_model_and_thread_together` remain unchanged.

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
cover duplicate introductions and concurrent committed replies.

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

Coordinator review covered all seven product modules and migration 150. Independent
peer review covered the four core store/model-switch/atomic-reply/migration test
files; the implementer also inspected the peer-authored converted helper slice.
No actionable source defect remained.
These reviews do not establish runtime behavior. Black formatted the 20 changed
Python files. The prescribed source reachability report has no findings and needs
no baseline change; it explicitly does not prove route reachability. Normal-hook
results and exact checkpoint head are recorded in the
coordinator handoff. Broader static baseline comparisons are still pending.

The [canonical closure](canonical-source-closure.json) is decisions 0006, 0022,
0025 and 0053. Quoted rulings and statuses remain unchanged. The first three stamps
move to frozen main; 0053 already carries that stamp from 820 and was reverified.
Recompute freshness after normal predecessor merges rather than restoring old
source or stamps.

## Pending Proof

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

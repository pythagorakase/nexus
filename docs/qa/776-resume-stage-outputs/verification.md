# 776 Saved Stage Outputs: Phase 1 Source Checkpoint

Status: source and Phase 1 tests are authored; runtime proof is pending. This is
not **READY FOR PROBE**. The source-only dispatch permits Black, prescribed
generators and normal hooks, but no pytest, PostgreSQL work, mypy, owner queries,
services, model reads or paid calls. No push or PR has occurred.

Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The frozen 776-S1b order
and coordinator's genesis refresh govern this slice. The whole-run fingerprint
and single-open-run choices are settled in [the recorded mechanism rulings](https://github.com/pythagorakase/nexus/issues/776#issuecomment-5922751146).
Phase2 still requires its separate explicit confirmation; full campaign approval
is not paid-probe permission.

## Source Change

At the base, every transition created a fresh run, no reader consumed saved
outputs, no fingerprint was stored, and cache deletion prevented a wizard retry
after an embedding failure. New ledger readers retain the full saved stage
records. The fingerprint includes transition JSON, weird level, resolved effective
model, trait-input settings, wizard retry budget and all Orrery settings.

A failed, matching, unpersisted run contributes only its longest valid saved
prefix. Derivation envelopes, packet schema version and current seed/expansion
models are validated before any provider boundary. Invalid output fails the new
run with no copied outputs; a subsequent request rebuilds. A persistence-content
block reuses only derivation, packet and seeds, rebuilding expansion. Reuse writes
this run's stage/detail/output rows with `reused_from`; it does not emit duplicate
progress, invoke a generator or fabricate generation timing.

`genesis_slot_claim` owns one pooled connection and a session advisory lock for
the run, committing immediately after acquisition. Lost claimants never prepare
cache data or write the request's weird level. Unlock failure closes the session
before propagating, so an uncertain lock cannot return to the pool. The wrapper
rereads the latest run after winning as well as before trying the claim, covering
a prior owner that finishes in that interval. A stopped owner's `running` row is
marked interrupted only after winning the claim; waiting requests follow the
winner's new run instead of returning the interrupted row.

Persistence saves the answer surface in the world transaction. A post-commit
retry reads that output, copies the prior stages and embeds only pending IDs with
NULL embedding stamps. It does not read the wizard cache or rebuild the world.
Completed responses are reconstructed from the ledger and current world. The
route keeps writable-slot admission first, invokes cache preparation only for
the claim owner, preserves HTTP errors and returns the required run ID.

Narrative `nexus continue` now checks the run status before scheduling a turn.
It finishes a running/failed genesis transition first, retains its Retrograde
answer, then continues. Missing or unknown `run_status` fails loudly. Existing
CLI model, chunk paging, home, receipts and transport behavior remain intact.

No bootstrap ownership, Cancel behavior, client idempotency, wait-screen stage
vocabulary or UI element is added. Joiners can retain stationary progress pips
under the recorded Q5 boundary; S6/S2 remain separate work.

## Phase 1 Test Source

New pure fingerprint coverage changes every input independently. New real
PostgreSQL cases drive the route on the disposable staged world to prove malformed
saved output refuses before a provider boundary and that the next request starts
fresh. A real child holds the session claim, is SIGKILLed, and the parent must
acquire it within the bounded wait. The child, its log and its routed database are
owned by the test; no owner gateway or provider is used.

Existing ledger assertions now require the derivation envelope and fingerprint.
The wizard weird-level boundary fixture invokes the new `prepare` callback and
returns run/world identity; it records the new fingerprint writer without opening
a database. TEST-skip equalities include the ordered reused-stage field.

The coordinator resolved an internal example ambiguity in item4: its skipped
`reused_stages: []` is the usual no-reuse example, while its stated rule and item6
require truthful actual reuse. A skipped direct answer therefore uses
`list(reused)`. A new Phase1 disposable regression disables Retrograde but keeps
trait derivation enabled, seeds a matching failed derivation output, then compares
the direct response and ledger reconstruction with `reused_stages=["derivation"]`.
No new owner choice is needed, and ordinary TEST-skipped runs still report `[]`.


Five CLI consumer files were adapted: `tests/test_cli.py`,
`tests/test_cli_model_selection.py`, `tests/test_cli_choice_http.py`,
`tests/test_cli_session_wait.py` and `tests/test_cli_generation_http.py`.
Narrative fakes serve legitimate idle/done ledger records while retaining existing
write/model/wait assertions. The two new real-loopback cases assert failed
embedding causes transition POST before continue POST, and done genesis causes
only the continue POST. No assertion was removed to hide the added status read.

## Pending Proof

Under the coordinator's serial slot, clear inherited runtime/routing/libpq,
PYTEST and live overrides; use the exact worktree import path, shared interpreter,
`nice -n 15`, load below24, denied Keychain/paid-provider access and private
receipts. The frozen Phase1 PostgreSQL command is:

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_genesis_ledger_pg.py \
  tests/test_api/test_genesis_fingerprint.py \
  tests/test_api/test_wizard_weird_level.py \
  tests/test_api/test_mock_wizard_responses.py \
  tests/test_api/test_route_capabilities.py \
  tests/test_orrery/test_retrograde_orchestrator.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
```

Also include the five changed CLI files and doc/reachability consumers in the
coordinator's deduplicated focused selection. Record guard/receipt/audit summaries,
actual failures and cleanup. No standalone full offline gate is claimed; broader
integration is coordinator-owned. Black, normal-hook results and their exact
checkpoint head belong in the handoff; flake8/mypy baseline comparisons remain
pending, as do the ordered read-only fleet ledger counts. The October7 empty
ledger survey is historical, not a current unaffected-slots claim.

Only after actual Phase1 proof may this lane report READY FOR PROBE. These six
capture-dependent Phase2 cases remain unavailable and unrun:

- Successful four-stage reuse without generation.
- Changed weird/model input rebuilding.
- Concurrent repeated POSTs joining one run.
- A killed owner followed by two joiners.
- Persistence-content refusal rebuilding expansion only.
- Cache-free completion after committed embedding failure.

The three restoring source plants also require that captured bundle: disable
reuse, bypass the claim, and read the cache before claiming. No synthetic bundle
or weakened validator substitutes for a real capture. The live probe is not
implemented or run in this Phase1 source checkpoint; no usage or token result is
claimed. Phase2 confirmation must identify the ready head, selected model, one-run
bound, private routed clone/8021 plan, exact usage evidence and cleanup. Any
failure before capture stops; persistence winning the kill race retains the
capture and stops; a second paid run is never automatic.

## Predecessors and Landing

This base retains822 identity and836 unified-reference behavior in the unchanged
mapper. Its cache deletion still follows world commit. Future809 fresh-NULL pin
and typed-reader changes must be merged normally without restoring old setup
resolution; fingerprint the already resolved model. Preserve820 anchored paths
and private state plus812 artifact admission in the later live-probe plan.
Any840 expansion-schema change must validate against the current models; never
patch a captured output or assume another paid capture is authorized.

The [canonical closure](canonical-source-closure.json) is decisions0009,0016,
0017 and0024. Their quoted rulings/statuses remain unchanged; stamps move to4ae.
Neither AGENTS nor turn-flow currently declares a changed source for this slice.
No migration/fleet application, config change, UI rebuild or state capture is
owed. Owner services stay stopped; the next authorized startup must use the new
gateway code. Publication remains held through Phase2's explicit disposition.

Codex — GPT-6

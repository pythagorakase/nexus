# Home Anchors, Wizard Store, and Checksum Progress

Implemented frozen 820-S2 + S3 on main
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`, after fast-forwarding the clean
existing `claude/820-home-anchors` placeholder. Refs #820; its other slices
and open owner questions remain outside this change.

## Contract and Current-Shape Adaptation

- `nexus/runtime/home.py:81` enumerates 14 model-path fields in order: local
  model directory, the one runtime embedder, production reranker, eight
  sorted offline embedding candidates, and three sorted offline rerankers.
  `anchor_model_paths` at line 105 preserves validated configured strings and
  anchors nonempty relative values once. Absolute and symlink spellings stay
  intact; empty paths stay empty.
- `nexus/config/loader.py:236` routes both supported format loaders through
  anchoring inside the existing failure-receipt boundary. The 816
  TEST-provider database overlay is unchanged. The five model-path readers
  and checkout-relative artifact-lock locator are unchanged.
- `nexus/runtime/home_plan.py:323` still inventories only its two production
  model keys and reads their raw strings. Its two-pass inventory at line 485
  preserves claimed-path ownership, missing entries, rewrites, checksums and
  final ordering. Progress includes receipts, regular-file bytes, symlinks
  as entries, each checksum block, and each completed entry.
- `nexus/api/conversations.py:44` locates future file-backed wizard threads at
  the configured base state directory, without a gateway-port namespace.
  The store now requires an explicit directory. The API fixture supplies a
  real private TOML configuration instead of patching a module constant.
- `nexus/cli.py:4428` renders a terminal stderr progress line only for text
  output, and `run_home` closes it in `finally`. JSON/stdout remain unchanged;
  there is no checksum-skipping flag.

Before editing, an existence-only check confirmed the main checkout's
`temp/wizard_threads` path was absent. The final check also used `lexists`,
confirming no dangling link. No transcript migration or owner file deletion
was performed. Only the negative control's explicitly created worktree
thread file was removed after its test identified it.

## Focused PostgreSQL Proof

The package import resolved to this worktree's `nexus/__init__.py`. The
one-minute load was 3.41 before the run; every test process used `nice -n 15`
and the shared interpreter. One serial test slot was held for this run and
its controls, then released. From this worktree:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD \
  nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -rs \
  -p tests.dbname_audit \
  tests/test_runtime_home.py tests/test_embedding_artifacts.py \
  tests/test_api/test_conversations.py tests/test_api/test_wizard_model_switch.py \
  tests/test_api/test_local_inference.py tests/test_api/test_local_models_endpoints.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_runtime/test_receipts.py tests/test_config/test_test_provider_database.py \
  tests/test_doc_front_matter.py tests/test_reachability.py
```

[Full output](green-initial.txt):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
325 passed, 3 skipped, 7 warnings in 105.10s (0:01:45)
```

The three skips are the existing opt-in live Conversations API probe and two
owner-corpus card probes. The ordinary PostgreSQL consumers executed. The
new tests use actual temporary configurations, files, artifact folders and
CLI processes; terminal proof uses a real PTY. The already-passing rejection
of `--no-hash` is pinned but is not claimed as a red-to-green change.

## Four Discriminating Negative Controls

The exact commands, pre-plant hashes and restored hashes are in
[mutation-restoration.json](mutation-restoration.json). All four controls
exited 1 for the intended assertions, and every source file was restored
byte-for-byte. The passing source above was unchanged after these controls.

| Plant | Failure Evidence |
| --- | --- |
| Remove the loader anchoring call | [4 failed, 2 warnings in 3.21s](red-anchor.txt): both locators, real reader, and artifact lock/verify. |
| Read anchored settings values in the move plan | [1 failed, 2 warnings in 2.59s](red-raw-plan.txt): fake-checkout model files no longer get the required move entries. |
| Restore the old `temp/wizard_threads` location | [3 failed, 7 warnings in 2.54s](red-wizard-store.txt): both locator cases and the real client file write. |
| Pass no progress callback from the CLI | [1 failed, 2 warnings in 3.32s](red-progress.txt): terminal text mode lacks the required progress line. |

All control summaries include the active secret-store and receipt-isolation
summaries and `dbname audit: owner targets: none`. See the preserved
[control script](mutation-controls.py.txt) and [completion summary](mutation-summary.txt).

The first wizard control correctly failed its three assertions, then the
private harness refused cleanup because its filename rule expected a bare
UUID instead of the actual `local_thread_<16hex>.json`. The production source
had already been restored in `finally`. That transcript and harness are kept
as [initial wizard output](red-wizard-store-initial.txt),
[initial summary](mutation-summary-initial.txt), and
[initial script](mutation-controls-initial.py.txt). Only the exact file named
in that failure was removed. The corrected helper reran the wizard control
for complete restoration hashes, then ran the progress control. Both the
main old-store path and the control's worktree path are absent afterward.

## Static Checks and Canonical Review

[Static comparison](static-comparison.json) records the exact commands and
exit codes. Black passed on all 11 changed Python files, and the exception
marker/shrink-only baseline check passed. Flake8 and mypy still return 1 for
existing diagnostics: 18 flake8 diagnostics and seven mypy errors in the
unchanged settings arithmetic. Comparing the same changed paths with a
tracked `origin/main` snapshot, ignoring only line-number shifts, found zero
new or removed diagnostics. Full final and baseline outputs are retained.
The initial new docstring-width and TOML typing diagnostics were corrected
before the passing focused run.

The source declaration scan identifies ledger records 0009 and 0053. Both
were re-read: checksum progress does not affect the token-only ledger ruling;
changing future local wizard-file placement does not alter the recorded
resumable-genesis or hosted-thread disposition. Their only changes are
verification stamps to the merge base above. Quotes, other body text, source
lists, statuses, and links remain byte-identical. No changed file is a
declared source of `AGENTS.md` or `docs/turn_flow_sequence.md`. The focused
run's canonical and reachability checks passed.

The coordinator reviewed the production diff and another agent reviewed the
inventory, tests, PTY handling and loader boundaries by source inspection;
neither reported a blocker. These were source reviews, not fabricated bot
approvals. [Source hashes](source-sha256.json) bind the final implementation.

## Landing Boundary

This branch ran no whole-tree gate. The coordinator owns the combined gate
before push/PR publication and merging. Normal applicable commit hooks run
when this branch is committed. No migration, fleet application, UI build,
owner model move, live owner-home activation, secret access, or paid call is
part of this lane. A coordinated gateway restart is owed when services run
again. `nexus.toml`, model readers, artifact lock and UI are unchanged.

## Shared Integration Validation

The assembled integration `2cc9a5fcff76e0c643ca41490eb2508b870b4850` includes this lane’s input `4fffb85b6008e76c3d14ce750666cf73bc802c6e` and passed the full PostgreSQL-enabled Python gate: 7056 passed, 72 skipped, 41 warnings. [Exact commands, logs, ancestry and guard limits](../resume-wave-a-2026-10-08/verification.md). This is shared assembled-tree coverage; no separate standalone or whole-suite offline gate was run. Existing focused/manual evidence retains its original source head.

## Review Follow-Up

Claude’s source review found no blocking issue. The locator-root anchoring of
explicit TOML and legacy JSON loads, bare missing-key refusal, and two-key
production-only move inventory are prescribed contracts. The existing locator
regression includes explicit-path parity under NEXUS_RUNTIME_CONFIG; both locator
modes and cwd independence passed. Existing local wizard files are not migrated;
the owner old-store path was confirmed absent. Canonical bodies were reverified,
as recorded above. Raw proof remains in the repository as ordered evidence.

The one source follow-up moves the unchanged type-only ChecksumProgress import
below third-party and ordinary local imports. Deferred annotations are already
enabled. The [AST/compile check](review-import-grouping.json) confirms all runtime
statements are unchanged; Black and normal hooks validate this small delta.
No new runtime behavior or test result is claimed.

Codex — GPT-6

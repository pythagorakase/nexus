# Model Artifact Admission, Plan, and Fetch

Implementation of frozen 812-S3 + S6 on `claude/812-models-plan-fetch`,
starting from main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` and the
committed 820 path contract `4fffb85b6008e76c3d14ce750666cf73bc802c6e`.
Refs #812. Focused and ordered manual validation passed. The coordinator's combined gate
and PR publication remain pending; this is not a whole-suite result.

## Contract and Current Shape

- `artifact_manifest.py:642` retains existing configuration/file problem
  ordering and explicitly selects cheap versus full verification.
  `verify_artifacts` (line 713) shares the lock/spec/report snapshot.
- `check_artifacts_at_boot` (line 731) compares file list, sizes and revision.
  `gateway_lifespan` in `nexus/api/narrative.py:111` runs it before recovery
  and scheduling, even with no slot set. Only the existing exact TEST-only
  process marker skips this check, and the provider refusal shares its
  constant.
- `nexus/runtime/readiness.py:1073` hashes for `models.artifacts`, registered
  after `runtime.log_writers`, dependent on `config.valid`, host-only and
  excluded from gateway evaluation.
- Plan (line 778) reports present, absent, drifted and unpinned states with
  download/free bytes only for a pinned absence; it never hashes or writes.
- Fetch (line 830) checks every existing path before downloading anything,
  requires locked repositories and revisions for absent paths, rechecks
  absence immediately before each download, and verifies the result. It
  never repairs, moves, deletes, or relocks an existing folder. Hub failures
  identify possible partial downloads without removing them.
- Production loader remedies point to fetch only when the configured path,
  repository and locked role/name/revision match. Non-production paths keep
  their existing pinned `hf download` remedies. Lock's missing-folder remedy
  remains unchanged.
- 812-S4a already landed: the runtime has one embedder and a direct production
  reranker. The manual configuration therefore changes only the reranker's
  `model_path`, never the removed production candidate registry. 820 anchors
  these paths in the loader; its implementation remains unchanged here.

There is no migration, fleet application, configuration schema change, UI
change or build. S4b, S5 and S7, legacy-vector policy, unused owner models,
and tokenizer pinning remain outside this implementation. A tokenizer
follow-up issue is prepared and awaits publication after the combined gate.

## Focused and Manual Proof

The exact package import resolved to this worktree and the initial one-minute
load was 5.20. The frozen 18-file proof plus document/reachability checks ran
serially under `nice -n 15`, with `NEXUS_RUN_POSTGRES=1`, the dbname audit,
`NEXUS_KEYRING_DISABLE=1` and `PYTHONPATH=$PWD`. `NEXUS_HOME`,
`NEXUS_RUNTIME_CONFIG`, `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`,
`NEXUS_RUN_LIVE_LLM`, `NEXUS_RUN_SECRET_STORE`, `NEXUS_RUN_CORPUS` and receipt
routing overrides were cleared. The complete command and output are in
[green-initial.log](green-initial.log); the immutable source bytes are recorded
in [green-source-sha256.json](green-source-sha256.json).

```sh
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -rs \
  -p tests.dbname_audit \
  tests/test_embedding_artifacts.py tests/test_runtime/test_readiness.py \
  tests/test_runtime/test_readiness_pg.py tests/test_api/test_runtime_status.py \
  tests/test_api/test_narrative_jobs_pg.py tests/test_memnon_model_failures_pg.py \
  tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_embedding_contract.py \
  tests/test_lore/test_runtime_config.py tests/test_memnon_script_model_loaders.py \
  tests/test_model_artifact_lock_committed.py tests/test_api/test_acceptance_staging_pg.py \
  tests/test_api/test_narrative_continue_validation.py tests/test_runtime/test_supervisor_live.py \
  tests/test_slot_routed_entrypoints.py tests/test_cli_contract.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_doc_front_matter.py tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
528 passed, 2 skipped, 20 warnings in 514.71s (0:08:34)
```

All three deliberate controls failed their intended single test:

| Plant | Result |
|---|---|
| Omit the lifespan artifact call | refusal test fails: 1 failed, 2 warnings in 2.74s |
| Remove the TEST marker bypass | marked-lane test fails: 1 failed, 2 warnings in 2.88s |
| Skip existing-folder hashes before fetch | drift refusal test fails: 1 failed in 2.84s |

Each control retained active secret/receipt guards and `owner targets: none`.
The [harness](red-controls-script.txt), [records](red-controls.json), and raw
logs ([boot](red-boot-call.log), [marker](red-test-marker.log),
[fetch](red-fetch-existing.log)) are retained. Every planted source was restored
in `finally`; all 12 Python source hashes match the original green snapshot.
The heavy test slot was then released, with no process left running.

## Ordered Manual Proof

The next serial slot started at load 5.12. Before preparation, all three
absolute targets beneath this worktree's `scratchpad/812-S3` were confirmed
absent with `lexists`: `fetch`, `boot`, and `manual-receipts`. All child commands
used `nice -n 15`, the shared interpreter and exact worktree `PYTHONPATH`.
The [environment harness](manual_common.py.txt) clears ambient `HF_*` and
`HUGGINGFACE_*` variables (including token, Hub, XET and asset-cache overrides),
`TRANSFORMERS_CACHE`, `TRANSFORMERS_OFFLINE`, runtime routing/home overrides,
TEST-provider overrides and live-call flags. It sets a private `HF_HOME`,
`HF_HUB_DISABLE_IMPLICIT_TOKEN=1`, `HF_DEBUG=0`, `NEXUS_KEYRING_DISABLE=1`, and
private receipt routing. The legacy spelling `HUGGING_FACE_HUB_TOKEN`, which
does not match those prefixes, was absent in the launcher environment; a
[presence-only record](manual-token-env-presence.json) verifies that without
reading a value. The private HF token path held no token. Read-only commands
run with Hub offline; only the single ordered download invocation enables
network access. No owner token or token file was read.

[Exact commands and timings](manual-results.jsonl):

| Command | Exit | Seconds |
|---|---:|---:|
| `check_artifacts_at_boot(load_settings())` | 0 | 0.505 |
| `models plan` | 0 | 0.511 |
| `models verify` | 0 | 3.921 |
| `doctor --json` | 1 | 4.844 |
| `models plan --config <scratch-fetch-config>` | 0 | 0.459 |
| `models fetch --config <scratch-fetch-config>` | 0 | 60.925 |
| `models verify --config <scratch-fetch-config>` | 0 | 4.102 |

The owner's configured embedder and reranker passed the cheap and full
checks. [Doctor's artifact entry](manual-doctor-models-artifacts.json) is
`pass`, with `observed` ending in `(sha256)`. Doctor's overall exit 1 is
retained accurately: this feature worktree has no UI build, and its deliberately
disabled Keychain provides no OpenAI key. Those are its only two failures;
all database/schema/identity/IDF checks and the new model check passed. No
owner services were started, secrets fetched, or doctor remedies executed.

The private fetch config changes only the direct production reranker's
`model_path`. Plan reported the owner's embedder present and the private
reranker absent: 1,742,869,078 download bytes, 50,658,877,440 free bytes.
The [single invocation](manual-fetch.stdout.log) fetched exactly ten locked
files from `naver/trecdl22-crossencoder-debertav3` at
`24f6a61d11707432d5780a1d5cf4e3af25cfaddb`. Its internal verification and the
separate full verify both passed. There was no unexpected-file or hash error,
and no retry. The existing embedder was reported as already matching and
was only read. The [download cleanup](manual-download-cleanup.json) confirms
that the proof reranker and private Hub/XET cache were removed.

The [startup records](manual-boot-results.json) show:

- Good checkout configuration: owned PID 135 served `/health` with HTTP 200
  and `{"status":"healthy","service":"narrative_api"}`, then was terminated
  and reaped; 1.517 seconds including cleanup.
- Bad private configuration: its fresh reranker folder held only `proof.txt`.
  Owned PID 148 exited 3 in 1.098 seconds, logging `The gateway will not start`,
  the ten missing files and the deliberately unexpected `proof.txt`. This
  intentional boot-negative diagnostic is separate from the successful real
  download, which produced no unexpected-file finding.
- Before and after each launch, `lsof -nP -iTCP:8013 -sTCP:LISTEN` returned 1
  with empty stdout and stderr. Both owned processes were reaped, the listener
  is absent, and the private bad artifact was removed. No slot or TEST-only
  marker was set for either gateway; only `/health` was requested.

The two exact configs and [single-key checks](manual-config-records.json),
all stdout/stderr logs, launch/cleanup records and the executed harness source
copies are retained in this directory (the harness expects its original
`scratchpad/812-S3` location). [Final cleanup](manual-final-cleanup.json)
confirms that all Python bytes still match the focused green snapshot and
no manual receipt directory was created. The heavy slot was released after
all subprocesses finished. The artifact lock, `nexus.toml`, owner model folders
and original 820 branch remain unchanged. No whole-suite result is claimed;
the coordinator owns the combined gate.

## Landing Notes

Run `nexus models verify` before the next gateway restart: drift now refuses
startup before scheduling. QA-kit gateways launched outside pytest also run
this check. There is no schema/fleet application or UI rebuild. The prepared
[tokenizer issue](tokenizer-followup-draft.md) will be deduplicated again and
published with the PR after the combined gate; its final URL remains a
coordinator publication dependency, not a missing implementation decision.

## Static Comparison

Black and the exception-disposition gate pass. Both added handlers fail the
operation explicitly. Their marker reasons are shortened to `hub` and `lock`
to retain the required header markers within the formatter's line length.

Flake8 reports 56 diagnostics versus 57 for the same 12 files from
`origin/main`; none are new. The difference removes the already-unused
`recover_active_slot_choice` import in the lifespan. Mypy reports the same
three existing errors: missing frontmatter stubs, an old non-Optional default
in narrative.py, and the optional LORE memory manager access in the runtime
configuration test. Raw outputs and normalized comparison are retained here:
[Black](black.log), [flake8](flake8.log), [flake8 baseline](flake8-main.log),
[mypy](mypy.log), [mypy baseline](mypy-main.log),
[comparison](static-comparison.txt), [exception gate](exceptions.log).

## Canonical Review

The changed lifespan adds a startup prerequisite and leaves the documented
turn orchestration, slot leases, acceptance path and scheduler ordering
intact. `docs/turn_flow_sequence.md` now names that prerequisite; it and
`AGENTS.md` are re-stamped to the merge base `4ae8b8d2` after this review.
Decision 0009 remains accurate: usage stays in tokens and the new artifact
commands add no prices, dollar columns or pool policy. Its existing 820
stamp already names this merge base; no quote, source list, status or ruling
is changed. `docs/decisions/README.md` references narrative.py only inside a
fenced example, not its actual sources front matter; it is unchanged.
The generated CLI reference is regenerated from the parser/transport table.
Historical `docs/vector_embeddings.md` and the artifact lock are unchanged.

## Shared Integration Validation

The assembled integration `2cc9a5fcff76e0c643ca41490eb2508b870b4850`, including this lane input `1b87677113eb0b30003d3b1713e9dd1a89ab4454`, passed the full PostgreSQL-enabled Python gate: **7,056 passed, 72 skipped, 41 warnings**. [Exact commands, immutable tree/input ancestry, complete logs and audit limits](https://github.com/pythagorakase/nexus/blob/bf229051e3d046b76ab8d18b34e9ee054a03bbf6/docs/qa/resume-wave-a-2026-10-08/verification.md). All three pieces reported active secret-store protection, untouched receipts and owner targets none. This is assembled-tree coverage; no separate standalone branch full gate or whole-suite offline run is claimed. Later changes here are evidence only; any landing merge/freshness changes require their own delta record.

The separate tokenizer policy follow-up was deduplicated and published as [#1126](https://github.com/pythagorakase/nexus/issues/1126). No tokenizer policy or fetch behavior was changed here.

Codex — GPT-6

## Review and landing merge

The review found no blockers. `fetch_remedy_for` deliberately catches nothing, as frozen item5 requires; malformed configuration and locks remain fatal. Empty repo IDs return before settings/lock reads. The exact TEST-only marker and INFO log preserve the ordered contract. The PR now names the missing-lock setup step. Partial-download and durable-proof policies remain unchanged.

Merged current main `81163beb0f02041f2e83c50a96dfa60286cbb28a` by an ordinary conflict-free merge, removing the820 prerequisite from this PR diff and preserving815pagination. Re-read AGENTS and the turn-flow source closure: the deferred-work paragraph accurately names cheap boot admission versus full verification and the TEST-only exception. Decision0009 remains token-only. Re-stamped all three to the new merge base without changing their rulings.

Artifact implementation, readiness, provider guard, CLI contract and associated tests match the assembled gate input; narrative.py differs only by the pending777UI-router registration. The merged CLI differs only by820s type-only import grouping; generated CLI reference matches the tested integration bytes. Final freshness/reference checks follow.

Codex — GPT-6

# Model Artifact Admission, Plan, and Fetch

Implementation of frozen 812-S3 + S6 on `claude/812-models-plan-fetch`,
starting from main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` and the
committed 820 path contract `4fffb85b6008e76c3d14ce750666cf73bc802c6e`.
Refs #812. Focused validation passed; manual proof and the coordinator's
combined gate remain pending, so this file does not yet claim landing readiness.

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

Read-only owner-artifact timings, one free isolated pinned download, and
owned-port 8013 startup proofs await the next serial proof slot. No whole-suite
result is claimed; the coordinator owns the combined gate.

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

Codex — GPT-6

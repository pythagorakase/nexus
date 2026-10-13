# 776 Saved Stage Outputs: Verification

Status: Phase 1 and Phase 2 of the 776-S1b order are complete on the integrated
wave-B tree (branch `claude/waveb-fix-776-s1b`, cut from the integration head
`7eb9a10c`). The one authorized paid probe ran once, inside its bound, and its
capture is committed at `tests/fixtures/genesis_776_real_bundle.json`. No push,
no PR, no fleet migration. The coordinator's own steps are listed at the end.

## Lane History

The lane's source (`95a45ca1`, merged into the assembly as `c38df3b1`) was
authored by Codex as a source-only checkpoint: its first evidence file said no
pytest, PostgreSQL, mypy, flake8 or fleet query had run, and that Phase 2 (probe,
capture, owner child, six PostgreSQL tests, red runs) did not exist. That file's
claims about Black and hooks had no recorded command; every check below replaces
them. Its base was `4ae8b8d2`; [canonical-source-closure.json](canonical-source-closure.json)
still cites that base. The assembly has since moved the `verified_commit` stamps
of decisions 0009, 0016, 0017 and 0024 (and of `AGENTS.md` and
`docs/turn_flow_sequence.md`) to `f073b371`, which is the stamp on this tree;
`tests/test_doc_front_matter.py` passes on it (below).

## What Is Wrong on `main` (Cited by the Order)

Every POST starts a fresh run (`perform_transition_with_retrograde` calls
`start_genesis_run` first); S1a saves stage outputs that nothing reads back; the
derivation output was the bare inputs dump; `genesis_runs.input_fingerprint` was
never written; the route had no claim, so a double click started a second paid
run; a `running` row left by a stopped process stayed `running`; and after an
embedding failure the world was committed and the cache cleared, so the wizard's
Retry answered 400 `No setup data found`. The order's file:line citations are in
`temp/orders_2026_10_07/776-S1b.md` ("What Is Wrong Today").

## Review Findings Applied (Commit `b71bb4cf`)

- Stale under item 8 (P1, two findings, fixed once): the two offline route tests
  that drive the cache guards with only `read_cache` replaced now also replace
  `wizard_chat.run_genesis_transition` with `lambda slot, prepare: prepare()`, as
  the `transitions` fixture in `tests/test_api/test_wizard_weird_level.py` does.
  The real guards still answer 409 and 422 and no slot database opens:
  `tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance`
  and `tests/test_wizard_agent.py` (the `base_timestamp` guard, which under the
  gate otherwise reached the routed fake slot 5 and answered 500). A grep for
  every caller of `transition_to_narrative_endpoint` or `/api/story/new/transition`
  found no other test that patches only `read_cache`:
  `test_wizard_weird_level.py` uses the fixture, `test_genesis_ledger_pg.py` drives
  the real claim on a clone, and `test_slot_mutation_guard.py` is refused with 422
  by request validation before the route body runs.
- Post-commit resume validation (P2): `resume_committed_genesis_run` validates
  only the persistence output and the derivation output's `outcome`
  (`_derivation_outcome`); packet, seed-candidate and expansion rows are copied
  verbatim. `transition_result_from_ledger` reads the derivation outcome the same
  way. Full validation stays in `reusable_genesis_outputs`, the pre-commit path.
- Lost anchor after a failed resume (P2): `_own_transition` now asks
  `_committed_genesis_run_to_resume` for the newest failed run with a non-NULL
  `persistence` output that no later `done` run follows, and resumes from it, so
  a resume that failed before copying persistence no longer strands the world
  behind a 400. One narrowing beyond the ruling: a later run with another
  non-NULL `input_fingerprint` also disqualifies the candidate, because such a run
  is a fresh build from new wizard inputs (a resume run always copies its source's
  fingerprint or has none), never a resume of the old world. New test:
  `test_resume_that_failed_before_copying_persistence_still_finishes`.
- P3: `SKIPPED_RETROGRADE` in `tests/proofs/proof_weird_entry_points.py` carries
  `"reused_stages": []` (stale under item 4); the skipped-reuse test asserts
  `settings.orrery.enabled is False`, the override it relies on; the nested
  `prepare()` is annotated `-> tuple[TransitionData, Optional[WeirdLevel]]`.
- The two "proof pending" findings and the "untested paths" finding are answered
  by the proof below.

## Integrated-Tree Proof (2026-10-13)

Every command ran from the worktree root with `PY=/Users/pythagor/nexus/.venv/bin/python`,
`PYTHONPATH=$PWD`, `nice -n 15`, and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset (`env -u ...`). Import check:
`PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed
`/Users/pythagor/nexus/.claude/worktrees/fix-776-s1b/nexus/__init__.py`. Every
PostgreSQL run read `uptime` first and waited in a bounded loop while the
one-minute load was 24 or more; the load never reached 24, so no run waited
(each log's header records `load-wait seconds: 0`). One pytest session ran at a
time. No connection timeout occurred, so no file needed its one rerun.

### Phase 1 PostgreSQL Set, First Run (Head `b71bb4cf`)

uptime: `11:28 up 5 days, 22:08, 5 users, load averages: 10.32 11.95 14.27`

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_genesis_fingerprint.py \
  tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py \
  tests/test_api/test_route_capabilities.py tests/test_orrery/test_retrograde_orchestrator.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_cli.py tests/test_cli_model_selection.py tests/test_cli_choice_http.py \
  tests/test_cli_session_wait.py tests/test_cli_generation_http.py \
  tests/test_wizard_agent.py tests/test_api/test_wizard_confirmation.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 42 targets: nexus_test_issue_613_*, postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_* x34, qa640_renamed_test_model_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:61266 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:61271 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:61266 (psycopg2), save_04@local:61271 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
376 passed, 2 skipped, 7 warnings in 303.84s (0:05:03)
```

At that point the Phase 2 tests did not exist yet; the two skips are the
corpus probes (`NEXUS_RUN_CORPUS=1`) in `test_card_identity.py`.

### The Live Probe (Phase 2, One Paid Run, Head `2b17dbcc`)

Lane: the order and the ruling name 8021, but 8021 is not free on this machine:
`netstat -anv -p tcp` shows `127.0.0.1.8021` and `::1.8021` in LISTEN owned by
`launchd:1`, and `launchctl print system` lists `"com.apple.ftp-proxy" => enabled`
(macOS's FTP proxy, socket-activated on 8021). User-level
`lsof -nP -iTCP:8021 -sTCP:LISTEN` cannot see that socket and exits 1, so the
order's lsof check passes while uvicorn's bind fails with `[Errno 48]`. A free
rehearsal (a TEST-model slot, so no provider call) confirmed the failure on 8021.
The probe therefore uses lane 8022, which no order or suite in this wave binds,
and refuses to start unless both lsof and a bind attempt find the lane free. The
same rehearsal on 8022 answered 200 with the skipped block.

uptime: `11:39 up 5 days, 22:19, 5 users, load averages: 9.31 12.35 14.11`;
probe start `2026-10-13T16:39:32Z`.

```sh
NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 NEXUS_GENESIS_RESUME_PROBE=1 \
NEXUS_GENESIS_CAPTURE_PATH=$PWD/tests/fixtures/genesis_776_real_bundle.json \
  nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_resume_live.py
```

```text
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_776s1b_probe_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 5 warnings in 222.97s (0:03:42)
```

Transcript: the clone `qa640_776s1b_probe_5b4b5e0b343c` (created with
`story_pin=None`, dropped by its fixture) was staged with `stage_fixture_world`
(slot model `gpt-6-astra`, the configured wizard default) and both phases
confirmed. The gateway (`python -m tests.slot_routed_uvicorn nexus.api.narrative:app
--host 127.0.0.1 --port 8022`, `store_access_env` for the live `nexus-api` read)
received the first POST. Read-only looks at the ledger during the run showed
the stage rows starting at 12:39:37 (derivation), 12:39:51 (packet), 12:39:52
(seed candidates) and 12:41:51 (expansion), local time. When the expansion
output committed the
probe SIGKILLed the gateway and wrote the capture (`captured_at`
`2026-10-13T16:42:59.282255+00:00`, model `gpt-6-astra`, outputs and details for
derivation, packet, seed_candidates and expansion); the run was still `running`
with no persistence output. The restarted gateway answered the second POST
`200 OK` with `retrograde.reused_stages == ["derivation", "packet",
"seed_candidates", "expansion"]`; the killed run is `failed` with
`GENESIS_RUN_INTERRUPTED`; zero usage events for the four seats after the
restart. Both gateways were stopped and the lane was free afterwards.

Usage events since the probe start, from
`.nexus/runtime/usage/usage-2026-10-13.jsonl` (every event, all `openai`,
`gpt-6-astra`, transport `responses`, attempt 1, outcome `accepted`):

| ts (UTC) | seat | input | output | total | cached input | reasoning |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 16:39:51.742711 | trait_input_derivation | 2,392 | 398 | 2,790 | 0 | 162 |
| 16:41:28.482731 | retrograde_seed_candidates | 26,363 | 4,301 | 30,664 | 0 | 516 |
| 16:41:51.347038 | retrograde_seed_selection | 6,311 | 469 | 6,780 | 0 | 209 |
| 16:42:59.120957 | retrograde_expansion | 15,149 | 3,287 | 18,436 | 0 | 244 |
| **Total** | | **50,215** | **8,455** | **58,670** | **0** | **1,131** |

Bound check: one derivation, two seed calls, one expansion, no retries; nothing
after the restart. The probe ran once.

### Phase 2 PostgreSQL Tests From the Capture (Head `767d9187`)

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit -x \
  -k "resumes_saved or changed_input or joins_the_running or stopped_owner or blocked_persistence or embedding_failure or failed_before_copying" \
  tests/test_api/test_genesis_ledger_pg.py
```

```text
E       AssertionError: HTTPException(status_code=500, detail='Transition failed: expansion release timed out')
1 failed, 3 passed, 16 deselected, 5 warnings in 96.59s (0:01:36)
```

That failure was the join test's own observer: the route runs each POST in an
executor thread, so the joiner's lost claim was never matched by thread name and
the held expansion timed out. The observer now records any lost claim (only the
second POST can lose one). Rerun of the remaining five:

```text
5 passed, 19 deselected, 5 warnings in 43.72s
```

The seven new route-level proofs are `test_retry_resumes_saved_outputs`,
`test_changed_input_rebuilds_the_run[weird_level]`,
`test_changed_input_rebuilds_the_run[slot_model]` (the other registered model is
the one whose `uses` lists `wizard.fallback_model`, read from `load_settings()`),
`test_repeated_post_joins_the_running_run`,
`test_stopped_owner_run_is_closed_and_resumed` (a real
`python -m tests.genesis_owner_child` owner, SIGKILLed once its expansion row
exists, then two concurrent POSTs),
`test_blocked_persistence_retry_calls_expansion_again`,
`test_retry_after_embedding_failure_completes_from_the_run`, and
`test_resume_that_failed_before_copying_persistence_still_finishes`. Embedding
runs with the configured MEMNON models; every provider boundary raises
`AssertionError("<stage> provider called")` unless a test replaces it.

### Red Runs (Plants Applied in the Worktree, Restored Byte for Byte)

Each plant was applied with a scratch edit, the named test run, then restored
with `git checkout -- <path>`; `git diff --quiet <path>` returned 0 every time.
No plant was committed. Plant diffs and full logs are kept under the session
scratchpad `fix-776-s1b-phase2-776-S1b/` (`red*.diff`, `red*.log`).

1. `reusable_genesis_outputs` returns `{}` (`+    return {}  # RED PLANT 1` at its
   first line), head `e8a66e5b`, `tests/test_api/test_genesis_ledger_pg.py::test_retry_resumes_saved_outputs`:

   ```text
   E           fastapi.exceptions.HTTPException: 500: Transition failed: derivation provider called
   1 failed, 5 warnings in 4.49s
   ```

2. `run_genesis_transition` skips the claim (`with contextlib.nullcontext(True) as
   won:` in place of `with genesis_slot_claim(slot) as won:`),
   `test_repeated_post_joins_the_running_run`. First at `e8a66e5b` the test failed
   on the owner's ledger write (the claimless joiner marked the live run
   interrupted); the assertion order was then changed (`857d999d`) so the count
   check comes first, and the same plant gives:

   ```text
   E       AssertionError: (['1bc9fbb481cb4b49a689a8755970bc1a', '30fee19029b1474c96481c636d7b6030'], {'first': HTTPException(status_code=500, de...tra', 'traits': ['fame', 'obligations', 'status'], 'derived': True, 'suppressed_cold_start_relationship_traits': []})})
   E       assert (2, ['expansi... 'expansion']) == (1, ['expansion'])
   1 failed, 5 warnings in 11.79s
   ```

3. The route reads the cache before the claim (`prepared = prepare()` before
   `asyncio.to_thread(run_genesis_transition, request.slot, lambda: prepared)`),
   head `e8a66e5b`, `test_retry_after_embedding_failure_completes_from_the_run`;
   the first POST answers the item 4 message and the second answers 400:

   ```text
   E           fastapi.exceptions.HTTPException: 400: No setup data found for slot 4. Complete the wizard first.
   ERROR    nexus.api.wizard_chat:wizard_chat.py:947 Transition failed: embedder down -- Retrograde history is committed but not yet embedded; retry the transition to finish it (the wizard's Retry, or: nexus continue --slot 4)
   1 failed, 5 warnings in 4.68s
   ```

Red runs for the Phase 1 tests the review asked for (head `857d999d`):

- Validator accepts anything (`return output` at the top of
  `_validate_genesis_output`), `test_invalid_saved_output_fails_before_any_provider_call`:
  `E       assert 'Saved derivation output' in "Transition failed: 'trait_compile_inputs'"`,
  `1 failed, 5 warnings in 3.94s`.
- Claim uses `pg_try_advisory_xact_lock`, `test_claim_is_exclusive_and_dies_with_its_process`:
  `E                   assert True is False` (with
  `RuntimeError: Genesis session claim was not held at release`),
  `1 failed, 5 warnings in 3.59s`.
- `wizard_max_retries` left out of the fingerprint payload, offline
  `tests/test_api/test_genesis_fingerprint.py`: the changed-retries case asserts
  `'03ce90fe…' != '03ce90fe…'`, `1 failed, 5 warnings in 0.49s`.
- No genesis status check in `run_continue` (`if False:` in place of
  `if retrograde_info is None:`), offline
  `tests/test_cli_generation_http.py -k "unfinished_genesis or finished_genesis"`:
  `E       KeyError: 'retrograde'` and `E       AssertionError: assert [] == ['done']`,
  `2 failed, 61 deselected, 5 warnings in 4.81s`.
- The skipped block hides reuse (`"reused_stages": []`),
  `test_skipped_run_reports_reused_derivation_in_direct_and_ledger_answers`:
  `E         {'reused_stages': []} != {'reused_stages': ['derivation']}`,
  `1 failed, 5 warnings in 4.42s`.

### Phase 1 PostgreSQL Set Again, Every Test Running (Head `d7a616ec`)

The same command as the first run (it already includes
`tests/test_cli_generation_http.py`), with `-rs`:

uptime: `12:10 up 5 days, 22:50, 5 users, load averages: 19.18 17.61 15.18`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:53280 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:53281 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:53280 (psycopg2), save_04@local:53281 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
384 passed, 2 skipped, 7 warnings in 355.94s (0:05:55)
```

The same set at `857d999d` (before the typing and guard-rule commits, which
change only test helpers) gave `384 passed, 2 skipped, 7 warnings in 381.77s`.

### Offline Suites

`$PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery`
at `857d999d`:

```text
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_owner_target_guard.py::test_no_test_spells_an_owner_target
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
FAILED tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
8 failed, 3189 passed, 671 skipped, 8 warnings in 687.29s (0:11:27)
```

Four were this fix's: the new Phase 2 helpers spelled `slot_dbname(4)`
(`test_owner_target_guard`), and `tests/genesis_owner_child.py` used
`__import__` (an unregistered dynamic import site, failing both reachability
tests and the doctor CI runner). `d7a616ec` threads the clone's name through the
helpers and imports the four boundary modules statically. Rerun of those files
plus the front-matter test on that content:

```sh
$PY -m pytest -q tests/test_owner_target_guard.py tests/test_reachability.py \
  tests/test_runtime/test_readiness.py::test_doctor_ci_runner_passes_on_this_checkout \
  tests/test_doc_front_matter.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
202 passed, 5 warnings in 28.87s
```

The other four (`test_assembled_prompt_fingerprint`, `test_gaia_prompt_is_concise_and_self_contained`,
`test_no_tracked_file_binds_a_wrapper_module`, `test_wire_schema_size_and_description_budget`)
also fail in the coordinator's whole-tree log of the integration head
(`temp/orders_2026_10_07/coord/waveb-wholetree-7eb9a10c.log`); this branch changes
no prompt, wire schema or script wrapper. They are not fixed here.

`$PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery` at `d7a616ec`:

```text
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
9 failed, 1898 passed, 1526 skipped, 7 warnings in 48.28s
```

All nine fail identically in the coordinator's whole-tree log of `7eb9a10c`
(Orrery settings validators: `claim_event_types contains event types emitted by
background branches: ['ate']` and `orrery.projects.milestone_magnitude must be >=
orrery.promote.magnitude_threshold`); none touches a file of this lane.

### Static Checks (No New Diagnostics)

Files: the lane's product files (`nexus/api/new_story_flow.py`,
`nexus/agents/orrery/retrograde_orchestrator.py`, `nexus/api/wizard_chat.py`,
`nexus/api/narrative_schemas.py`, `nexus/cli.py`), its changed tests
(`tests/test_api/test_genesis_ledger_pg.py`, `test_mock_wizard_responses.py`,
`test_wizard_weird_level.py`, `test_wizard_confirmation.py`,
`tests/test_cli.py`, `test_cli_choice_http.py`, `test_cli_generation_http.py`,
`test_cli_model_selection.py`, `test_cli_session_wait.py`,
`tests/test_wizard_agent.py`, `tests/proofs/proof_weird_entry_points.py`) and the
new files (`tests/test_api/test_genesis_fingerprint.py`,
`tests/test_api/test_genesis_resume_live.py`, `tests/genesis_owner_child.py`).
The baseline is `git archive origin/main` (`f073b371`) extracted to a scratch
directory, checked with the same commands.

- Black: `$PY -m black --check <files>` → `All done! ✨ 🍰 ✨ 19 files would be left unchanged.`
- flake8: `$PY -m flake8 <files>` → 43 diagnostics on the branch, 45 on the
  baseline; by file, code and message: new `[]`, gone two E501 in
  `nexus/api/wizard_chat.py`. Pre-existing diagnostics on untouched lines remain
  (for example `nexus/api/new_story_flow.py:14:1: F401 'pathlib.Path' imported but unused`
  and E501 lines in `narrative_schemas.py`).
- mypy: `$PY -m mypy --explicit-package-bases <files>` → 49 errors in the lane's
  files on the branch, 50 on the baseline. By file and message the branch adds
  three, all in `nexus/api/wizard_chat.py` and all from lane 776-S3
  (`d0e9d848 Store wizard transcripts in each slot database`, merged into the
  assembly after this lane): `Argument "expected_thread_id" to "record_wizard_reply"
  has incompatible type "str | None"` (twice, lines 577 and 758, blamed to
  `d0e9d848`) and `Argument 1 to "build_message_history" has incompatible type
  "list[WizardMessage]"` (line 553, a January line whose argument type 776-S3
  changed). This fix's own three new diagnostics (an unannotated boundary dict,
  a `str` weird level and untyped `requests`) were fixed in `ec975a35`;
  `$PY -m mypy --explicit-package-bases tests/genesis_owner_child.py
  tests/test_api/test_genesis_ledger_pg.py` → `Success: no issues found in 2 source files`.
- Exception dispositions: `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
  → `OK: exception disposition coverage and shrink-only baseline verified.`
  Every commit's pre-commit hooks passed (catalog, config validation,
  dispositions).

### Read-Only Fleet Listing (2026-10-13T16:59:03Z)

`PGOPTIONS='-c default_transaction_read_only=on' psql -At -d <db> -c "SELECT count(*) FROM genesis_runs"`:

```text
NEXUS_template: 0
save_01: 0
save_02: 0
save_03: 0
save_04: 0
save_05: 0
```

No slot holds a run to resume; affected slots: none.

### Cleanup

`psql -At -d postgres -c "select datname from pg_database where datname like 'qa640_776%' or datname like 'qa640_offline_gate%'"`
returned no rows after the last run (the probe clone, the rehearsal clones and
every test clone were dropped by their fixtures). No listener remains on 8022.
The owner's gateway (8002), mock provider (5102) and the 8012 QA session were
not touched; `nexus down` was not needed because no `nexus`-managed service was
started (the probe and rehearsals ran uvicorn directly and stopped it).

## Coordinator's Steps (Not Run Here)

- The whole-tree PostgreSQL gate and its split.
- State-surface regeneration (this lane changes no file under `ui/`).
- Fleet migrations (this lane has none).
- `tests/proofs/proof_weird_entry_points.py` itself, which needs an assembled
  gateway and browser session; only its stale constant was updated.
- Push, PR and merge; a gateway restart is owed when the owner's services run
  again (product code changed in `new_story_flow.py`, `retrograde_orchestrator.py`,
  `wizard_chat.py`, `narrative_schemas.py` and `cli.py`).

## Accepted Under Decision 776-Q5

A joiner waits on the run it joined with no client change: the UI and CLI
waiters skip records of the run they snapshotted, so a joiner's pips stay still
while it waits. That is accepted under Decision 776-Q5 and left to 776-S2 and
776-Q10; it answers 776-S6's note on `pollRetrogradeStages`.

Claude Opus 5.5 (fixer), after Codex — GPT-6 (lane author)

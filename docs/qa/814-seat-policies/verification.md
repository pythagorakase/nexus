# STOP-REPORT: Auxiliary Seat Policies

Work order 814-B, branch `claude/814-seat-policies`, migration 126, gateway lane 8019. No paid calls were authorized. The new isolated proof used TEST, but the required broad PostgreSQL gate unexpectedly made a paid call; see the stop reason below. The registry IDs and their `uses` assignments are unchanged.

## Import Boundary

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/814-seat-policies/nexus/__init__.py
```

## Read-Only Save 04 Trail

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m nexus.cli model --slot 4
skald follow_story gpt-5.6-terra story_pin
gaia follow_story gpt-5.6-terra story_follow
wizard follow_story gpt-5.6-terra story_pin
orrery.experiences.model follow_story gpt-5.6-terra story_follow
storyteller.correspondence.compaction_model follow_story gpt-5.6-terra story_follow
orrery.retrograde.maturation.model_ref fixed gpt-5.6-terra seat_default
ir_eval.judgment.model fixed gpt-5.6-terra seat_default
global.model.default_model fixed gpt-5.6-terra seat_default
summaries.model follow_story gpt-5.6-terra story_follow
```

The CLI read path is direct SQL and does not need a gateway (`nexus/cli.py:1890`). Mutation retains the existing PATCH endpoint. No save pin was changed by this read.

## Resolution and Provider Boundaries

- `nexus/config/story_model.py:85`: one policy/source resolver, with the compatibility wrapper returning only `.model`.
- `nexus/config/story_model.py:194`: accepting transactions capture story pins under `FOR SHARE`, serializing resolution with repins.
- `nexus/config/story_model.py:242`: unresolved legacy jobs raise with table and job ID before provider dispatch.
- `ir_eval/engine/judge.py:90`: IR judgment uses `client.responses.parse` directly. This is the auxiliary seat requiring native OpenAI grammar. Both configuration validation and actual follow-story resolution reject an incompatible provider. Experiences, compaction, maturation, and summaries use the existing registry-routed provider paths.
- `nexus/config/settings_models.py:284`: `global.model.default_model` is explicitly display-only. A source search found no runtime generation consumer of this field; it is nevertheless declared and included in the CLI trail.
- `nexus/telemetry/attempt_manifest.py:105`: `story_pin.resolved_source` records the captured writer/Gaia resolution source. The existing JSON identity field provides storage; historical attempts remain without an observed source.
- Summaries also declare `model_policy = "follow_story"`, preserving their existing prose-following default while freezing the chosen identity in the new deferred queue.

## Migration Boundary

The runner applies migration 126 only inside disposable clone fixtures. Each new column has a `COMMENT ON`; NULL remains allowed solely to represent pre-migration jobs. No automatic backfill chooses a model for those jobs.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --status
NEXUS_template: [ ] 126_seat_policies
save_01: [LOCKED] (status runner skips locked slots)
save_02: [ ] 126_seat_policies
save_03: [ ] 126_seat_policies
save_04: [ ] 126_seat_policies
save_05: [ ] 126_seat_policies
```

The block above extracts only the relevant status entries. Separate read-only connections, including save_01, executed `SELECT count(*) FROM schema_migrations WHERE version LIKE '126%'`:

```text
NEXUS_template: migration 126 applied rows = 0
save_01: migration 126 applied rows = 0
save_02: migration 126 applied rows = 0
save_03: migration 126 applied rows = 0
save_04: migration 126 applied rows = 0
save_05: migration 126 applied rows = 0
```

## Repin Proof

`tests/test_api/test_seat_policy_jobs_pg.py` clones save_04 into `qa640_814_seats_*`, applies branch migrations through the repository runner, and generates a real HTTP TEST-provider turn. The test arranges a scene/season transition and a named declaration on that draft so the production accepting transaction visits all four queues. It then changes the clone pin with the public `nexus model --slot 4 --set` path and compares literal job identities before/after repinning. The scheduler runs after repinning; log assertions require the persisted TEST identity for each queue.

The clone's scheduler is stopped during generation and acceptance so it cannot consume the proof jobs early. Existing copied jobs and unrelated embedding/milestone work are isolated only in the disposable clone. The fixture closes its gateway and runs `nexus down` with the same lane environment.

Maturation dispatch reaches TEST, but the existing TEST server returns narrative/choices fields for `RetrogradeWireSeedCandidateResponseRuntime`, which rejects those extra fields. This proof verifies model identity and error propagation, not successful maturation inference. No paid provider is substituted.

## Stop Reason

The required broad PostgreSQL gate violated the work order's no-paid-calls rule. `test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt` changes repository defaults to TEST but clones save_04 without changing its Skald pin. With compaction now following the story, that fixture selected the clone's paid pin. This fixture boundary should have been checked before executing the gate.

One successful paid call is confirmed in `postgres-gate.log:725-731`:

```text
2026-09-24 19:26:05,908 - httpx - INFO - HTTP Request: POST https://api.openai.com/v1/responses "HTTP/1.1 200 OK"
2026-09-24 19:26:06,039 - nexus.usage - INFO - USAGE provider=openai model=gpt-5.6-terra seat=correspondence_compaction slot=- run=- attempt=1 outcome=accepted in=6250 out=2221 total=8471 cached=0 reasoning=74 tier=default
```

A second paid route was initialized; the captured log does not show another successful paid response. No monetary charge is inferred from the token count. The implementation was stopped immediately after inspecting and confirming this evidence. The gate had already exited. No push, PR, merge, fleet migration, or further provider test was performed after discovery.

Cleanup inspection found no listener on lane 8019 and no remaining `qa640_814_seats_*` proof databases. The repository fixtures own cleanup for the other PostgreSQL test databases. The fleet remains at migration 125, as verified above.

## Validation

All commands ran from this worktree with the shared interpreter. The final offline gate is green. The broad PostgreSQL gate is **not green**: five failures require fixture repair beyond the authorized #885 exemptions. The changes remain local and are not ready for a PR.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2765 passed, 929 skipped, 9 warnings in 132.25s (0:02:12)
```

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config tests/test_api tests/test_orrery -k 'model or seat or resolve or policy or job'
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-correspondence_compaction_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[True-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[True-correspondence_compaction_jobs]
FAILED tests/test_orrery/test_character_experiences_pg.py::test_fresh_duplicate_render_job_is_stale_rejected
FAILED tests/test_orrery/test_claim_propagation_live.py::test_single_hop_ledgers_scheduled_time_provenance_and_policy
FAILED tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible
FAILED tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity
10 failed, 340 passed, 2 skipped, 1693 deselected, 11 warnings, 1 error in 311.00s (0:05:10)
```

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config tests/config/test_story_model.py

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
44 passed, 5 warnings in 3.83s
```

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_retrograde_maturation.py

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
24 passed, 5 warnings in 16.80s
```

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 7 warnings in 1.66s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```console
$ PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_seat_policy_jobs_pg.py

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 9 warnings in 49.51s
```

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 19.55s
```

The isolated repin run above passed before the final provider-construction tightening and the later assertion requiring the exact accepting-turn compaction job. Those final live-path/assertion changes were not rerun after the stop. The offline suite exercised the final production code. The subsequent duplicate-job fixture correction was also not rerun.

The five non-exempt gate failures are the four scheduler preemption parametrizations (two NULL legacy-experience identities; two paid-pin compaction cases) and `test_fresh_duplicate_render_job_is_stale_rejected` (its manually copied job omitted the new columns). The duplicate fixture has been updated, without weakening the production NULL check; the scheduler fixture remains unrepaired at the stop.

The #885-exempt results are `test_resolve_four_template_states_are_distinguishable`, `test_single_hop_ledgers_scheduled_time_provenance_and_policy`, `test_unresolved_arrival_marks_location_unreproducible`, `test_project_applied_ledger_survives_replay_policy_retuning`, `test_declaration_status_hint_resolves_same_batch_faction`, and the `test_live_widened_sources_keep_resolver_and_audit_in_parity` setup error. Their errors are empty-slot-5 actors/clock/anchor failures, confirmed against the issue's named file list.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

No output; exit status 0. Both commit hooks also passed. Black was run through the shared interpreter over the changed Python paths, then checked with `-m black --check` over the same paths:

```text
All done! ✨ 🍰 ✨
25 files would be left unchanged.
```

Additional development runs, retained in local logs: `-m pytest -q tests/test_config tests/config/test_story_model.py tests/test_orrery/test_retrograde_maturation.py` ended `63 passed, 4 skipped, 5 warnings in 4.33s`; `-m pytest -q tests/config/test_story_model.py` ended `8 passed, 5 warnings in 2.92s`. Initial resolver tests had two test-authoring errors (duplicated `by_alias` argument), fixed before the passing runs. The first isolated repin attempt failed on a missing optional chronology map; the fixture now initializes that map.

An initial concurrent full-suite attempt was interrupted after configuration files changed underneath its imported settings classes (`418 failed, 1373 passed, 695 skipped, 9 warnings, 12 errors in 109.07s (0:01:49)`); it is not valid gate evidence. A later complete run found five old maturation fixture failures (`5 failed, 2761 passed, 928 skipped, 9 warnings in 135.38s (0:02:15)`), repaired before the green final run. Two redundant recording-cursor enqueue tests were removed because their existing real PostgreSQL equivalents retain the same coverage. No new mocked behavioral tests were added.

## Coordinator Follow-Up

Before any rerun, repair the recovery fixture to explicitly pin its disposable clone to TEST and explicitly give its legacy experience fixture a resolved TEST identity. Do not relax the NULL error or rerun the current fixture against a paid story pin.

Open questions: Should a follow-up complete these fixture repairs and revalidate the final live path? What explicit model assignments should existing legacy fleet jobs receive at land time?

Apply migration 126 only at land time. Existing queued rows with NULL resolution intentionally fail; any remediation must explicitly select their literal model rather than infer a new model from the current pin. No fleet migration or legacy backfill was performed here.

## Changed Files

- `docs/qa/814-seat-policies/verification.md`
- `ir_eval/engine/judge.py`
- `ir_eval/ir_eval.py`
- `ir_eval/runner.py`
- `ir_eval/scripts/auto_judge.py`
- `migrations/126_seat_policies.sql`
- `nexus.toml`
- `nexus/agents/lore/logon_utility.py`
- `nexus/agents/orrery/experiences.py`
- `nexus/agents/orrery/retrograde_maturation.py`
- `nexus/api/commit_handler.py`
- `nexus/api/commit_handler_sync.py`
- `nexus/api/native_structured_output.py`
- `nexus/api/summary_triggers.py`
- `nexus/cli.py`
- `nexus/config/settings_models.py`
- `nexus/config/story_model.py`
- `nexus/jobs/compaction.py`
- `nexus/jobs/summaries.py`
- `nexus/telemetry/attempt_manifest.py`
- `scripts/api_openai.py`
- `scripts/creative_character_expansion.py`
- `scripts/process_characters.py`
- `scripts/summarize_narrative.py`
- `tests/config/test_story_model.py`
- `tests/test_api/test_seat_policy_jobs_pg.py`
- `tests/test_config/test_seat_policies.py`
- `tests/test_orrery/test_character_experiences_pg.py`
- `tests/test_orrery/test_retrograde_maturation.py`

Codex — GPT-6-Astra.

# STOP-REPORT: Auxiliary Seat Policies

Work order 814-B, second issue; branch `claude/814-seat-policies`, lane 8019,
migration 126. Implementation commit: `a0d61748`. Prior commits `a725781c` and
`e69831f0` are preserved. The required proof gate has not passed; no push,
merge, fleet migration, or template migration has been performed.

## Stop Reason

The mandatory test-session guard exposes a conflict in existing offline tests:
they construct providers with paid, local, retired, or invented model IDs before
replacing network clients with Python fakes. The guard blocks construction,
which is the required behavior. The first offline run reports 59 failures in
five files; preserving the existing OpenAI unknown-model guidance fixes one of
those. The remaining tests require a coordinator decision about replacing the
fake-client test design or separating request construction from client creation.
Disabling the guard or moving these offline tests behind live markers would
conceal the conflict. Neither was done.

Representative exact errors from the first guarded offline gate:

```text
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'claude-sonnet-4-5' (provider=None) is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'nousresearch/hermes-4-70b' (provider='local') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'anthropic-log-test-model' (provider=None) is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
```

`tests/test_native_structured_output.py:481` constructs an Anthropic provider
before substituting `FakeMessages`; `tests/test_usage_recorder.py:180` similarly
constructs a paid writer before substituting `FakeResponses`. These are not the
#885 empty-slot failures and are not exempt.

## Historical Paid Call

The first issue made one unauthorized paid call before stopping:

```text
2026-09-24 19:26:06,039 - nexus.usage - INFO - USAGE provider=openai model=gpt-5.6-terra seat=correspondence_compaction slot=- run=- attempt=1 outcome=accepted in=6250 out=2221 total=8471 cached=0 reasoning=74 tier=default
```

This is historical evidence from the prior issue, not a continuation call.
The new guard was installed before running this continuation's provider tests.

## Import Boundary

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/814-seat-policies/nexus/__init__.py
```

## Implemented Boundaries

- `nexus/config/provider_guard.py:13`: only the registry's `test` provider is
  permitted when `NEXUS_TEST_PROVIDER_ONLY=1`; rejection names the model and flag.
- `scripts/api_openai.py:411`, `scripts/api_anthropic.py:384`, and
  `scripts/api_openrouter.py:268`: guard before credentials/client construction.
  The local llama-server route already uses `OpenAIProvider`
  (`nexus/agents/lore/logon_utility.py:749`); there is no separate local generation
  client to bypass this wrapper.
- `tests/conftest.py:13`: session-wide environment flag, inherited by child
  processes, unless `NEXUS_RUN_LIVE_LLM=1` is explicitly set.
- `nexus/config/story_model.py:57`: shared transaction-level story-settings writer;
  `nexus/api/slot_endpoints.py:295` calls it for the existing CLI/PATCH path.
- `tests/pg_fixtures.py:75`: default `story_pin="TEST"`, Gaia NULL; corpus clones
  are repinned before migrations, so active legacy jobs are backfilled to TEST.
  Preserving a source pin requires explicit live-LLM opt-in. This resolves all
  four scheduler recovery cases without weakening executor checks.
- `migrations/126_seat_policies.py:42`: managed migration uses repository settings,
  the target database's story row, and `resolve_seat` for each active queue;
  queued/leased NULL identities receive `migration_backfill`. Terminal rows stay
  NULL. Resolution failures propagate into the runner's rollback/failure path.
- The duplicate experience-job fixture already copied `resolved_model` and
  `resolved_source` in `e69831f0`; that repair is preserved.
- The three named live modules now declare `live_llm` in addition to
  `requires_postgres`. Previously they declared only the latter.
- No model registry IDs, policies, or paid-provider defaults were changed by this
  continuation. The reachability baseline records the new production guard and
  removes the newly tested OpenRouter module from orphan exemptions.

## Preserved Resolver Contract

`nexus/config/story_model.py:111` remains the one policy/source resolver;
`resolve_story_model` returns only its `.model`. Accepting transactions lock the
story row while capturing the resolution (`story_model.py:220`), and executors
require the persisted identity (`story_model.py:268`). A NULL legacy identity
still raises with the table and job ID.

IR judgment is the one auxiliary seat with a native OpenAI grammar restriction:
`ir_eval/engine/judge.py:90` directly uses `client.responses.parse`. Configuration
validation (`settings_models.py:3899`) and actual follow-story resolution
(`story_model.py:178`) reject incompatible providers. The other auxiliary seats
use registry-routed provider paths. `global.model.default_model` is a display-only
setting with no runtime generation consumer; it still declares its policy and
appears in the trail. Writer/Gaia attempt identities retain `resolved_source`
inside the existing story-pin JSON (`attempt_manifest.py:105`).

## Read-Only Save 04 Trail

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m nexus.cli model --slot 4
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

## Managed Backfill Proof

`tests/test_api/test_seat_policy_backfill_pg.py` dumps save_04 read-only, restores
it to a uniquely named `qa640_814_backfill_*` database, runs the repository
migration runner, checks every active job's literal result against the resolver,
checks that terminal identities remain NULL, and drops only its clone. It does
not construct a provider or use the clone helper's live-pin opt-in exception.

```text
Migration 126 applied only to qa640_814_backfill_730550256d4c; source pin=gpt-5.6-terra
Backfilled jobs: {"character_experience_jobs": [[1, "gpt-5.6-terra", "migration_backfill"], [2, "gpt-5.6-terra", "migration_backfill"], [3, "gpt-5.6-terra", "migration_backfill"], [4, "gpt-5.6-terra", "migration_backfill"], [5, "gpt-5.6-terra", "migration_backfill"], [6, "gpt-5.6-terra", "migration_backfill"], [7, "gpt-5.6-terra", "migration_backfill"], [8, "gpt-5.6-terra", "migration_backfill"], [9, "gpt-5.6-terra", "migration_backfill"]], "orrery_maturation_jobs": [], "correspondence_compaction_jobs": [], "narrative_summary_jobs": []}
```

The source has nine queued experience jobs (IDs 1–9), all now proven to backfill
as `gpt-5.6-terra` / `migration_backfill` on the clone. No other queue had active
rows in this source snapshot.

## Acceptance, Repin, and Executor Proof

The final routing code passed the real TEST-provider turn, acceptance, CLI repin,
and scheduler test. All four accepting queues retain TEST after repinning the
clone to a paid model. The scheduler's captured identity logs prove dispatch:

```text
Frozen jobs after repin: {"character_experience_jobs": [[10, "TEST", "story_follow"], [11, "TEST", "story_follow"], [12, "TEST", "story_follow"], [13, "TEST", "story_follow"], [14, "TEST", "story_follow"], [15, "TEST", "story_follow"], [16, "TEST", "story_follow"], [17, "TEST", "story_follow"], [18, "TEST", "story_follow"], [19, "TEST", "story_follow"]], "orrery_maturation_jobs": [[18, "TEST", "seat_default"]], "correspondence_compaction_jobs": [[2, "TEST", "story_follow"]], "narrative_summary_jobs": [[1, "TEST", "story_follow"], [2, "TEST", "story_follow"]]}
2026-09-24 19:35:09,439 - nexus.config.story_model - INFO - character_experience_jobs job 10 uses persisted model=TEST source=story_follow
2026-09-24 19:35:09,439 - nexus.config.story_model - INFO - character_experience_jobs job 10 uses persisted model=TEST source=story_follow
2026-09-24 19:35:09,706 - nexus.config.story_model - INFO - orrery_maturation_jobs job 18 uses persisted model=TEST source=seat_default
2026-09-24 19:35:10,077 - nexus.config.story_model - INFO - correspondence_compaction_jobs job 2 uses persisted model=TEST source=story_follow
2026-09-24 19:35:10,312 - nexus.config.story_model - INFO - narrative_summary_jobs job 1 uses persisted model=TEST source=story_follow
2026-09-24 19:35:10,618 - nexus.config.story_model - INFO - narrative_summary_jobs job 2 uses persisted model=TEST source=story_follow
Scheduler pass: {"owner": true, "drained": true, "promotion": [0, 0], "orrery_narration_jobs": [0, 0], "character_experience_jobs": [12, 0], "orrery_maturation_jobs": [0, 1], "relationship_milestone_queue": 0, "narrative_summary_jobs": 2, "narrative_embedding_jobs": 0}
```

The existing TEST response still fails the maturation wire schema; the proof
checks persisted routing and loud error propagation, not successful maturation
content. The other selected dispatches use TEST and complete. The scheduler
proof's usage lines all say `provider=test`.

## Validation

Commands below ran from the worktree with the shared interpreter. Logs remain
under `docs/qa/814-seat-policies/logs/` (ignored runtime evidence). Exact tail
outputs follow; a failed gate is not described as passing.

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config/test_provider_guard.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
6 passed, 5 warnings in 0.63s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_seat_policy_backfill_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 1.12s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_seat_policy_jobs_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 9 warnings in 47.58s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_scheduler_recovery_pg.py -k preserves_preempted tests/test_orrery/test_character_experiences_pg.py::test_fresh_duplicate_render_job_is_stale_rejected
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 7 deselected, 7 warnings in 17.27s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_character_experiences_pg.py::test_fresh_duplicate_render_job_is_stale_rejected
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 7 warnings in 2.00s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
2 failed, 58 passed, 5 warnings in 22.62s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_openai_registry_capabilities.py
FAILED tests/test_openai_registry_capabilities.py::test_registry_controls_request_parameters[gpt-6-astra-False]
FAILED tests/test_openai_registry_capabilities.py::test_unregistered_model_fails_with_registry_guidance
FAILED tests/test_openai_registry_capabilities.py::test_default_provider_and_cli_use_registered_judgment_model
FAILED tests/test_openai_registry_capabilities.py::test_ir_judge_default_constructs_without_network
4 failed, 1 passed, 5 warnings in 3.56s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config/test_provider_guard.py tests/test_openai_registry_capabilities.py::test_unregistered_model_fails_with_registry_guidance tests/test_prompt_lint.py tests/test_reachability.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
67 passed, 5 warnings in 19.68s
```

The first reachability run reported the new guard and the now-tested OpenRouter wrapper as baseline changes; the baseline was updated through `scripts/check_reachability.py --write-baseline --reason 'Track the test-session provider guard and remove the now-tested OpenRouter wrapper from orphan exemptions.'`. The final combined check above is green. The four-case `-k` command deselected the duplicate-job case, which was therefore rerun explicitly.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

No output; exit status 0. Both commit hooks also passed.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/config/provider_guard.py nexus/config/story_model.py nexus/api/slot_endpoints.py scripts/api_openai.py scripts/api_anthropic.py scripts/api_openrouter.py migrations/126_seat_policies.py tests/conftest.py tests/pg_fixtures.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_api/test_seat_policy_backfill_pg.py tests/test_config/test_provider_guard.py tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_stage2a_status_live.py
reformatted migrations/126_seat_policies.py
reformatted tests/test_config/test_provider_guard.py
reformatted tests/test_api/test_seat_policy_backfill_pg.py
reformatted nexus/api/slot_endpoints.py

All done! ✨ 🍰 ✨
4 files reformatted, 11 files left unchanged.
```

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/config/provider_guard.py nexus/config/story_model.py nexus/api/slot_endpoints.py scripts/api_openai.py scripts/api_anthropic.py scripts/api_openrouter.py migrations/126_seat_policies.py tests/conftest.py tests/pg_fixtures.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_api/test_seat_policy_backfill_pg.py tests/test_config/test_provider_guard.py tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_stage2a_status_live.py
All done! ✨ 🍰 ✨
15 files would be left unchanged.
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q
FAILED tests/test_orrery_tag_validation.py::test_anthropic_transport_repairs_invalid_declaration
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[gpt-6-astra-openai-responses]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[claude-sonnet-5-anthropic-None]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[nousresearch/hermes-4-70b-openai-chat_completions]
FAILED tests/test_usage_recorder.py::test_two_provider_passes_keep_seats_models_and_sum
59 failed, 2712 passed, 929 skipped, 9 warnings in 138.59s (0:02:18)
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q
FAILED tests/test_orrery_tag_validation.py::test_anthropic_transport_repairs_invalid_declaration
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[gpt-6-astra-openai-responses]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[claude-sonnet-5-anthropic-None]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[nousresearch/hermes-4-70b-openai-chat_completions]
FAILED tests/test_usage_recorder.py::test_two_provider_passes_keep_seats_models_and_sum
58 failed, 2713 passed, 930 skipped, 9 warnings in 122.56s (0:02:02)
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_GATEWAY_PORT=8019 NEXUS_API_URL=http://127.0.0.1:8019 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config tests/test_api tests/test_orrery -k 'model or seat or resolve or policy or job'
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
FAILED tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible
FAILED tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning
3 failed, 347 passed, 5 skipped, 1699 deselected, 11 warnings in 231.51s (0:03:51)
```

The PostgreSQL gate is green under the work order's named #885 exemptions.
The three failures above match the exact IDs in `gh issue view 885 --comments`:
`test_resolve_four_template_states_are_distinguishable`,
`test_unresolved_arrival_marks_location_unreproducible`, and
`test_project_applied_ledger_survives_replay_policy_retuning`. The replay failures
report `cannot unpack non-iterable NoneType object` and
`replay project tests need one located uncommitted actor`, respectively; the
developer endpoint reports `save_05 is expected to bind off-screen actors`. All five requested
fixture-repair cases pass. The separately recorded repin and backfill proofs also
run in this gate. Five skips include the three live-module cases now correctly
requiring the live opt-in; no skipped case is counted as passed.

The offline gate is **not green**. The final 58 IDs, grouped by file, are:

- `tests/test_native_structured_output.py`: 50
- `tests/test_openai_registry_capabilities.py`: 3
- `tests/test_orrery_tag_validation.py`: 1
- `tests/test_summary_triggers.py`: 3
- `tests/test_usage_recorder.py`: 1

```text
FAILED tests/test_native_structured_output.py::test_two_pass_writer_native_config_reaches_shipped_anthropic_request[high-high]
FAILED tests/test_native_structured_output.py::test_two_pass_writer_native_config_reaches_shipped_anthropic_request[None-None]
FAILED tests/test_native_structured_output.py::test_two_pass_gaia_tool_envelope_reaches_forced_non_strict_tool
FAILED tests/test_native_structured_output.py::test_two_pass_gaia_tool_envelope_async_uses_effort_only_config
FAILED tests/test_native_structured_output.py::test_openai_chat_transport_dispatches_without_responses_attempt
FAILED tests/test_native_structured_output.py::test_openai_chat_transport_dispatches_async_without_responses_attempt
FAILED tests/test_native_structured_output.py::test_anthropic_provider_uses_native_output_format
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-sync-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-sync-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-sync-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-async-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-async-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[model_retry-async-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-sync-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-sync-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-sync-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-async-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-async-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[validation_error-async-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-sync-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-sync-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-sync-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-async-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-async-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[value_error-async-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-sync-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-sync-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-sync-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-async-native]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-async-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_rejection_logs_cover_branches_without_input_leaks[json_decode_error-async-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_tool_envelope_forces_non_strict_tool_and_validates_input
FAILED tests/test_native_structured_output.py::test_anthropic_tool_envelope_async_carries_effort_without_format
FAILED tests/test_native_structured_output.py::test_anthropic_tool_envelope_repairs_text_only_then_raises
FAILED tests/test_native_structured_output.py::test_anthropic_tool_envelope_async_repairs_text_only_then_raises
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_omits_schema_and_parses_json_fence
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_async_parses_bare_fence
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_repairs_then_raises_on_garbage
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_async_repairs_then_raises
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_carries_effort_without_format
FAILED tests/test_native_structured_output.py::test_anthropic_prompted_transport_async_carries_effort_without_format
FAILED tests/test_native_structured_output.py::test_anthropic_non_native_transport_rejects_caller_schema_arguments[output_config-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_non_native_transport_rejects_caller_schema_arguments[output_config-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_non_native_transport_rejects_caller_schema_arguments[output_format-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_non_native_transport_rejects_caller_schema_arguments[output_format-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_provider_accepts_native_output_config_override
FAILED tests/test_native_structured_output.py::test_anthropic_provider_wraps_legacy_output_format_override
FAILED tests/test_native_structured_output.py::test_chat_request_params_ride_extra_body
FAILED tests/test_native_structured_output.py::test_build_native_structured_provider_threads_request_params
FAILED tests/test_native_structured_output.py::test_plain_chat_completion_merges_request_params
FAILED tests/test_openai_registry_capabilities.py::test_registry_controls_request_parameters[gpt-6-astra-False]
FAILED tests/test_openai_registry_capabilities.py::test_default_provider_and_cli_use_registered_judgment_model
FAILED tests/test_openai_registry_capabilities.py::test_ir_judge_default_constructs_without_network
FAILED tests/test_orrery_tag_validation.py::test_anthropic_transport_repairs_invalid_declaration
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[gpt-6-astra-openai-responses]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[claude-sonnet-5-anthropic-None]
FAILED tests/test_summary_triggers.py::test_summary_generator_uses_registry_native_provider_contract[nousresearch/hermes-4-70b-openai-chat_completions]
FAILED tests/test_usage_recorder.py::test_two_provider_passes_keep_seats_models_and_sum
```

## Usage and Cleanup Evidence

Scanning each continuation gate log for `USAGE provider=` found zero non-test
lines. The uncaptured `repin.log` contains six usage lines, all `provider=test`;
`offline.log`, `offline-final.log`, `postgres-gate.log`, `fixture-repairs.log`,
`duplicate-repair.log`, and `backfill.log` contain no usage lines. No live opt-in
was set. The guard was never disabled.

The proof fixture ran `$ nexus down` with its lane environment during cleanup
(`repin.log`, after the scheduler proof). A final
`lsof -nP -iTCP:8019 -sTCP:LISTEN` returned exit status 1 with no output.
No `qa640_814_*` clones remain.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --status
NEXUS_template: [ ] 126_seat_policies
save_01: [LOCKED]
save_02: [ ] 126_seat_policies
save_03: [ ] 126_seat_policies
save_04: [ ] 126_seat_policies
save_05: [ ] 126_seat_policies
```

That block extracts the database headings and migration 126 entries from the
full runner output. Separate read-only connections, including locked save_01,
executed the exact SQL
`SELECT count(*) FROM schema_migrations WHERE version LIKE '126%'`:

```text
NEXUS_template: migration 126 applied rows = 0
save_01: migration 126 applied rows = 0
save_02: migration 126 applied rows = 0
save_03: migration 126 applied rows = 0
save_04: migration 126 applied rows = 0
save_05: migration 126 applied rows = 0
Remaining qa640_814_* clones: []
```

## Files Changed in This Continuation

- `config/reachability_baseline.json`: register guard reachability and tested OpenRouter module.
- `migrations/126_seat_policies.py`: managed DDL and active-row backfill.
- `migrations/126_seat_policies.sql`: replaced by the managed migration.
- `nexus/api/slot_endpoints.py`: call the shared validated pin writer.
- `nexus/config/provider_guard.py`: reject non-test registry providers before clients exist.
- `nexus/config/story_model.py`: expose the shared transaction-level pin writer.
- `scripts/api_anthropic.py`: guard provider initialization.
- `scripts/api_openai.py`: guard provider initialization while preserving registry errors.
- `scripts/api_openrouter.py`: guard provider initialization.
- `tests/conftest.py`: enable the guard for non-live test sessions.
- `tests/pg_fixtures.py`: pin clones to TEST before corpus migrations.
- `tests/test_api/test_seat_policy_backfill_pg.py`: real save_04 backfill proof.
- `tests/test_api/test_seat_policy_jobs_pg.py`: use fixture pinning rather than raw pin SQL.
- `tests/test_config/test_provider_guard.py`: real guarded provider-construction coverage.
- `tests/test_orrery/test_claim_propagation_live.py`: require live opt-in.
- `tests/test_orrery/test_composition_sources_live.py`: require live opt-in.
- `tests/test_orrery/test_stage2a_status_live.py`: require live opt-in.
- `docs/qa/814-seat-policies/verification.md`: this evidence and stop report.

## Coordinator Question

The frozen work order's guard, clone routing, backfill, named fixture repairs,
and PostgreSQL proof are implemented. How should the 58 existing offline
fake-client tests be redesigned while preserving the hard rule that non-test
registry providers cannot be constructed without live opt-in? A follow-up order
can specify TEST-backed protocol coverage or a pure request-builder boundary.
The current guard must not be bypassed to obtain a green gate.

No push or PR was attempted because the mandatory offline gate remains red.

Codex — GPT-6-Astra.

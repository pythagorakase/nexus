# Auxiliary Seat Policy Verification

Work order 814-B, third issue; branch `claude/814-seat-policies`, migration 126,
lane 8019. Rebased cleanly onto `34eb55dc` (#941). All four preceding commits
are preserved through the rebase: `a725781c` → `d76c7c21`, `e69831f0` →
`223aa398`, `a0d61748` → `e197e2e7`, and `c89bbd42` → `3a8de008`.
The lazy-client implementation is `1c6c6227`.

## Result

The offline suite passes with zero failures. The PostgreSQL selection has only
the three exact #885 exemptions listed below. Prompt lint, reachability,
configuration validation, and Black pass. No continuation gate log contains a
non-test `USAGE provider=` line. Migration 126 remains unapplied to the fleet
and template; only disposable test databases were migrated.

## Historical Paid Call

The first issue made one unauthorized paid call before stopping:

```text
2026-09-24 19:26:06,039 - nexus.usage - INFO - USAGE provider=openai model=gpt-5.6-terra seat=correspondence_compaction slot=- run=- attempt=1 outcome=accepted in=6250 out=2221 total=8471 cached=0 reasoning=74 tier=default
```

This is historical evidence, not a call made during this continuation. The
second issue installed a session guard but stopped when it rejected 58 existing
offline fake-client tests. The third ruling moves that guard to real SDK-client
creation while retaining eager registry validation. No paid live opt-in was used.

## Implementation Evidence

- `nexus/config/story_model.py:111`: `resolve_seat` returns the frozen identity,
  policy, source, and story location. The compatibility wrapper returns `.model`.
- `nexus/config/story_model.py:220`: enqueue resolution reads the story row with
  `FOR SHARE`; `story_model.py:268` requires and logs the persisted literal ID.
- `nexus/config/story_model.py:54`: shared validated story-pin writer, used by
  the existing slot PATCH/CLI path and by disposable clone fixtures.
- `nexus.toml:9`, `:389`, `:732`, `:1161`, `:1222`, `:1248`: declared auxiliary
  policies. Registry IDs and `uses` entries remain unchanged. #941's
  `[summaries.window]` and settings changes survived the rebase.
- `ir_eval/engine/judge.py:90`: judgment alone directly requires the OpenAI
  `responses.parse` grammar. `settings_models.py:3883` and
  `story_model.py:178` reject incompatible follow-story providers. Other
  auxiliary generation seats use provider routing. `global.model.default_model`
  has no generation consumer; its policy still appears in the CLI trail.
- `nexus/telemetry/attempt_manifest.py:105`: `resolved_source` fits in the
  existing story-pin JSON for writer/Gaia attempts.
- `migrations/126_seat_policies.py:42`: managed `run(conn)` adds commented
  columns to all four queues and resolves queued/leased legacy rows against
  that database's story, marking them `migration_backfill`. Terminal rows stay
  NULL. Resolution errors fail the migration; executor NULL checks remain loud.
- `scripts/api_openai.py:387`, `scripts/api_anthropic.py:372`, and
  `scripts/api_openrouter.py:257`: provider construction validates registry
  identity without creating a client. OpenAI also resolves capability flags.
- `scripts/api_openai.py:431`, `scripts/api_anthropic.py:417`, and
  `scripts/api_openrouter.py:299`: lazy client properties call
  `nexus/config/provider_guard.py:13` before retrieving credentials or creating
  an SDK client. Explicitly assigned fake clients bypass creation, not the
  guard. Unregistered constructor IDs raise `ValueError` with either flag value.
- `nexus/agents/lore/logon_utility.py:749`: local llama-server generation uses
  the same guarded OpenAI-compatible wrapper; no separate local SDK client.
- `tests/conftest.py:13`: sets `NEXUS_TEST_PROVIDER_ONLY=1` before collection,
  inherited by subprocesses, unless `NEXUS_RUN_LIVE_LLM=1` is set.
- `tests/pg_fixtures.py:75`: default clone pin is TEST, Gaia follows; preserving
  the source pin requires live opt-in. Pinning precedes corpus migrations.
- `tests/test_orrery/test_claim_propagation_live.py:46`,
  `test_composition_sources_live.py:44`, and `test_stage2a_status_live.py:37` now
  require live opt-in. Previously their only gate was PostgreSQL.

## Offline Fixture Repairs

`tests/test_native_structured_output.py` and
`tests/test_orrery_tag_validation.py` used the unregistered retired ID
`claude-sonnet-4-5`; the rejection-log cases also used the invented
`anthropic-log-test-model`. They now use `registry_model("anthropic")`, which
currently selects registered `claude-sonnet-5`, retaining native schema,
prompted, tool-envelope, effort, and rejection-log assertions. Two chat dispatch
tests now assign the whole fake client before inspecting its fake Responses
method. Capability tests assert that no client exists instead of accessing the
lazy property solely to close an unused SDK client. No assertions were removed
or weakened, and fake-client tests were not converted to TEST protocol tests.

The first focused run after implementation had two failures from the partial
client patch described above (`214 passed, 2 failed`). After that repair the
same selection passes all 216 tests. The final full offline gate also passes.

## Import Boundary

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/814-seat-policies/nexus/__init__.py
```

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

## Backfill and Repin Proof
The fresh save_04 clone preserved its source pin for resolution only; no provider was constructed. All nine active experience jobs received the literal paid ID and backfill source. Terminal rows remained NULL.
```text
Migration 126 applied only to qa640_814_backfill_1cbb939bb922; source pin=gpt-5.6-terra
Backfilled jobs: {"character_experience_jobs": [[1, "gpt-5.6-terra", "migration_backfill"], [2, "gpt-5.6-terra", "migration_backfill"], [3, "gpt-5.6-terra", "migration_backfill"], [4, "gpt-5.6-terra", "migration_backfill"], [5, "gpt-5.6-terra", "migration_backfill"], [6, "gpt-5.6-terra", "migration_backfill"], [7, "gpt-5.6-terra", "migration_backfill"], [8, "gpt-5.6-terra", "migration_backfill"], [9, "gpt-5.6-terra", "migration_backfill"]], "orrery_maturation_jobs": [], "correspondence_compaction_jobs": [], "narrative_summary_jobs": []}
```
The final rebased code accepted a real TEST-provider turn, repinned the clone through the CLI/PATCH path, and ran the scheduler. All four queues retained TEST and executors logged the persisted identity:
```text
Frozen jobs after repin: {"character_experience_jobs": [[10, "TEST", "story_follow"], [11, "TEST", "story_follow"], [12, "TEST", "story_follow"], [13, "TEST", "story_follow"], [14, "TEST", "story_follow"], [15, "TEST", "story_follow"], [16, "TEST", "story_follow"], [17, "TEST", "story_follow"], [18, "TEST", "story_follow"], [19, "TEST", "story_follow"]], "orrery_maturation_jobs": [[18, "TEST", "seat_default"]], "correspondence_compaction_jobs": [[2, "TEST", "story_follow"]], "narrative_summary_jobs": [[1, "TEST", "story_follow"], [2, "TEST", "story_follow"]]}
2026-09-24 19:49:02,017 - nexus.config.story_model - INFO - character_experience_jobs job 10 uses persisted model=TEST source=story_follow
2026-09-24 19:49:02,187 - nexus.config.story_model - INFO - orrery_maturation_jobs job 18 uses persisted model=TEST source=seat_default
2026-09-24 19:49:02,506 - nexus.config.story_model - INFO - correspondence_compaction_jobs job 2 uses persisted model=TEST source=story_follow
2026-09-24 19:49:02,691 - nexus.config.story_model - INFO - narrative_summary_jobs job 1 uses persisted model=TEST source=story_follow
2026-09-24 19:49:02,942 - nexus.config.story_model - INFO - narrative_summary_jobs job 2 uses persisted model=TEST source=story_follow
Scheduler pass: {"owner": true, "drained": true, "promotion": [0, 0], "orrery_narration_jobs": [0, 0], "character_experience_jobs": [12, 0], "orrery_maturation_jobs": [0, 1], "relationship_milestone_queue": 0, "narrative_summary_jobs": 2, "narrative_embedding_jobs": 0}
```
The TEST maturation response does not satisfy the maturation wire schema; this proof asserts persisted routing and loud error propagation, not successful maturation content. Other selected dispatches complete.

## Required Gates

Commands ran from this worktree, with no `NEXUS_RUN_LIVE_LLM` opt-in. Exact final tail lines follow. Runtime logs are ignored artifacts under `docs/qa/814-seat-policies/logs/`.

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2785 passed, 934 skipped, 9 warnings in 124.28s (0:02:04)
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config tests/test_api tests/test_orrery -k 'model or seat or resolve or policy or job'
=========================== short test summary info ============================
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
FAILED tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible
FAILED tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning
3 failed, 357 passed, 5 skipped, 1705 deselected, 11 warnings in 234.68s (0:03:54)
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config/test_provider_guard.py tests/test_native_structured_output.py tests/test_orrery_tag_validation.py tests/test_openai_registry_capabilities.py tests/test_summary_triggers.py tests/test_usage_recorder.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
216 passed, 5 warnings in 7.15s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_seat_policy_backfill_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 1.02s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_seat_policy_jobs_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 9 warnings in 38.06s
```

```console
$ PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 19.03s
```

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py

```
Config validation exited 0 with no output.

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python - <<'PY'
import subprocess, sys
files = subprocess.check_output(['git','diff','--name-only','--diff-filter=ACMR','origin/main','--','*.py'], text=True).splitlines()
raise SystemExit(subprocess.call([sys.executable, '-m', 'black', '--check', *files]))
PY
All done! ✨ 🍰 ✨
41 files would be left unchanged.
```
Both pre-commit hooks (`regenerate-orrery-catalog`, `validate-config`) passed on the implementation commit. `git diff --check` is clean.

## Exact #885 Exemptions

Compared by exact ID against the current [#885 comment list](https://github.com/pythagorakase/nexus/issues/885). These are the only PostgreSQL failures:

- `tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable`
- `tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible`
- `tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning`

## Usage, Fleet, and Cleanup
```text
third-backfill.log: usage lines=0, non-test usage lines=0
third-black.log: usage lines=0, non-test usage lines=0
third-cli-trail.log: usage lines=0, non-test usage lines=0
third-config.log: usage lines=0, non-test usage lines=0
third-focused-final.log: usage lines=0, non-test usage lines=0
third-focused.log: usage lines=0, non-test usage lines=0
third-migration-status.log: usage lines=0, non-test usage lines=0
third-offline.log: usage lines=0, non-test usage lines=0
third-postgres-gate.log: usage lines=0, non-test usage lines=0
third-repin.log: usage lines=7, non-test usage lines=0
third-static.log: usage lines=0, non-test usage lines=0
SQL: SELECT count(*) FROM schema_migrations WHERE version LIKE '126%'
NEXUS_template: migration 126 applied rows = 0
save_01: migration 126 applied rows = 0
save_02: migration 126 applied rows = 0
save_03: migration 126 applied rows = 0
save_04: migration 126 applied rows = 0
save_05: migration 126 applied rows = 0
Remaining qa640_814_* clones: []
```

```console
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --status
NEXUS_template:
  [ ] 126_seat_policies
save_01: [LOCKED]
save_02:
  [ ] 126_seat_policies
save_03:
  [ ] 126_seat_policies
save_04:
  [ ] 126_seat_policies
save_05:
  [ ] 126_seat_policies
```
The status excerpt shows only database headings and migration 126. The read-only SQL audit above additionally covers locked save_01. The repin fixture ran `nexus down` with its lane environment; final `lsof -nP -iTCP:8019 -sTCP:LISTEN` returned 1 with no output. No fleet or template migrations were applied.

## Files Changed

- `config/reachability_baseline.json`: Register guard reachability and tested OpenRouter module.
- `docs/qa/814-seat-policies/verification.md`: Record current gates, SQL, CLI trail, and historical incident.
- `ir_eval/engine/judge.py`: Resolve judgment once and retain its source record.
- `ir_eval/ir_eval.py`: Resolve the developer judgment seat.
- `ir_eval/runner.py`: Remove the bypassing default override.
- `ir_eval/scripts/auto_judge.py`: Resolve the configured judgment seat.
- `migrations/126_seat_policies.py`: Add commented identity columns and backfill active legacy jobs.
- `nexus.toml`: Declare auxiliary fixed/follow-story policies.
- `nexus/agents/lore/logon_utility.py`: Route resolved seats and record attempt sources.
- `nexus/agents/orrery/experiences.py`: Capture and execute persisted experience identities.
- `nexus/agents/orrery/retrograde_maturation.py`: Capture and execute persisted maturation identities.
- `nexus/api/commit_handler.py`: Capture async accepting-turn compaction identity.
- `nexus/api/commit_handler_sync.py`: Capture synchronous accepting-turn compaction identity.
- `nexus/api/native_structured_output.py`: Resolve the judgment default through the shared resolver.
- `nexus/api/slot_endpoints.py`: Use the shared validated story-pin writer.
- `nexus/api/summary_triggers.py`: Capture and route summary model identities.
- `nexus/cli.py`: Print every seat policy, ID, and source.
- `nexus/config/provider_guard.py`: Reject non-test real-client creation under the session flag.
- `nexus/config/settings_models.py`: Type policies and validate the judgment grammar boundary.
- `nexus/config/story_model.py`: Provide resolution records, pin writes, and persisted-job checks.
- `nexus/jobs/compaction.py`: Enqueue and execute the captured compaction model.
- `nexus/jobs/summaries.py`: Enqueue and execute the captured summary model.
- `nexus/telemetry/attempt_manifest.py`: Store resolved source in attempt story-pin JSON.
- `scripts/api_anthropic.py`: Validate registry identity and guard lazy SDK creation.
- `scripts/api_openai.py`: Resolve defaults/capabilities and guard lazy SDK creation.
- `scripts/api_openrouter.py`: Validate registry identity and guard lazy SDK creation.
- `scripts/creative_character_expansion.py`: Resolve the configured generation seat.
- `scripts/process_characters.py`: Resolve the configured generation seat.
- `scripts/summarize_narrative.py`: Resolve the summary seat with story context.
- `tests/config/test_story_model.py`: Update developer-seat compatibility coverage.
- `tests/conftest.py`: Enable the test-only provider guard for non-live sessions.
- `tests/pg_fixtures.py`: Repin disposable clones to TEST through the production writer.
- `tests/test_api/test_seat_policy_backfill_pg.py`: Prove active-row backfill on a save_04 clone.
- `tests/test_api/test_seat_policy_jobs_pg.py`: Prove acceptance, repin, and persisted executor routing.
- `tests/test_config/test_provider_guard.py`: Cover guarded clients, fake injection, TEST, and unknown IDs.
- `tests/test_config/test_seat_policies.py`: Cover policy/source combinations using the real registry.
- `tests/test_native_structured_output.py`: Use registered Anthropic IDs and inject whole fake clients.
- `tests/test_openai_registry_capabilities.py`: Assert capability construction leaves clients uncreated.
- `tests/test_orrery/test_character_experiences_pg.py`: Preserve identity in duplicate-render fixtures.
- `tests/test_orrery/test_claim_propagation_live.py`: Require explicit live-LLM opt-in.
- `tests/test_orrery/test_composition_sources_live.py`: Require explicit live-LLM opt-in.
- `tests/test_orrery/test_retrograde_maturation.py`: Use explicit resolved identities in maturation fixtures.
- `tests/test_orrery/test_stage2a_status_live.py`: Require explicit live-LLM opt-in.
- `tests/test_orrery_tag_validation.py`: Replace a retired ID with a registered Anthropic model.

## Coordinator Questions

None blocking. Fleet/template application of migration 126 remains the
coordinator's land-time responsibility. The TEST maturation payload limitation
and the three #885 empty-slot cases remain explicitly outside this routing proof.

Codex — GPT-6-Astra.

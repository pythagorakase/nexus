# Executed Diagnostic and Proof Commands

Run from this worktree. Each block preserves the invocation, including log redirection, and the last lines of its captured output. Intermediate failures are diagnostic evidence, not passing gates. The interrupted targeted run exposed a synthetic generation lease that was never finished; its fixture was repaired. The final full PostgreSQL command and remainder are in `verification.md`.

## Roster Repair

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster.py tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape > temp/gate/roster-repair.log 2>&1
```

```text
FAILED tests/test_presence_roster_pg.py::test_roster_same_turn_departure_survives_commit_reconciliation
FAILED tests/test_presence_roster_pg.py::test_roster_operator_provenance_includes_historical_presence
FAILED tests/test_presence_roster_pg.py::test_historical_settings_are_ordered_but_frontier_is_rejected
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape
8 failed, 27 passed, 5 warnings in 8.73s
```

## Production Recheck

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction tests/test_player_identity_consumers_pg.py::test_ambient_resolver_excludes_established_protagonist > temp/gate/production-recheck.log 2>&1
```

```text
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape
FAILED tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction
FAILED tests/test_player_identity_consumers_pg.py::test_ambient_resolver_excludes_established_protagonist
10 failed, 1 passed, 7 warnings in 10.10s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## Repairs Targeted

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction tests/test_player_identity_consumers_pg.py tests/test_wizard_opening_presence_pg.py tests/test_api/test_correspondence_pg.py tests/test_orrery/test_mood_live.py tests/test_jobs_cli_pg.py tests/test_summary_triggers.py > temp/gate/repairs-targeted.log 2>&1
```

```text
FAILED tests/test_wizard_opening_presence_pg.py::test_ordinary_turn_carries_promoted_presence_before_commit
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/threading.py:331: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
10 failed, 24 passed, 9 warnings in 123.16s (0:02:03)
```

## Offline First

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/offline-first.log 2>&1
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
2 failed, 2645 passed, 807 skipped, 9 warnings in 96.14s (0:01:36)
```

## Roster Config

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_runtime_config.py tests/test_presence_roster_pg.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape > temp/gate/roster-config.log 2>&1
```

```text
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 5 warnings in 18.70s
```

## Full PostgreSQL Repair First

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/full-pg-repair-first.log 2>&1
```

```text
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
101 failed, 3272 passed, 49 skipped, 11 warnings, 32 errors in 753.01s (0:12:33)
```

## Offline Repair

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/offline-repair.log 2>&1
```

```text
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2647 passed, 807 skipped, 9 warnings in 96.16s (0:01:36)
```

## Followup Targeted

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_connection_lifecycle.py tests/test_wizard_opening_presence_pg.py tests/test_lore/test_pass2_baseline_pg.py tests/test_api/test_correspondence_pg.py tests/test_jobs_cli_pg.py tests/test_summary_triggers.py tests/test_orrery/test_mood_live.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape > temp/gate/followup-targeted.log 2>&1
```

```text
=========================== short test summary info ============================
ERROR tests/test_lore/test_pass2_baseline_pg.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
7 warnings, 1 error in 0.58s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## Followup Targeted Fixed

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_connection_lifecycle.py tests/test_wizard_opening_presence_pg.py tests/test_lore/test_pass2_baseline_pg.py tests/test_api/test_correspondence_pg.py tests/test_jobs_cli_pg.py tests/test_summary_triggers.py tests/test_orrery/test_mood_live.py tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape > temp/gate/followup-targeted-fixed.log 2>&1
```

```text
FAILED tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[alias-owner]
FAILED tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[canonical-name]
FAILED tests/test_wizard_opening_presence_pg.py::test_ordinary_turn_carries_promoted_presence_before_commit
FAILED tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore
6 failed, 32 passed, 9 warnings in 98.30s (0:01:38)
```

## Wizard Diagnostic

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider --tb=short tests/test_wizard_opening_presence_pg.py::test_declared_character_named_without_presence_commits_present_row > temp/gate/wizard-diagnostic.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_wizard_opening_presence_pg.py::test_declared_character_named_without_presence_commits_present_row
1 failed, 9 warnings in 7.94s
```

## Provider Repair

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_wizard_opening_presence_pg.py tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore > temp/gate/provider-repair.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore
1 failed, 6 passed, 9 warnings in 20.18s
```

## Pass-2 Final Guard

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore > temp/gate/pass2-final-guard.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore
1 failed, 5 warnings in 1.50s
```

## Pass-2 Persisted History

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore > temp/gate/pass2-persisted-history.log 2>&1
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore
1 failed, 5 warnings in 1.60s
```

## Pass-2 Shared Setting

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore > temp/gate/pass2-shared-setting.log 2>&1
```

```text
    self.trace(f"{self.name}.complete", info)
  File "/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/httpcore/_trace.py", line 47, in trace
    self.logger.debug(message)
Message: 'close.complete'
Arguments: ()
```

## Pass-2 Current Contract

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore > temp/gate/pass2-current-contract.log 2>&1
```

```text
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 2.12s
```

## Offline Final

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/offline-final.log 2>&1
```

```text
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2647 passed, 807 skipped, 9 warnings in 94.49s (0:01:34)
```

## Collection

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider > temp/gate/collection.log 2>&1
```

```text
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3452 tests collected in 2.82s
```

## Black Check

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check . > temp/gate/black-check.log 2>&1
```

```text
would reformat /Users/pythagor/nexus/.claude/worktrees/test-fallout-repair/tests/test_session_manager.py
would reformat /Users/pythagor/nexus/.claude/worktrees/test-fallout-repair/tests/test_wizard_live.py

Oh no! 💥 💔 💥
90 files would be reformatted, 562 files would be left unchanged.
```

## Black Final

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only --diff-filter=ACM 1c5ce99a HEAD -- '*.py') > temp/gate/black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
39 files would be left unchanged.
```

## npm Install

```sh
npm --prefix ui ci > temp/gate/npm-ci.log 2>&1
```

```text

To address all issues (including breaking changes), run:
  npm audit fix --force

Run `npm audit` for details.
```

## UI Check

```sh
npm --prefix ui run check > temp/gate/ui-check.log 2>&1
```

```text

> nexus-ui@1.0.0 check
> tsc

```

## UI Build

```sh
npm --prefix ui run build > temp/gate/ui-build.log 2>&1
```

```text
mode      generateSW
precache  22 entries (2273.62 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## UI Reader Test

```sh
npm --prefix ui test -- client/src/components/nexus/NarrativePane.test.tsx > temp/gate/ui-reader-test.log 2>&1
```

```text
 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  13:28:43
   Duration  496ms (transform 52ms, setup 24ms, collect 128ms, tests 48ms, environment 146ms, prepare 34ms)

```

The whole-repository Black probe reports 90 files needing formatting, all outside this repair. The changed-file gate is clean. No repository-wide formatting sweep was performed.

## Full PostgreSQL Final

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/full-pg-final.log 2>&1
```

```text
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
95 failed, 3278 passed, 49 skipped, 11 warnings, 32 errors in 736.90s (0:12:16)

```

Agent: Codex (GPT-6 Astra).

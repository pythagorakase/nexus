# Validation Command History

All commands ran from the assigned worktree with `PY=/Users/pythagor/nexus/.venv/bin/python`. Tails are verbatim; diagnostic failures were not represented as passes. PostgreSQL gate summaries retain the known #885 failures.

## Offline Baseline

Diagnostic run overlapped the settings edit and retained the old imported Settings class; it is not a valid unchanged-base result.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-baseline.log 2>&1
```

```text
422 failed, 2230 passed, 854 skipped, 9 warnings, 12 errors in 115.81s (0:01:55)
```

## PostgreSQL Baseline

Initial PostgreSQL selection: only the three exempt #885 failures.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-baseline.log 2>&1
```

```text
3 failed, 156 passed, 2 skipped, 1412 deselected, 9 warnings in 33.58s
```

## Unit

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster.py tests/test_presence_reconciliation.py > /tmp/nexus-799-unit.log 2>&1
```

```text
47 passed, 1 skipped, 5 warnings in 0.30s
```

## Focused

Collection command named a nonexistent test file; corrected in the subsequent run.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py tests/test_new_story_db_mapper.py tests/test_trait_compiler.py > /tmp/nexus-799-focused.log 2>&1
```

```text
no tests ran in 0.00s
```

## Retrograde

Existing recording cursors needed the new catalog reads.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-retrograde.log 2>&1
```

```text
20 failed, 26 passed, 4 skipped, 5 warnings in 1.05s
```

## Identity

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_presence_roster_pg.py -k identity > /tmp/nexus-799-identity.log 2>&1
```

```text
13 passed, 12 deselected, 5 warnings in 6.49s
```

## Retrograde2

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-retrograde2.log 2>&1
```

```text
46 passed, 4 skipped, 5 warnings in 0.70s
```

## Offline

Intermediate fixture and reachability regressions; corrected before the final gate.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline.log 2>&1
```

```text
9 failed, 2664 passed, 858 skipped, 9 warnings in 100.84s (0:01:40)
```

## PostgreSQL

Two old duplicate-stub expectations and one fixture missing migration 123 were corrected. Other failures were #885.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg.log 2>&1
```

```text
6 failed, 157 passed, 2 skipped, 1412 deselected, 9 warnings in 37.25s
```

## Regressions

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_lore/test_two_pass_pipeline.py tests/test_reachability.py > /tmp/nexus-799-regressions.log 2>&1
```

```text
113 passed, 5 warnings in 9.39s
```

## PostgreSQL2

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg2.log 2>&1
```

```text
3 failed, 165 passed, 2 skipped, 1412 deselected, 9 warnings in 42.50s
```

## Identity Final

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_orrery/test_character_identity_pg.py > /tmp/nexus-799-identity-final.log 2>&1
```

```text
17 passed, 5 warnings in 7.30s
```

## Offline Final

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-final.log 2>&1
```

```text
2675 passed, 864 skipped, 9 warnings in 98.00s (0:01:38)
```

## PostgreSQL Final

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-final.log 2>&1
```

```text
3 failed, 166 passed, 2 skipped, 1412 deselected, 9 warnings in 43.27s
```

## Final Regressions

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-final-regressions.log 2>&1
```

```text
100 passed, 4 skipped, 5 warnings in 1.24s
```

## Offline Proof

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-proof.log 2>&1
```

```text
2675 passed, 865 skipped, 9 warnings in 101.29s (0:01:41)
```

## PostgreSQL Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-proof.log 2>&1
```

```text
3 failed, 167 passed, 2 skipped, 1412 deselected, 9 warnings in 45.28s
```

## CLI Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_character_identity_pg.py::test_identity_ambiguity_never_retries_test_provider > /tmp/nexus-799-cli-proof.log 2>&1
```

```text
1 passed, 5 warnings in 2.26s
```

## Scope Proof

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_trait_compiler.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py > /tmp/nexus-799-scope-proof.log 2>&1
```

```text
100 passed, 4 skipped, 5 warnings in 1.29s
```

## Offline Gate

Final offline gate.

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-offline-gate.log 2>&1
```

```text
2675 passed, 866 skipped, 9 warnings in 100.04s (0:01:40)
```

## PostgreSQL Gate

Final PostgreSQL gate: only exempt #885 failures.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-pg-gate.log 2>&1
```

```text
3 failed, 168 passed, 2 skipped, 1412 deselected, 9 warnings in 46.59s
```

## Formatting and Reachability

Black was applied to the affected Python files during implementation. Final check:

```python
import subprocess
import sys
paths = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], text=True).splitlines()
raise SystemExit(subprocess.call([sys.executable, "-m", "black", "--check", *[path for path in paths if path.endswith(".py")]]))
```

```text
All done! ✨ 🍰 ✨
22 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py
```

```json
{
  "maintained": 362,
  "reachable_by_kind": {
    "production": 189,
    "operator": 174,
    "migration": 171,
    "test": 234
  },
  "test_only": 34,
  "existing_unreachable": 85,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```


## PR #929 Review-Amendment Validation

All commands ran from this worktree. `$PY` denotes
`/Users/pythagor/nexus/.venv/bin/python`; each pytest command below used
`PYTHONPATH=$PWD`. These are diagnostic runs before the final post-merge gates
in `verification.md`. Failed diagnostic runs are retained as history, not
reported as passing gates.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py
```

```text
14 passed, 5 warnings in 0.32s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_orrery/test_character_identity_pg.py -k identity
```

Successive diagnostic-run tails:

```text
3 failed, 16 passed, 12 deselected, 5 warnings in 20.24s
1 failed, 22 passed, 12 deselected, 5 warnings in 25.45s
3 failed, 23 passed, 12 deselected, 5 warnings in 29.55s
```

The first caught a missing `scene_location` parameter in the maturation helper;
the second caught the existing manifest schema-version trigger; the third
caught missing JSON codecs in the newly added real async-acceptance fixture.
Each was fixed. The final required PostgreSQL selection includes all these tests.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
15 failed, 2663 passed, 877 skipped, 9 warnings in 98.94s (0:01:38)
```

This pre-merge diagnostic run caught SQL-shape and frontier-setting expectations
in existing recording fixtures, plus the new field description exceeding the
wire's 70-character budget. Existing fixtures were updated, the description was
shortened, and the final offline gate was rerun after merge.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_orrery/test_retrograde_maturation.py
```

```text
1 failed, 29 passed, 4 skipped, 5 warnings in 0.76s
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_commit_handler_sync.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_persistence.py
```

```text
1 failed, 66 passed, 5 skipped, 5 warnings in 1.22s
67 passed, 5 skipped, 5 warnings in 1.25s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_character_identity_pg.py::test_identity_maturation_failure_class_is_durable_and_terminal
```

```text
1 passed, 5 warnings in 1.51s
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_skald_wire.py tests/test_trait_compiler.py
```

```text
129 passed, 2 skipped, 5 warnings in 1.06s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py -k 'identity_declaration_binds'
```

```text
3 failed, 3 passed, 20 deselected, 5 warnings in 7.12s
6 passed, 20 deselected, 5 warnings in 7.55s
```

The failed run caught `deepcopy` attempting to pickle `asyncpg.Record`. Batch
validation now copies only mutable index containers and preserves read-only row
evidence. All six sync/async exact, alias, and novel/idempotent cases then passed.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_commit_handler.py tests/test_commit_handler_sync.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_persistence.py tests/test_skald_wire.py tests/test_trait_compiler.py
```

```text
210 passed, 7 skipped, 5 warnings in 1.71s
```

Black formatted changed Python files during development. The final check covers
every Python file changed against `origin/main`; its exact command and output
are in `verification.md`. Both commit hooks passed on fix commit `85f2fb7f`.
The clean main merge is `c74eec9c`.

## Third-Round Review Validation

The initial focused failure was the prior prose-remainder expectation for character ambiguity; it now expects the terminal exception. The initial consumer failure was an incorrect assumption that disabling title stripping disables surname review. The initial offline run exposed four stale SQL-fixture assumptions and two missing reachability-baseline entries; these were repaired before the final gates. Its run overlapped editing and is diagnostic, not final evidence. New consumer behavior is proved through real PostgreSQL; the existing sync cursor adapter was maintained for the offline orchestration suite.

### Initial Focused Diagnostics

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_trait_compiler.py tests/test_presence_roster.py > /tmp/nexus-799-third-focused.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_trait_compiler.py::test_ambiguous_target_name_is_structured_remainder
1 failed, 74 passed, 5 warnings in 0.65s
```

### Initial Consumer Proofs

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_identity_consumers_pg.py > /tmp/nexus-799-third-consumers.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_identity_consumers_pg.py::test_identity_policy_reference_and_pair_hint[strip_titles-False-Lady Ada-Lady Ada-Lady Fox-Lady Fox-Ada]
1 failed, 7 passed, 5 warnings in 8.53s
```

### Corrected Consumer Proofs

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_identity_consumers_pg.py > /tmp/nexus-799-third-consumers-fixed.log 2>&1
```

```text
8 passed, 5 warnings in 8.15s
```

### Corrected Focused Diagnostics

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_character_identity.py tests/test_trait_compiler.py tests/test_presence_roster.py > /tmp/nexus-799-third-focused-fixed.log 2>&1
```

```text
75 passed, 5 warnings in 0.62s
```

### Initial Offline Diagnostics

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-third-offline-initial.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_commit_handler.py::test_async_reconciled_mentions_flow_through_adapter_and_commit
FAILED tests/test_commit_handler_sync.py::test_sync_commit_links_same_turn_character_declaration
FAILED tests/test_commit_handler_sync.py::test_sync_reconciled_mentions_flow_through_adapter_and_commit
FAILED tests/test_commit_handler_sync.py::test_bootstrap_commit_seeds_setting_for_next_presence_baseline
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
6 failed, 2680 passed, 891 skipped, 9 warnings in 100.20s (0:01:40)
```

### Combined Focused Proofs

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_identity_consumers_pg.py tests/test_character_identity.py tests/test_trait_compiler.py tests/test_presence_roster.py > /tmp/nexus-799-third-focused-final.log 2>&1
```

```text
83 passed, 5 warnings in 8.16s
```

### Adapter and Reachability Regression Checks

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler.py tests/test_commit_handler_sync.py tests/test_reachability.py > /tmp/nexus-799-third-adapters.log 2>&1
```

```text
58 passed, 1 skipped, 5 warnings in 7.92s
```

### Final Offline Gate

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-third-offline-final.log 2>&1
```

```text
2686 passed, 891 skipped, 9 warnings in 100.42s (0:01:40)
```

### Final Requested PostgreSQL Gate

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed' > /tmp/nexus-799-third-pg-final.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
3 failed, 190 passed, 2 skipped, 1412 deselected, 9 warnings in 70.63s (0:01:10)
```

### Final Black Check

```sh
git diff origin/main --name-only -- '*.py' | xargs /Users/pythagor/nexus/.venv/bin/python -m black --check > /tmp/nexus-799-third-black.log 2>&1
```

```text
All done! ✨ 🍰 ✨
28 files would be left unchanged.
```

### Final Reachability Check

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py > /tmp/nexus-799-third-reachability-final.log 2>&1
```

```text
    "migration": 172,
    "test": 235
  },
  "test_only": 34,
  "existing_unreachable": 85,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

### Full-Gate Acceptance Fixture Follow-Up

The first full PostgreSQL run was interrupted with SIGINT after its nonexempt failure was reproduced independently: the pre-existing acceptance fixture lacked a frontier setting. Commit `b52ef431` supplies the setting in that disposable fixture; it does not relax runtime validation. The entire acceptance file then passes. The full gate was restarted.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-third-full-pg.log 2>&1
```

```text
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/encodings/utf_8.py:15: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
11 failed, 331 passed, 3 skipped, 11 warnings, 4 errors in 135.26s (0:02:15)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_acceptance_staging_pg.py::test_staging_resolves_same_turn_declarations_only_on_acceptance > /tmp/nexus-799-third-acceptance-diagnostic.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_api/test_acceptance_staging_pg.py::test_staging_resolves_same_turn_declarations_only_on_acceptance
1 failed, 7 warnings in 1.54s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_acceptance_staging_pg.py > /tmp/nexus-799-third-acceptance-fixed.log 2>&1
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
18 passed, 7 warnings in 20.35s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Black After the Acceptance Fixture Correction

```sh
git diff origin/main --name-only -- '*.py' | xargs /Users/pythagor/nexus/.venv/bin/python -m black --check > /tmp/nexus-799-third-black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
29 files would be left unchanged.
```

### Disposable Schema Fixture Repairs

The second full run was interrupted after two fixture schema failures were isolated: the slot-lock fixture omitted the production generation-session tables, and the private lifecycle databases lacked migration 123 because the fleet template is intentionally unchanged. The standalone slot-lock reproduction confirmed the missing table. Commit `db255876` loads migrations 098/121 and a real session into the former, and applies migration 123 only to private lifecycle databases when absent. Both fixtures then pass, including the real CLI/gateway/TEST wizard lifecycle. No fixture names or database prefixes were changed.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-third-full-pg-final.log 2>&1
```

```text
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/psycopg2/__init__.py:122: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
12 failed, 741 passed, 6 skipped, 11 warnings, 4 errors in 294.36s (0:04:54)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_slot_mutation_guard.py::test_locked_slot_rejects_http_side_effects_and_database_writes > /tmp/nexus-799-third-slot-guard.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_api/test_slot_mutation_guard.py::test_locked_slot_rejects_http_side_effects_and_database_writes
1 failed, 7 warnings in 1.10s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_slot_mutation_guard.py::test_locked_slot_rejects_http_side_effects_and_database_writes tests/test_connection_lifecycle.py > /tmp/nexus-799-third-fixture-repairs.log 2>&1
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 7 warnings in 67.92s (0:01:07)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Final Main Merge

`git fetch origin && git merge origin/main` brought in `725d4203` (PR #930). Only the reachability baseline reason conflicted; both module sets and the prompt-registry retirements were preserved. Merge commit `a516210a` passed both hooks. The worktree import was reverified, and final post-merge gates follow in the verification document.

### Completed Full-Gate Fixture Audit

The first completed full PostgreSQL run had eight failures outside #885. Four required migration 123 in their fixture databases; two used a SimpleNamespace instead of the current OrreryTickProposal; one declaration acceptance lacked a setting, leaving an incubator row that caused the subsequent test's duplicate-key failure. Commit `3e35daa7` fixes these setups. Existing fixture names remain unchanged. Retrograde maturation/project tests now use migrated disposable copies of save_02, rather than requiring a forbidden fleet migration.

The same commit prevents None/empty/whitespace persistent references from binding a title-only canonical name after normalization; a real PostgreSQL regression checks that guard.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus-799-third-merged-full-pg.log 2>&1
```

```text
103 failed, 3415 passed, 49 skipped, 11 warnings, 32 errors in 909.06s (0:15:09)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_identity_consumers_pg.py tests/test_orrery/test_knowledge_surfacing_live.py tests/test_orrery/test_retrograde_maturation.py tests/test_orrery/test_retrograde_projects_live.py tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_need_clock_anchor_pg.py::test_atomic_transition_replaces_stale_clock_before_protagonist_trigger > /tmp/nexus-799-third-full-repairs.log 2>&1
```

```text
90 passed, 5 warnings in 49.10s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_identity_consumers_pg.py > /tmp/nexus-799-third-empty-reference.log 2>&1
```

```text
9 passed, 5 warnings in 9.25s
```

A final `git fetch origin && git merge origin/main` after `3e35daa7` reported `Already up to date.` at `725d4203`; the worktree import was verified again before the final reruns.

## Final Verified Gates

These final runs follow `3e35daa7`; all failures in the full gate are covered by #885, as enumerated in the verification document.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2708 passed, 892 skipped, 9 warnings in 113.67s (0:01:53)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed'
```

```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
3 failed, 191 passed, 2 skipped, 1412 deselected, 9 warnings in 114.61s (0:01:54)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q
```

```text
95 failed, 3424 passed, 49 skipped, 11 warnings, 32 errors in 1067.16s (0:17:47)
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py
```

```text
    "migration": 173,
    "test": 236
  },
  "test_only": 34,
  "existing_unreachable": 75,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

```sh
git diff origin/main --name-only -- '*.py' | xargs /Users/pythagor/nexus/.venv/bin/python -m black --check
```

```text
All done! ✨ 🍰 ✨
35 files would be left unchanged.
```

Codex, running gpt-6-astra.

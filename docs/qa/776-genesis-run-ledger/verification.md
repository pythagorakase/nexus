# STOP-REPORT: 776-S1a

Implementation stopped at the first proof run because the frozen order's
incomplete-transition premise is false at base `9ac0caf6`. No PR was opened,
no branch was pushed, and this partial implementation is not ready to land.
The latest fetched `origin/main` was `d05481d8`; no rebase was attempted after
the stop condition. This report records partial work, not a completed proof.

## Binding Stop Rule

The working rules at
`/Users/pythagor/nexus/temp/orders_2026_09_30/_common_codex.md` say:
“If the order's premise turns out to be false, write a stop-report instead of
improvising.” The user's instruction repeats that rule. I did not change the
mapper, the schema validator, or the existing staging fixture to make the
specified tests pass.

## False Premise and Diagnosis

The order specifies `zone=None` as an incomplete transition that the real
mapper refuses with `ValueError("Transition data is incomplete")`, including
the skipped TEST-model case with no open stage row. The actual staged fixture
sets `ready_for_transition=True` and `validated=True` at
`tests/test_orrery/test_retrograde_wizard_live.py:261-262`.
`TransitionData.validate_completeness` at
`nexus/api/new_story_schemas.py:1374-1404` recomputes those flags only when all
required fields are present; with a missing zone it returns the existing true
flag. Therefore the mapper's guard at
`nexus/api/new_story_db_mapper.py:525-542` does not reject the data. It enters
the world transaction, reaches `create_location_hierarchy` at `:652`, and raises
`AttributeError: 'NoneType' object has no attribute 'name'` at `:175`.

These three unchanged files have no diff against the base. The proof's actual
stack (first failing test) is:

```text
nexus/api/new_story_flow.py:661: in perform_transition_with_retrograde
    mapper.perform_transition(transition_data, in_transaction=_persist_hook)
nexus/api/new_story_db_mapper.py:652: in perform_transition
    location_ids = self.create_location_hierarchy(
nexus/api/new_story_db_mapper.py:469: in create_location_hierarchy
    return _execute_hierarchy(cursor)
nexus/api/new_story_db_mapper.py:395: in _execute_hierarchy
    zone_record = self.map_zone_to_db(zone, layer_id)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <nexus.api.new_story_db_mapper.NewStoryDatabaseMapper object at 0x1335a2910>
zone = None, layer_id = 1

    def map_zone_to_db(self, zone: ZoneDefinition, layer_id: int) -> Dict[str, Any]:
        """
        Map ZoneDefinition to zones table format.
    
        Database columns:
        - name, summary, layer (FK)
        - boundary (PostGIS polygon, not set during creation)
    
        Args:
            zone: ZoneDefinition from structured output
            layer_id: ID of the parent layer
    
        Returns:
            Dictionary ready for database insertion
        """
        return {
>           "name": zone.name,
            "summary": zone.summary,
            "layer": layer_id,
            # boundary will be NULL initially (can be set later with PostGIS)
        }
E       AttributeError: 'NoneType' object has no attribute 'name'

nexus/api/new_story_db_mapper.py:175: AttributeError

```

The same AttributeError occurs in
`test_failure_is_recorded_at_each_stage[persistence]` and
`test_failure_is_recorded_at_each_stage[None]`. These are unexpected failures;
I did not reclassify them as acceptable or replace the required assertions.

A corrected, database-free reproduction was run from this worktree:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'from nexus.api.new_story_schemas import TransitionData; d=TransitionData.model_construct(setting=None, character=None, seed=None, layer=None, zone=None, location=None, base_timestamp=None, thread_id=None, ready_for_transition=True, validated=True); print("zone:", d.zone); print("ready_for_transition:", d.ready_for_transition); print("validated:", d.validated); print("validate_completeness():", d.validate_completeness())'
```

```text
zone: None
ready_for_transition: True
validated: True
validate_completeness(): True
```

An earlier exploratory reproduction omitted required model_construct fields
and itself raised `AttributeError: 'TransitionData' object has no attribute
'setting'`; the corrected reproduction above supplies every accessed field.

## Partial Files Changed

- `migrations/141_genesis_run_ledger.sql`: COMMENT-complete retained run and stage tables with wall-clock timestamps and the specified constraints.
- `nexus/agents/orrery/retrograde_orchestrator.py`: durable ledger writers/readers and generation output callbacks; process registry removed.
- `nexus/api/new_story_flow.py`: per-attempt ledger, all-stage failure recording, and transaction-coupled persistence/skip completion.
- `nexus/api/wizard_chat.py`: durable status read through asyncio.to_thread, including run_status and error.
- `nexus.toml`: removed the process-local operating note.
- `docs/database.md`: described the ledger and its transaction boundary.
- `docs/orrery_retrograde_spec.md`: changed status-record lifetime documentation.
- `tests/test_api/test_genesis_ledger_pg.py`: specified disposable PostgreSQL proofs, including the three failing required assertions.
- `tests/test_api/test_route_capabilities.py`: player status proof routed through offline_gate_db on slot 4.
- `tests/test_api/test_wizard_weird_level.py`: adjusted ledger boundaries and transaction statement assertions.
- `tests/test_orrery/test_retrograde_orchestrator.py`: removed process-registry tests and asserted stage output callbacks.
- `docs/qa/776-genesis-run-ledger/verification.md`: this stop-report and exact evidence.

The UI implementation and Vitest changes have not begun. `npm --prefix ui ci`,
UI tests/check, the offline suites, reachability, flake8, and mypy have not run.
No full PostgreSQL gate was run (the user's newer sequencing instruction assigns
that gate to the coordinator). No migrated-clone catalog snapshot or read-only
owner wizard listing was collected before the stop. No resumable output reuse,
input fingerprint writes, bootstrap ownership, or wizard-cache cutover was added.

## Commands and Verbatim Tails

Import provenance, run before trusting test results:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/776-genesis-run-ledger/nexus/__init__.py
```

Formatting:

```sh
/Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/orrery/retrograde_orchestrator.py nexus/api/new_story_flow.py nexus/api/wizard_chat.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_orrery/test_retrograde_orchestrator.py
```

```text
reformatted tests/test_api/test_genesis_ledger_pg.py
reformatted tests/test_orrery/test_retrograde_orchestrator.py
reformatted nexus/api/new_story_flow.py
reformatted nexus/agents/orrery/retrograde_orchestrator.py
reformatted tests/test_api/test_wizard_weird_level.py
reformatted nexus/api/wizard_chat.py

All done! ✨ 🍰 ✨
6 files reformatted, 1 file left unchanged.
```

Proof set (foreground shell command, harness returned a session; waited until
exit before continuing; exit 1):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_route_capabilities.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_mock_wizard_responses.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_owner_target_guard.py --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/pytest-proof > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/776-S1a/proof.log 2>&1
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: nexus_m10_fresh_test_49901, nexus_m10_template_test_49901, nexus_test_issue_613_*, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_offline_gate_* x12, qa640_renamed_test_model_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_genesis_ledger_pg.py::test_stage_rows_and_outputs_persist
FAILED tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[persistence]
FAILED tests/test_api/test_genesis_ledger_pg.py::test_failure_is_recorded_at_each_stage[None]
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
4 failed, 327 passed, 7 warnings in 50.34s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

```

Migration sequence failure is expected under the user's sequencing update:

```text
E       AssertionError: assert {'013', '119', '140'} == frozenset({'013', '119'})
E         Extra items in the left set:
E         '140'
```

`KNOWN_GAPS` was not changed, and migration 140 was not taken.

Migration comments check:

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
```

## Scope and Coordinator Questions

The pytest secret-store guard denied nexus-api and the test-only provider guard
was not overridden. The dbname audit reported owner targets: none; the proofs
used disposable clones through offline_gate_db. The change adds no code that
resets wizard caches or accesses save_05 specifically. No gateway was started,
and no migration was applied to an owner save or NEXUS_template. This is offline
protocol/storage evidence only; it does not qualify any live provider.

1. Should the frozen order be amended to set ready_for_transition=False as well
   as zone=None for the validation-refusal proofs, or is a separate fix for
   TransitionData.validate_completeness required first? Either choice needs the
   coordinator's revised scope; this run did neither.
2. Once that premise is resolved, should implementation resume from this partial
   branch or should the coordinator issue a new order? UI reattach and the
   remaining proof gates are outstanding.

If this work later lands, the original notes still apply: migration 141 after
139 and 140; coordinator fleet migration then locked-slot-1 migration; owner
gateway restart and UI rebuild; no affected wizard caches, save_05 untouched.
Gateway death/run ownership and reattach after world commit remain deferred to
S1b/Q5 and S2 respectively. No landing is authorized by this report.

Authored by Codex, running GPT-6.

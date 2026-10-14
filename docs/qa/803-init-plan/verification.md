# Init Plan Verification

## Lane Source Checkpoint (Codex, Before Assembly)

The lane was authored by Codex on base `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`
(commit `3e1f537a`, merged into the wave-B assembly at `a3d271fa`) without
running the order's Proof Expected. Base `4ae8b8d2` predates the 811-S3a,
803-S1, 803-S7, 822-S1 and 812-S3 merges on the integration head; the assembly
moved the canonical documents' `verified_commit` stamps (AGENTS.md,
docs/turn_flow_sequence.md, Decision 0009) to `f073b371`, so the lane's own
restamp of Decision 0009 is superseded. The lane recorded these source
preparation commands (their output is the lane's; they were not rerun here
except as the checks below):

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black nexus/cli.py nexus/cli_contract.py nexus/runtime/init_plan.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
3 files reformatted, 2 files left unchanged.

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --write
Wrote docs/cli_reference.md

nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/check_reachability.py --write-baseline --reason '#803 S6: nexus/runtime/init_plan.py is imported by nexus/cli.py (run_init), so it joins production_reachable'
maintained: 399; production reachable: 219; no reported findings
```

The lane's earlier sentence "Two independent source reviews found no blocking
defect" had no recorded command or artifact behind it and is withdrawn. What is
known is the independent Opus review of the integrated lane (nine findings, two
refuters each), whose findings this fix applies.

## Integrated-Tree Proof (2026-10-13)

Run by the wave-B fixer (Claude Opus 5.5) in worktree
`.claude/worktrees/fix-803-s6`, branch `claude/waveb-fix-803-s6`, on commit
`266f4e5ac0bc799e1c8f7aaaa35032b23409c042` (integration head `7eb9a10c` plus the
one-line import fix below). Every command ran from the worktree root with the
shared interpreter; PostgreSQL runs had `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`
and `NEXUS_SLOT` unset (`env -u ...`). Import check:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/fix-803-s6/nexus/__init__.py
```

Machine load before each PostgreSQL run (`uptime`, one-minute average): 7.22,
9.25, 12.77 and 11.57. None exceeded 24, so no wait loop ran.

### The Import Fix

811-S3a moved the migration runner to `nexus.maintenance.migrate` and left
`scripts/migrate.py` as a re-export shim, so the lane's
`monkeypatch.setattr(migrate, "TEMPLATE_DB", ...)` on the shim never reached
readiness, which reads `nexus.maintenance.migrate.TEMPLATE_DB`. Both PostgreSQL
tests then planned against the owner's real `NEXUS_template` (and, in the
no-template test, the unrouted `save_NN`). Commit `266f4e5a` changes
`tests/test_runtime/test_init_plan_pg.py:23` from `from scripts import migrate`
to `from nexus.maintenance import migrate`, as order item 10 and
`tests/test_runtime/test_readiness_pg.py:34` require. Nothing else in the file
changed.

### Focused PostgreSQL Proof

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py tests/test_runtime/test_readiness_pg.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_readiness.py tests/test_cli_contract.py tests/test_cli_reference_doc.py
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
...............................................                          [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 17 targets: postgres, qa640_1013_readiness_* x2, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
263 passed in 212.18s (0:03:32)
```

The order says this lane adds no migration and tightens no contract, so
`tests/test_orrery/test_card_identity.py` and `tests/test_connection_lifecycle.py`
are not owed; they run in the coordinator's whole-tree gate.

Clone cleanup, after the focused run and again after the red run below (empty
output both times):

```text
psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_803s6%'"
(no output; exit 0)
```

### Gate Finding of 2026-10-09

The whole-tree gate on this head failed
`test_plan_without_template_blocks_its_dependents` with
`assert 'postgres.reachable' == 'template.present'`. After the import fix it
passes, and it reads no owner database:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -rA -p tests.dbname_audit "tests/test_runtime/test_init_plan_pg.py::test_plan_without_template_blocks_its_dependents"
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 1 targets: postgres
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
PASSED tests/test_runtime/test_init_plan_pg.py::test_plan_without_template_blocks_its_dependents
1 passed in 0.19s
```

### Plan Samples From Step (d)

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s -p tests.dbname_audit "tests/test_runtime/test_init_plan_pg.py::test_plan_names_pending_migrations_in_registry_order"
```

Printed text plan:

```text
1. template.migrations_current: python scripts/migrate.py --template
2. slots.migrations_current: python scripts/migrate.py --slot 1 --write-locked-slot; python scripts/migrate.py --slot 2
```

Printed `--json` plan:

```json
{
  "blocked": [],
  "ok": false,
  "schema_version": 1,
  "steps": [
    {
      "check_id": "template.migrations_current",
      "number": 1,
      "observed": "qa640_803s6_template_bb948528d631: 1 pending (151)",
      "remediation": "python scripts/migrate.py --template"
    },
    {
      "check_id": "slots.migrations_current",
      "number": 2,
      "observed": "qa640_803s6_slot1_beeb5ebb0cae: 1 pending (151); qa640_803s6_slot2_29bbd7b145ba: 1 pending (151); qa640_803s6_slot3_d41daaaf37e6 at 151; qa640_803s6_slot4_3f0366050dd0 at 151; qa640_803s6_slot5_270518215781 at 151",
      "remediation": "python scripts/migrate.py --slot 1 --write-locked-slot; python scripts/migrate.py --slot 2"
    }
  ],
  "target": "owner-host"
}
```

Tail:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 15.84s
```

### Red Run: Sort-by-ID Plant

The plant (applied in the worktree, never committed):

```diff
--- a/nexus/runtime/init_plan.py
+++ b/nexus/runtime/init_plan.py
@@ -52,7 +52,7 @@ def plan_from_report(report: ReadinessReport) -> InitPlan:
         raise ValueError("An init plan cannot use a report with omitted checks")
     steps: list[PlanStep] = []
     blocked: list[str] = []
-    for check in report.checks:
+    for check in sorted(report.checks, key=lambda c: c.id):  # RED PLANT
         if check.status == "fail":
             if check.remediation is None:
                 raise RuntimeError(
```

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
...
_______________ test_plan_lists_failed_checks_in_report_order _________________
E       AssertionError: assert ['slots.migra...ools.pg_dump'] == ['template.mi...ools.pg_dump']
E         At index 0 diff: 'slots.migrations_current' != 'template.migrations_current'
tests/test_runtime/test_init_plan.py:118: AssertionError
...
_____________ test_plan_names_pending_migrations_in_registry_order _____________
E       AssertionError: assert ['slots.migra...ions_current'] == ['template.mi...ions_current']
E         At index 0 diff: 'slots.migrations_current' != 'template.migrations_current'
tests/test_runtime/test_init_plan_pg.py:145: AssertionError
...
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_init_plan.py::test_plan_lists_failed_checks_in_report_order
FAILED tests/test_runtime/test_init_plan.py::test_plan_lists_skipped_checks_as_blocked
FAILED tests/test_runtime/test_init_plan.py::test_init_plan_matches_doctor_under_a_broken_config
FAILED tests/test_runtime/test_init_plan_pg.py::test_plan_names_pending_migrations_in_registry_order
FAILED tests/test_runtime/test_init_plan_pg.py::test_plan_without_template_blocks_its_dependents
5 failed, 6 passed in 15.40s
```

Both tests the order names fail on step order. The other three fail on the
order of `blocked` (`'slots.idf_analyzer_current' != 'template.present'` at
`test_init_plan.py:153`, `'slots.idf_analyzer_current' !=
'template.migrations_current'` at `test_init_plan_pg.py:195`) and on doctor
parity (`'models.artifacts' != 'postgres.reachable'` at
`test_init_plan.py:216`). The file was restored from a byte copy and proved
clean:

```text
cp <scratch>/init_plan.py.orig nexus/runtime/init_plan.py && git diff --quiet -- nexus/runtime/init_plan.py && echo "restored: git diff --quiet exit 0"
restored: git diff --quiet exit 0
```

### Offline Suites

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3192 passed, 671 skipped, 8 warnings in 640.80s (0:10:40)
```

This run outlived the ten-minute command limit; the harness moved it to the
background and the fixer polled its log to completion before continuing.

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
11 failed, 1896 passed, 1517 skipped, 7 warnings in 48.46s
```

None of the sixteen failures is in a file this lane or this fix changed (the
fix changes one import line of `tests/test_runtime/test_init_plan_pg.py`); they
belong to other wave-B lanes and go to the coordinator for triage:

- `test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module` reports
  only `tests/test_orrery/test_place_point_required_pg.py:11` (the other stale
  811-S3a import, owned by another lane's fixer). Before this fix it would also
  have reported `tests/test_runtime/test_init_plan_pg.py:23`.
- The two `test_lore` failures are a changed Gaia prompt fingerprint and a Gaia
  prompt of 732 words against a bound of 700.
- `test_skald_wire.py` reports a changed description,
  `NewEntityDeclaration.coordinates`.
- The `test_orrery/test_worker.py` and `test_config.py` failures are settings
  validation errors (`orrery.projects.milestone_magnitude must be >=
  orrery.promote.magnitude_threshold`; `claim_event_types contains event types
  emitted by background branches: ['ate']`).
- `test_wizard_agent.py` and `test_wizard_confirmation.py` fail in the wizard
  transition path.

### Reachability, Front Matter and CLI Reference

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 20.12s

PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m scripts.render_cli_reference --check
(no output; exit 0)
```

The lane's `config/reachability_baseline.json` delta (`git diff 0cc63fa9
a3d271fa -- config/reachability_baseline.json`) changed only `reason` and added
`"nexus/runtime/init_plan.py"` to `production_reachable`. The assembly later
replaced the reason with the combined wave-B reason; at this head the path is
still present (`config/reachability_baseline.json:268`).

### Static Checks

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/runtime/init_plan.py nexus/cli.py nexus/cli_contract.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
All done! ✨ 🍰 ✨
5 files would be left unchanged.

PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/runtime/init_plan.py nexus/cli.py nexus/cli_contract.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
Success: no issues found in 5 source files

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/runtime/init_plan.py nexus/cli.py nexus/cli_contract.py tests/test_runtime/test_init_plan.py tests/test_runtime/test_init_plan_pg.py
nexus/cli.py:983:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4486:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4997:89: E501 line too long (113 > 88 characters)
nexus/cli.py:5026:89: E501 line too long (118 > 88 characters)
nexus/cli.py:5066:89: E501 line too long (90 > 88 characters)
nexus/cli.py:5151:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5177:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5178:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5197:89: E501 line too long (101 > 88 characters)
```

`origin/main` (`f073b371`) comparison, with `git show origin/main:<path>` into
a scratch directory and the worktree's `.flake8`:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m flake8 --config <worktree>/.flake8 nexus/cli.py nexus/cli_contract.py
nexus/cli.py:981:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4349:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4845:89: E501 line too long (113 > 88 characters)
nexus/cli.py:4874:89: E501 line too long (118 > 88 characters)
nexus/cli.py:4914:89: E501 line too long (90 > 88 characters)
nexus/cli.py:4999:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5025:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5026:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5045:89: E501 line too long (101 > 88 characters)
```

Same nine diagnostics with the same lengths, moved by inserted lines; `git
blame` attributes all nine head lines to September commits (`df88c7c8`,
`1099ea5b`, `20e2c07b`, `71c0bd13`). No new diagnostic. Mypy is clean at head,
so it adds none.

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

### Gateway Import Grep (Landing Note)

```text
grep -rln --include='*.py' --exclude=init_plan.py 'cli_contract\|nexus.cli import\|init_plan' nexus/api nexus/runtime
(no output; exit 1)
```

The gateway imports none of the changed Python files, so no gateway restart is
owed. No migration, no fleet application, no `ui/` change.

### Cited Lines on the Integrated Tree

- `nexus/cli.py:5446-5458` registers `init` with a required `--plan` and no
  `--apply`; `run_init` is at `:4644`, after `run_doctor` (`:4626`); `_dispatch`
  routes `init` at `:6343`, after `doctor` at `:6341`.
- `nexus/cli_contract.py:110-111` gives `doctor` and `init` `local_operator`;
  `:215` is `SELF_DIAGNOSTIC_COMMANDS = frozenset({"doctor", "init",
  "receipts"})` (806-S1 added `receipts`).
- `docs/runtime.md:341` is the CLI Surface line; `:439-448` is the paragraph;
  `:453` ends "playability are later slices of #803."
- `nexus/config/loader.py:293-298` records a `config.load_settings` failure
  receipt when configuration loading fails, which is the write the wording
  below accounts for.

### Coordinator's Steps

- The whole-tree PostgreSQL gate, including `tests/test_orrery/test_card_identity.py`
  and `tests/test_connection_lifecycle.py`: coordinator's step.
- State-surface regeneration: coordinator's step (no `ui/` change here).
- Fleet migrations: coordinator's step (this lane has none).
- No paid call and no owner service was needed; `nexus init --plan` was never
  run against the owner host, because `secrets.seat_providers` reads the
  platform secret store.

## Whole-Tree Failure at the Integration Head (2026-10-13)

Run by the wave-B fixer (Claude Opus 5.5) in worktree
`.claude/worktrees/fix-803-s6`, branch `claude/waveb-fix-803-s6`, cut from the
final integration head `a984e79089758eff6859e0a27db7142db1e58ebf`. Every
command ran from the worktree root with the shared interpreter, `nice -n 15`
and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. One-minute
load (`uptime`) before the PostgreSQL runs: 5.77, 7.60, 5.36, 9.66, 9.77,
9.26, 9.79 and 8.22. None exceeded 24, so no wait loop ran. The import
check `PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed
`/Users/pythagor/nexus/.claude/worktrees/fix-803-s6/nexus/__init__.py`.

### The Finding

The coordinator's gate log `temp/orders_2026_10_07/coord/waveb2-wholetree-a984e790.log`
records `test_plan_without_template_blocks_its_dependents` failing with
`AssertionError: assert 'postgres.reachable' == 'template.present'`.

### Diagnosis: A Server Outage, Not a Patch Target or Leaked State

The same gate log shows that PostgreSQL was unreachable during that run:

```text
grep -c 'failed: timeout expired' temp/orders_2026_10_07/coord/waveb2-wholetree-a984e790.log
1971
grep -c 'verify "trust"' temp/orders_2026_10_07/coord/waveb2-wholetree-a984e790.log
0
```

The run ended `203 failed, 5138 passed, 215 skipped, 8 warnings, 1765 errors
in 6075.07s (1:41:15)`. In the same file, the sibling
`test_plan_names_pending_migrations_in_registry_order` errored at fixture setup
(`tests/test_runtime/test_init_plan_pg.py:64`, `disposable_slot_database` ->
`assert_one_target("postgres")` -> `psycopg2.OperationalError: connection to
server on socket "/tmp/.s.PGSQL.5432" failed: timeout expired`), and every
failing `tests/test_runtime/test_readiness_pg.py` test shows the same timeout.
The no-template test opens no fixture connection, so the plan ran its
`postgres.reachable` check against the unreachable server, that check failed
first, and `template.present` became a blocked dependent. The plan was correct;
the outage looked like an assertion failure. The `scripts.migrate` patch-target
fix (`266f4e5a`) is present at this head
(`tests/test_runtime/test_init_plan_pg.py:20` imports
`nexus.maintenance.migrate`), and no cached readiness state is involved: the
three ruled orders below are green on the integration head.

### Reproduction Orders on `a984e790` (All Green)

Alone:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py
..                                                                       [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2 passed in 15.24s
```

After `tests/config` and the first PostgreSQL file of the gate, in one session:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/config tests/test_api/test_acceptance_staging_pg.py tests/test_runtime/test_init_plan_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 26 targets: postgres, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, qa640_acceptance_* x19
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
159 passed, 7 warnings in 68.59s (0:01:08)
```

The whole `tests/test_runtime` directory:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime
........................................................................ [ 29%]
........................................................................ [ 59%]
........................................................................ [ 89%]
.........................                                                [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 18 targets: postgres, qa640_1013_readiness_* x2, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
241 passed in 181.28s (0:03:01)
```

### Red: The Gate's Failure Reproduced by an Unreachable Server (`a984e790`)

`[api.database]` in `nexus.toml` leaves `port` absent, so `PGPORT` selects the
port (`nexus/database.py:158-163`). `PGPORT=1` names a port with no server,
which stands in for the outage without a plant in any file:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PGPORT=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py
>       assert step.check_id == "template.present"
E       AssertionError: assert 'postgres.reachable' == 'template.present'
E         
E         - template.present
E         + postgres.reachable

tests/test_runtime/test_init_plan_pg.py:189: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 1 targets: postgres
dbname audit: owner server: local:1
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_init_plan_pg.py::test_plan_without_template_blocks_its_dependents
ERROR tests/test_runtime/test_init_plan_pg.py::test_plan_names_pending_migrations_in_registry_order
1 failed, 1 error in 0.24s
```

This is the gate's pattern exactly: the sibling errors at setup and the
no-template test fails on `postgres.reachable`.

### The Fix (`d226faa4`)

`tests/test_runtime/test_init_plan_pg.py` adds a `reachable_server` fixture
that runs `pg_fixtures.assert_one_target("postgres")`, the same probe the clone
fixtures run first, and the no-template test takes it. An unreachable server
now errors at setup like every other PostgreSQL test. The test also compares
the whole plan step (number, check id, observed text and remediation) instead
of its fields one at a time, so a real mismatch prints the observed text. No
assertion was removed or loosened; the step number is now asserted too.

### Green and Outage Tails on `d226faa4`

The same unreachable-server run now errors both tests at setup:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PGPORT=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 1 targets: postgres
dbname audit: owner server: local:1
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
ERROR tests/test_runtime/test_init_plan_pg.py::test_plan_names_pending_migrations_in_registry_order
ERROR tests/test_runtime/test_init_plan_pg.py::test_plan_without_template_blocks_its_dependents
2 errors in 0.17s
```

The ruled focused set:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py tests/test_runtime/test_readiness_pg.py tests/test_script_wrappers.py
................                                                         [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 17 targets: postgres, qa640_1013_readiness_* x2, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
16 passed in 46.54s
```

The two whole-tree consumers (run on the uncommitted change that became
`d226faa4`; the change touches only the test file above):

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
receipt isolation: checkout and user receipts untouched
dbname audit: 6 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:58497 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:58498 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:58497 (psycopg2), save_04@local:58498 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
10 passed, 2 skipped, 2 warnings in 41.89s
```

The two skips are `tests/test_orrery/test_card_identity.py:122: Set
NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.` The
`secret-store guard` line of this run sits above the eight lines kept here.

Static checks on the changed file:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black tests/test_runtime/test_init_plan_pg.py
All done! ✨ 🍰 ✨
1 file left unchanged.
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m flake8 tests/test_runtime/test_init_plan_pg.py
(no output; exit 0)
PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases tests/test_runtime/test_init_plan_pg.py
Success: no issues found in 1 source file
```

Clone sweep after the runs (empty output):

```text
psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_803s6%' OR datname LIKE 'readiness803%'"
(no output; exit 0)
```

### Coordinator's Steps

- A quiet whole-tree gate on the next integration head: coordinator's step. The
  `a984e790` gate cannot judge any PostgreSQL test, because the server timed
  out throughout it.
- State-surface regeneration and fleet migrations: coordinator's steps (this
  fix has neither).

## Deliberate Departure From the Order's Verbatim Text

Order items 2, 4 and 8 gave the module docstring, the `--plan` help and the
`docs/runtime.md` paragraph as "changes nothing" / "writes nothing", quoting
Decision 803-Q2. With an invalid `nexus.toml`, the `config.valid` check calls
`load_settings`, which records a #806 failure receipt
(`nexus/config/loader.py:293-298`); `test_init_plan_matches_doctor_under_a_broken_config`
asserts the receipts. The lane therefore wrote "applies no setup changes" and
added "Existing diagnostic failure receipts are still recorded when
configuration loading fails." The coordinator ruled on 2026-10-09 (#803
comment, 03:35) that this truthful wording stands: the plan changes no
database, file or setting, and a failed check still leaves its #806 failure
receipt. The same wording is in `nexus/runtime/init_plan.py:3-4`,
`nexus/cli.py:5455`, `docs/runtime.md:440-442` and the regenerated
`docs/cli_reference.md:118`.

## PR Body Notes

- Deliberate departure: the `--plan` help, the module docstring and the
  `docs/runtime.md` paragraph say "applies no setup changes" rather than the
  order's "changes nothing", and the paragraph adds the failure-receipt
  sentence, because `load_settings` records a #806 receipt under a broken
  config (`nexus/config/loader.py:293-298`). Ruled by the coordinator in #803
  on 2026-10-09.
- Deferred: `--apply` stays parked under 803-Q2. `doctor` and `init` open each
  readiness slot database read-only under owner-host while `COMMAND_TRANSPORTS`
  declares them `local_operator`; the Transport Rule calls such a handler
  `database`. Route to #817.
- Landing: no migration, no fleet application, no gateway restart (grep above
  prints nothing), no UI rebuild.

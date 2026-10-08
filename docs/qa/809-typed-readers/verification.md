# 809-S1 Typed Settings Readers

Status: source implementation and the ordered 12-case offline red/green proof
are complete. PostgreSQL, static comparison and coordinated integration proof
remain pending. No publication or merge readiness is claimed.

The coordinator separately admitted a lightweight Black/source checkpoint.
Black completed over all 32 changed or added Python files: 10 reformatted,
22 unchanged. Its output is [black-source-checkpoint.txt](black-source-checkpoint.txt).
This is formatting evidence only; it does not substitute for green tests or
the ordered comparison of static diagnostics.

Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`.
Branch: `codex/809-typed-readers`.
Order: `temp/orders_2026_10_07/809-S1.md`, bound by the
[recorded Q9 ruling](https://github.com/pythagorakase/nexus/issues/809#issuecomment-5915947649).

## Initial Red Before Product Changes

The ordered file was authored while every product file still matched the base.
The exact invocation, cleared environment key names, base, import path and load
are recorded in [initial-red.json](initial-red.json). The complete unchanged
output is [initial-red.txt](initial-red.txt).

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  -p tests.dbname_audit -p no:cacheprovider tests/config/test_typed_readers.py
```

The process ran in this exact worktree with its absolute `PYTHONPATH`, no
PostgreSQL opt-in, disabled Keychain, cleared runtime/database routing and
`PYTEST_*` overrides, and a 120-second deadline. Import admission returned
`/Users/pythagor/.codex/worktrees/resume-typed-readers/nexus/nexus/__init__.py`.
The one-minute load was 23.219. The process completed normally with test exit 1.

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner targets: none
11 failed, 1 passed in 1.11s
```

Every failure was inspected:

| Case | Initial Failure |
| --- | --- |
| Product AST closure | Exactly the six ordered modules import or call the facade. |
| API constraints table absent | Validation incorrectly succeeds. |
| Choice-text limit absent | Validation incorrectly succeeds. |
| Section helper identity/refusal | `Settings.require_orrery` is absent. |
| Promotion without Orrery | Slot resolution happens before section admission. |
| Narration without Orrery | Default configuration reaches slot resolution. |
| Maturation drain without Orrery | Reconstructing `dict(Settings)` raises unrelated correspondence validation. |
| Maturation enqueue without Orrery | Default configuration reaches slot resolution. |
| Experiences without Orrery | Mapping reader calls missing `Settings.get`. |
| Scheduler without Orrery | Mapping reader subscripts `Settings`. |
| Scheduler without runtime | Mapping reader subscripts `Settings`. |

The exact by-alias Orrery dump parity guard passed. The new file installs a
connection-refusal tripwire even when included later in a PostgreSQL-enabled
session. The tripwire raises pytest's failure outcome, which cannot satisfy the
required `RuntimeError`. The scheduler's explicit database is the unused
disposable name `qa640_809_unused`; no connection was attempted.

## Bounded Green and Source Checkpoint

The same exact offline command passed on source commit
`dec6f76cfdf559e89cda2085817aa1afdaf1d9ec`, under the same 120-second deadline,
cleared environment, exact import path and connection-refusal tripwire. The
one-minute load was 7.593. Original metadata and output are retained in
[initial-green.json](initial-green.json) and [initial-green.txt](initial-green.txt).

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner targets: none
12 passed in 0.90s
```

No source correction was needed after this green run. The source checkpoint's
normal commit hooks passed the catalog regeneration, configuration/model-ID
validation and exception-disposition checks. The migration-comment hook had no
applicable files. Two independent source reviews found no blocker in the ten
production conversions; the review of partial maturation tables and queued-model
identity tests found their prior semantics preserved. These are source reviews,
not additional runtime proof.

## Source Changes and Caller Adaptations

The API constraints table and choice-text limit become required. `Settings.api`
remains optional; its absent-section reader raises explicitly. Orrery and
runtime admission methods retain section identity and name the requiring
operation. Workers, maturation, experiences, seat capture and scheduler now
receive `Settings`. Promotion admits Orrery before attempting a connection.

The accepted-chunk operation loads once, dumps only the Orrery section with
aliases for the unchanged engine, and shares the typed object with experience
and checkpoint readers. Developer endpoints use the same explicit mapping
boundary. The attempt-manifest dump/hash and facade exports remain unchanged.
Source search now finds `load_settings_as_dict` under `nexus/` only in
`nexus/config/__init__.py` and `nexus/config/loader.py`.

Adapted existing caller files:

- `tests/pg_fixtures.py`
- `tests/test_api/test_attempt_manifest_pg.py`
- `tests/test_api/test_narrative_jobs_pg.py`
- `tests/test_api/test_narrative_summary_paid_pg.py`
- `tests/test_api/test_orrery_config_reuse_pg.py`
- `tests/test_api/test_scheduler_locked_pg.py`
- `tests/test_api/test_scheduler_pg.py`
- `tests/test_api/test_seat_policy_jobs_pg.py`
- `tests/test_api/test_summary_budget_usage.py`
- `tests/test_live_gate_clones_pg.py`
- `tests/test_orrery/test_acquisition_scan_pg.py`
- `tests/test_orrery/test_character_experiences_pg.py`
- `tests/test_orrery/test_embedding_audit.py`
- `tests/test_orrery/test_experience_enqueue_gin_pg.py`
- `tests/test_orrery/test_live_cycle.py`
- `tests/test_orrery/test_narration_job_fencing_pg.py`
- `tests/test_orrery/test_retrograde_maturation.py`
- `tests/test_orrery/test_stage2a_status_live.py`
- `tests/test_orrery/test_worker.py`
- `tests/test_pg_experience_seeds.py`
- `tests/test_presence_roster_pg.py`

`tests/settings_helpers.py`, settings parity and assembled-prompt fingerprint
tests are unchanged. Facade values feeding only unchanged mapping consumers
remain mappings. The API config-reuse regression blocks both facade exports,
records one returned `Settings`, and requires checkpoint object identity plus
the existing exact tick keyword values.

Three adaptations preserve previously tested meaning under validation:

- The retired narration provider key now fails while constructing `Settings`.
  Only that test's worker call and lease-update assertion are retired, as
  ordered; an invalid settings object cannot reach the worker.
- An explicit zero embedding request still returns before reading a missing
  Orrery section. Default work refuses that section, and a separate assertion
  retains rejection of configured `max_embeddings_per_drain=0`.
- The rendering pin proof uses another registered model and asserts it differs
  from the captured job model, replacing the formerly unchecked invalid literal
  `render-time-model`. Partial maturation tables retain model defaults plus the
  configured seat ID that the old subsection merge used to supply.

The newer `seed_experience_candidates` and `seed_experience_render_job` fixture
helpers accept typed settings. Their existing disposable-target check remains
before settings access or connection; the invalid-settings owner-refusal
controls in `test_pg_disposable_target.py` stay unchanged.

## Canonical Source Review

Reverified `AGENTS.md`, `docs/turn_flow_sequence.md`, and decisions 0010, 0016,
0017, 0019, 0027, 0044 and 0055 before moving their stamps to the frozen main
base. All quoted text, source lists, kinds and bodies are unchanged. Seat
precedence, commit ordering, scheduler lease/queue order, deterministic
descriptors, provider-era provenance columns and story-derived weirdness remain
unchanged. Maturation is still accepted-branch-only and one-shot: its entity job
uniqueness and already-connected guard remain intact. The scheduler mention in
the decisions README is a fenced example, not a source declaration.

## Remaining Proof and Landing Scope

After the coordinator grants the test slot: run the ordered focused groups and
all adapted non-live consumers, including `test_pg_experience_seeds.py`,
`test_pg_disposable_target.py`, card identity and connection lifecycle. Execute
`test_stage2a_status_live.py` in the shared PostgreSQL proof: despite its name,
it carries only `requires_postgres` and uses the routed disposable TEST clone.
Keep live-provider flags unset. Collect the two edited live/paid files only
(`test_live_cycle.py`, `test_narrative_summary_paid_pg.py`); never enable live
inference. Run document/reachability checks and compare Black, flake8,
mypy and exception-disposition diagnostics with the frozen base. The
coordinator owns full integration validation and publication.

No migration, fleet application, UI change or UI build is required. Product
changes require a gateway restart when services next run. `nexus.toml`, scripts,
`ir_eval/`, owner resources and model files are unchanged. The remaining #809
slices and owner question Q1 stay open.

Codex — GPT-6

# Verification for #1007: One Bare-Name Entity Ref Contract

Branch `claude/1007-bare-entity-refs`, cut from `origin/main` at 9a67e864. All commands ran from the worktree root with the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`); `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` were unset.

## Deterministic Replay

`PYTHONPATH=$PWD $PY docs/qa/1007-bare-entity-refs/replay_target_ref.py` (adapted from `temp/qa_night_2026-09-29_123541Z/contract_target_ref.py`; no model calls):

```
{"nexus_module": "/Users/pythagor/nexus/.claude/worktrees/1007-bare-entity-refs/nexus/__init__.py"}
{"step": 1, "candidate_target": "character:Vale", "rejected_by": "ValidationError", "error": "candidates.0.project_intent.target_ref: Value error, entity ref carries an entity-kind prefix (for example 'character:Vale'); write the bare proper name ('Vale') and let the kind field or project_type carry the kind (value_error)"}
{"step": 2, "matching_name_control": "accepted", "target_ref": "Vale"}
{"step": 3, "different_target": "Orla", "error": "- project plan seed 'seed_001' changes target_ref from 'Vale' to 'Orla'"}
```

Before this change the same step one printed `{"candidate_target_accepted": "character:Vale"}` and every expansion replay failed with `changes target_ref from 'character:Vale' to 'Vale'` (`temp/qa_night_2026-09-29_123541Z/contract-target-ref-result.jsonl`). Now the seed stage rejects the prefix with the fixed bare-name message (the value is not echoed), the bare/bare control passes, and a genuinely different target is still rejected by the strict comparison.

## Live Proof (Bounded)

Invocation one, exactly as the order specified:

```
NEXUS_RUN_LIVE_LLM=1 NEXUS_RETROGRADE_LIVE_MODEL=gpt-5.6-terra $PY -m pytest -q -s -o log_cli=true --log-cli-level=INFO --basetemp=temp/1007-live tests/test_orrery/test_retrograde_live.py::test_live_retrograde_seed_and_expansion_round_trip 2>&1 | tee docs/qa/1007-bare-entity-refs/live.log
```

Usage line (verbatim from `live.log`; `*.log` is gitignored, so the committed copy is `live-log.txt`):

```
INFO     nexus.usage:usage.py:279 USAGE provider=openai model=gpt-5.6-terra seat=retrograde_seed_candidates slot=- run=- attempt=1 outcome=accepted in=11249 out=1367 total=12616 cached=0 reasoning=758 tier=default effort=- max_output=8000
```

Cross-check, `temp/1007-live/test_live_retrograde_seed_and_0/usage/usage-2026-09-29.jsonl` (the only usage file under `temp/1007-live`):

```
{"ts":"2026-09-29T17:05:33.496283Z","quota_day":"2026-09-29","provider":"openai","model":"gpt-5.6-terra","seat":"retrograde_seed_candidates","slot":null,"run_id":null,"attempt":1,"outcome":"accepted","transport":"responses","request_id":"resp_09c8a209af4cd8b8006abbefc8fcc087d1ae5fb67520323527","input_tokens":11249,"output_tokens":1367,"total_tokens":12616,"cached_input_tokens":0,"cache_creation_tokens":null,"reasoning_tokens":758,"service_tier":"default","aggregate":false,"requests":null,"reasoning_effort":null,"max_output_tokens":8000}
```

Entity refs the validated live seed response carried (from the test's `print`):

```
SEED_ENTITY_REF seed_ledger_scar.events.participating_entities "Mara"
SEED_ENTITY_REF seed_ledger_scar.events.participating_entities "Ledger Court"
SEED_ENTITY_REF seed_ledger_scar.pair_tags.subject_ref "Mara"
SEED_ENTITY_REF seed_ledger_scar.pair_tags.object_ref "Ledger Court"
SEED_ENTITY_REF seed_ledger_scar.claimed_edges.open_endpoint_name "Ledger Court"
SEED_ENTITY_REF seed_ledger_scar.claimed_edges.open_endpoint_name "Ledger Court"
SEED_ENTITY_REF seed_voice_hunt.events.participating_entities "Mara"
SEED_ENTITY_REF seed_voice_hunt.events.participating_entities "Vale"
SEED_ENTITY_REF seed_voice_hunt.pair_tags.subject_ref "Mara"
SEED_ENTITY_REF seed_voice_hunt.pair_tags.object_ref "Vale"
SEED_ENTITY_REF seed_voice_hunt.claimed_edges.open_endpoint_name "Vale"
SEED_ENTITY_REF seed_voice_hunt.claimed_edges.open_endpoint_name "Vale"
SEED_ENTITY_REF seed_voice_hunt.project_intent.target_ref "Vale"
```

Repair attempts: none. `live.log` carries no `structured-output rejected` line and the only usage row is `attempt=1 outcome=accepted`. Every ref is a bare name, including `project_intent.target_ref "Vale"`, the field that carried `character:Sister Orla` in #1007.

Outcome: the test **failed** after the seed stage, at its own pre-existing assertion `assert seed_response["selected_seed_ids"]` (the model returned an empty `selected_seed_ids`), so the expansion seat never ran. That assertion is about the model's selection, not about refs; the seed response passed wire and contract validation. Tokens spent: 12,616 of the 120,000 bound. Per the order, the second invocation runs only if the first passes, so it was not run.

## Offline Gate

`$PY -m pytest -q`:

```
=========================== short test summary info ============================
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
1 failed, 4065 passed, 1048 skipped, 7 warnings in 310.32s (0:05:10)
```

The one failure is pre-existing and unrelated: `tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants` asserts `"rather than invent"` in `prompts/storyteller_gaia.md`, which lacks that phrase at 9a67e864 (`git show origin/main:prompts/storyteller_gaia.md`). It fails identically on a `git archive 9a67e864` export. This branch touches neither file.

## PostgreSQL Gate

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/`:

```
176 failed, 1414 passed, 39 skipped, 7 warnings, 28 errors in 265.03s (0:04:25)
```

Baseline, same command against a `git archive 9a67e864` export (`PYTHONPATH` pointed at the export):

```
177 failed, 1387 passed, 39 skipped, 7 warnings, 28 errors in 272.81s (0:04:32)
```

The branch failure set (`pg_orrery_failures_branch.txt`, 204 ids) is identical to the baseline's except that the baseline also fails `tests/test_orrery/test_config.py::test_orrery_settings_load_queue_and_resolution_defaults` (`pg_orrery_failures_diff_vs_main.txt`). No failing test is in a file this branch changes. Root errors in the log: `IDF analyzer mismatch for corpus narrative: rebuild required` (140 lines), `need-clock anchor unavailable: no canonical world time or base_timestamp` (32), `cannot unpack non-iterable NoneType object` (19); `save_05` appears 24 times (#885). The +27 passed are the new tests in this branch.

## Lint and Type Checks

```
$PY -m black --check <changed .py files>
All done! ✨ 🍰 ✨
9 files would be left unchanged.
$PY -m flake8 <changed .py files>
(no output, exit 0)
$PY -m mypy <changed .py files>
Success: no issues found in 9 source files
```

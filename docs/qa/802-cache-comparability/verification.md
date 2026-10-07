# Verification: Cache Comparability in `usage_totals`; the Tag Utilization Report (#802 S1b, S5)

Work order 802-S1b, branch `claude/802-cache-and-tag-report`, cut from
`origin/main` at `364fef4b`. No migration, no paid call, no gateway lane, no
write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`.
Decision 802-Q3 (D, mark non-comparable, defer normalisation) and Decision 9
of #858 (tokens only) bind.

## Cited Lines, Rechecked at `364fef4b`

Each line the order cites was read in this worktree before the change.

- `nexus/telemetry/turn_observation.py:370-374`: `usage_totals` holds
  `critical_path`, `background` and `overall`. `_sum_totals` (`:671-681`) adds
  each field of `USAGE_TOKEN_FIELDS` (`:125-131`) over every reported section,
  whatever its provider; `_overall_totals` (`:739-754`) adds the two parts the
  same way.
- `nexus/telemetry/usage.py:587-644`: `record_openai_response` stores
  `input_tokens` (Responses) or `prompt_tokens` (chat completions), which
  include cached input, and sets no `cache_creation_tokens` (`:625-641`).
  `:647-686`: `record_anthropic_response` stores Anthropic's raw
  `input_tokens`, which excludes cache reads and writes. `:543-566`:
  `record_token_estimate` adds both back only for the drift log line and the
  manifest's `reported_input_tokens`.
- `turn_observation.py:78-81`: the limit was stated only in prose. An
  attempt's usage names one provider (`_agreed`, `:543-545`); a job's names one
  provider or a sorted list (`_profile`, `:585`); the legacy block names none
  (`_legacy_block`, `:694-706`); the legacy source is appended at `:718`; the
  empty background is `:722-728`.
- `SCHEMA_VERSION = 2` (`:120`); version paragraph `:97-105`. `docs/cli.md:366`
  said "schema version 2". Tests pinned 2 at `tests/test_turn_observation.py:575`
  and `tests/test_api/test_attempt_manifest_pg.py:296`.
- `scripts/api_anthropic.py:1001-1008`: the structured Anthropic path sends a
  scalar `system` with no `cache_control`.
- Issue #802 body line 50 lists "Tag utilization report command" among the
  absorbed reader ideas. `nexus/cli.py:5267-5283` holds only `tags audit`
  (#811); `grep -n utilization nexus/cli.py` finds nothing. The map line
  `/Users/pythagor/nexus/temp/brainstorm_2026_09_04/maps/gap-04-tag-vocabulary-utilization-and-the-tag-l.md:95`
  (read-only, gitignored) specifies the report. Issue #757 had no comments.
- Importers of `turn_observation` at `364fef4b`: `nexus/cli.py` (loaded per
  call, `:4576` and `:6011`) and `scripts/qa_shift/envelope_measure.py`
  (reads only `attempts`).
- Declared sources: none of the changed files (`nexus/telemetry/turn_observation.py`,
  `tests/test_turn_observation.py`, `tests/test_api/test_attempt_manifest_pg.py`,
  `docs/cli.md`, this file) appears in the `sources:` of `AGENTS.md`,
  `docs/turn_flow_sequence.md` or `docs/decisions/README.md`.

## Live Usage Ledger, Read Only

Every event in `/Users/pythagor/nexus/.nexus/runtime/usage/usage-*.jsonl`,
counted by `(provider, transport)` on 2026-10-07 (read with `cat` piped into
an isolated `python -I` counter; nothing written):

```
648 ('openai', 'responses')
171 ('openai', 'pydantic_ai')
14 ('test', 'pydantic_ai')
6 ('test', 'responses')
2 ('anthropic', 'anthropic_messages')
841
```

No live turn mixes providers today; the flag is for the turn that does.

## What Changed

- `_section_providers` reads a reported section's `provider` (a list gives its
  set, a string gives itself; anything else raises).
- `_sum_totals` and `_overall_totals` add `providers` (sorted union) and
  `comparable` (`len(providers) <= 1`) after `events`. The legacy source names
  `_profile` of its events' providers; the legacy block keeps its shape. The
  empty background carries `providers: []`, `comparable: true`.
- `format_turn_summary` ends the Critical path, Background and Overall lines
  with ` · providers differ: <names>` when the sum is not comparable.
- `SCHEMA_VERSION = 3`; the module docstring and `docs/cli.md` say so. No total
  changed and nothing is normalised; `usage.py` and `attempt_manifest.py` are
  untouched.

## Red Run

With the new tests written, `"comparable": True` was planted in `_sum_totals`
and `_overall_totals` (reverted before the commit):

```
=================================== FAILURES ===================================
/Users/pythagor/nexus/.claude/worktrees/802-cache-and-tag-report/tests/test_turn_observation.py:907: assert True is False
/Users/pythagor/nexus/.claude/worktrees/802-cache-and-tag-report/tests/test_turn_observation.py:990: AssertionError: assert {'background'...enai'], True)} == {'background'...nai'], False)}
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_turn_observation.py::test_usage_totals_mark_sums_across_providers_not_comparable
FAILED tests/test_turn_observation.py::test_background_and_overall_comparability_follow_their_own_providers
2 failed, 41 deselected in 0.60s
```

Line 907 is `assert critical_path["comparable"] is False`; line 990 is the
three-part `(providers, comparable)` assertion, whose `overall` differs.

## Issue Comments (802-S5)

- #757: https://github.com/pythagorakase/nexus/issues/757#issuecomment-6043365748
- #802: https://github.com/pythagorakase/nexus/issues/802#issuecomment-6043367735

## Proof Tails

PostgreSQL set, `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit -p no:warnings tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_lore/test_window_coverage_pg.py tests/test_owner_target_guard.py
.......................                                                  [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_756s1_distinct_*, qa640_756s1_generation_* x2, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_800b_inspect_*, qa640_802_reported_*, qa640_814_seats_*, qa640_historical_coverage_* x3, qa640_window_coverage_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
93 passed, 2 skipped in 59.95s
```

The two skips are `tests/test_lore/test_window_coverage_pg.py:488` ("Set
NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.").

Offline:

```
$ $PY -m pytest -q -p no:warnings tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2945 passed, 559 skipped in 639.92s (0:10:39)

$ $PY -m pytest -q -p no:warnings tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
655 passed, 262 skipped in 48.78s

$ $PY -m pytest -q -p no:warnings tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1210 passed, 1107 skipped in 19.71s

$ $PY -m pytest -q -p no:warnings tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed in 28.55s

$ $PY -m pytest -q tests/test_turn_observation.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
43 passed, 5 warnings in 1.57s
```

Static checks on the three changed Python files, branch against their
`origin/main` versions:

- Black: `3 files would be left unchanged.`
- flake8: the same 15 pre-existing `E501` lines in
  `tests/test_api/test_attempt_manifest_pg.py` on both sides (on the branch
  the ones after `:296` sit 12 lines lower); none in the other two files.
- `mypy --explicit-package-bases`: one identical pre-existing error on both
  sides, `tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs
  not installed for "requests"  [import-untyped]`.
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`

## Landing Notes

No migration and no fleet application; no UI change, rebuild or state-surface
regeneration. The CLI loads `turn_observation` per call and
`envelope_measure` reads only `attempts`, so no gateway restart is owed.
On #802: S1b and S5 are done; S2 (Backstage read) and S3 (golden-path proof)
stay open.

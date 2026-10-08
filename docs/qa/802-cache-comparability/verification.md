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
counted by `(provider, transport)` on 2026-10-07 (read-only: `cat` piped into
an isolated `python -I` counter; nothing written). First read at `d94681d8`;
the same command, rerun at `797205b5`, gave the identical output below:

```
$ PY=/Users/pythagor/nexus/.venv/bin/python
$ cat /Users/pythagor/nexus/.nexus/runtime/usage/usage-*.jsonl | $PY -I -c 'import collections,json,sys; c=collections.Counter((e.get("provider"),e.get("transport")) for e in map(json.loads,filter(str.strip,sys.stdin))); [print(n,k) for k,n in c.most_common()]; print(sum(c.values()))'
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
and `_overall_totals` (reverted before the commit). The run below was repeated
at `d94681d8` with the plant reapplied and then reverted, so the command that
produced the tail is on record:

```
$ PYTHONPATH=$PWD $PY -m pytest -q --tb=line -p no:warnings tests/test_turn_observation.py -k "comparab"
FF                                                                       [100%]
=================================== FAILURES ===================================
/Users/pythagor/nexus/.claude/worktrees/802-cache-and-tag-report/tests/test_turn_observation.py:907: assert True is False
/Users/pythagor/nexus/.claude/worktrees/802-cache-and-tag-report/tests/test_turn_observation.py:990: AssertionError: assert {'background'...enai'], True)} == {'background'...nai'], False)}
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_turn_observation.py::test_usage_totals_mark_sums_across_providers_not_comparable
FAILED tests/test_turn_observation.py::test_background_and_overall_comparability_follow_their_own_providers
2 failed, 41 deselected in 1.32s
```

Line 907 is `assert critical_path["comparable"] is False`; line 990 is the
three-part `(providers, comparable)` assertion, whose `overall` differs.

## Issue Comments (802-S5)

- #757: https://github.com/pythagorakase/nexus/issues/757#issuecomment-6043365748
- #802: https://github.com/pythagorakase/nexus/issues/802#issuecomment-6043367735

## Proof Tails

Where a tail below names no commit, it ran on the tree at `5f1de28d`, the
implementation commit (`d94681d8` added only this file); the split offline
rerun names `d94681d8`, and the static checks and ledger counts name
`797205b5`. `7f6fa0e2` changed only this file.

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

Offline. The non-api, non-orrery piece (`tests --ignore=tests/test_api
--ignore=tests/test_orrery`) ran at `d94681d8` as four sequential pieces that
together collect the same files: `tests/test_lore`, the other subdirectories,
the top-level files `a` to `m` plus the two `*_test.py` files, and the
top-level files `n` to `z`. Their sums (2945 passed, 559 skipped) equal the
single run they replace:

```
$ PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
414 passed, 55 skipped in 37.28s

$ PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/config tests/test_config tests/test_ir_eval_v2 tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
544 passed, 26 skipped in 152.00s (0:02:32)

$ PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_[a-m]*.py tests/*_test.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
748 passed, 199 skipped in 305.72s (0:05:05)

$ PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_[n-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1239 passed, 279 skipped in 90.87s (0:01:30)

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
`origin/main` versions, run at `797205b5` by
`scratchpad/802-S1b/static2.sh` (session scratchpad, not committed), which
prints each command before its verbatim output and exit status. The names it
uses:

```
W=/Users/pythagor/nexus/.claude/worktrees/802-cache-and-tag-report
M=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/802-S1b/main
PY=/Users/pythagor/nexus/.venv/bin/python
FILES="nexus/telemetry/turn_observation.py tests/test_turn_observation.py tests/test_api/test_attempt_manifest_pg.py"
# origin/main copies, made before the main-side runs:
for f in $FILES; do git show origin/main:$f > $M/$f; done
cp $W/pyproject.toml $W/.flake8 $M/
```

```
### branch (cwd $W, HEAD 797205b5)
$ $PY -m black --check $FILES
All done! ✨ 🍰 ✨
3 files would be left unchanged.
[exit 0]

$ $PY -m flake8 $FILES
tests/test_api/test_attempt_manifest_pg.py:82:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:133:89: E501 line too long (121 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:137:89: E501 line too long (138 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:141:89: E501 line too long (126 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:157:89: E501 line too long (166 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:162:89: E501 line too long (106 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:238:89: E501 line too long (100 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:259:89: E501 line too long (96 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:441:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:449:89: E501 line too long (125 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:480:89: E501 line too long (111 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:484:89: E501 line too long (122 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:510:89: E501 line too long (93 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:527:89: E501 line too long (118 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:547:89: E501 line too long (91 > 88 characters)
[exit 1]

$ PYTHONPATH=$W $PY -m mypy --explicit-package-bases $FILES
tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_api/test_attempt_manifest_pg.py:10: note: Hint: "python3 -m pip install types-requests"
tests/test_api/test_attempt_manifest_pg.py:10: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_api/test_attempt_manifest_pg.py:10: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
Found 1 error in 1 file (checked 3 source files)
[exit 1]

### origin/main copies (cwd $M, origin/main 364fef4b)
$ $PY -m black --check $FILES
All done! ✨ 🍰 ✨
3 files would be left unchanged.
[exit 0]

$ $PY -m flake8 $FILES
tests/test_api/test_attempt_manifest_pg.py:82:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:133:89: E501 line too long (121 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:137:89: E501 line too long (138 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:141:89: E501 line too long (126 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:157:89: E501 line too long (166 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:162:89: E501 line too long (106 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:238:89: E501 line too long (100 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:259:89: E501 line too long (96 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:429:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:437:89: E501 line too long (125 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:468:89: E501 line too long (111 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:472:89: E501 line too long (122 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:498:89: E501 line too long (93 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:515:89: E501 line too long (118 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:535:89: E501 line too long (91 > 88 characters)
[exit 1]

$ MYPYPATH=$W $PY -m mypy --explicit-package-bases $FILES
tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_api/test_attempt_manifest_pg.py:10: note: Hint: "python3 -m pip install types-requests"
tests/test_api/test_attempt_manifest_pg.py:10: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_api/test_attempt_manifest_pg.py:10: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
Found 1 error in 1 file (checked 3 source files)
[exit 1]
```

Conclusion: no new diagnostics. Black is clean on both sides. flake8 reports
the same 15 pre-existing `E501` lines in
`tests/test_api/test_attempt_manifest_pg.py` on both sides; the seven after
`:296` sit 12 lines lower on the branch (the added `providers`/`comparable`
assertions), and none falls on a changed line. mypy reports the same one
pre-existing error on both sides (`requests` stubs, `:10`).

```
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Landing Notes

No migration and no fleet application; no UI change, rebuild or state-surface
regeneration. The CLI loads `turn_observation` per call and
`envelope_measure` reads only `attempts`, so no gateway restart is owed.
On #802: S1b and S5 are done; S2 (Backstage read) and S3 (golden-path proof)
stay open.

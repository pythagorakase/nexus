# Issue 811 Slice A: Stale Vocabulary and Dead Helpers Verification

Branch `claude/811-stale-vocab-dead-helpers`, cut from `origin/main` at
3ca248df, on 2026-09-29. No migration. No `save_NN` database or
`NEXUS_template` was written; the SQL below is read-only, and the
PostgreSQL tests ran on the disposable databases their fixtures create and
drop.

## Deprecated-Category Baseline (Read-Only)

Active `entity_tags` rows whose tag belongs to a category that
`tag_category_registry` marks deprecated. This is the baseline slice B's
`nexus tags audit` verb must report.

```sql
SELECT count(*)
FROM entity_tags et
JOIN tags t ON t.id = et.tag_id
JOIN tag_category_registry r ON r.category = t.category
WHERE r.deprecated AND et.cleared_at IS NULL;
```

| Database | Active deprecated-category rows |
|---|---|
| `save_01` | 0 |
| `save_02` | 0 |
| `save_03` | 4 |
| `save_04` | 6 |
| `save_05` | 0 |

Breakdown (same predicate, grouped by category and tag):

| Slot | Category | Tag | Rows |
|---|---|---|---|
| 03 | `orrery_signal` | `debt_pulse_active` | 1 |
| 03 | `place_affordance` | `worksite` | 1 |
| 03 | `profession_lite` | `black_market_operator` | 2 |
| 04 | `legitimacy_status` | `gray_legal` | 1 |
| 04 | `orrery_signal` | `debt_pulse_active` | 2 |
| 04 | `place_affordance` | `worksite` | 1 |
| 04 | `profession_lite` | `black_market_operator` | 2 |

## The Runtime Tag Library Still Lists `place_affordance`

`nexus/agents/orrery/tag_library.py:104-107` filters `t.deprecated = FALSE`
and `t.synonym_for IS NULL` but not `r.deprecated`. Every slot still holds 25
non-deprecated tags under the deprecated `place_affordance` category:

```
$ psql -d save_NN -Atc "select r.category, r.deprecated, count(t.*) filter (where not t.deprecated) from tag_category_registry r left join tags t on t.category=r.category where r.category='place_affordance' group by 1,2"
save_02..save_05: place_affordance|t|25
```

So the tag library appended to the wizard and Skald prompts still offers
those 25 tags (visible in `docs/qa/742-scene-order/after-gaia.txt:2327`).
This slice fixes the hand-written prompt text only; filtering the library by
category deprecation is registry enforcement and stays on #811.

## Obsolete Embedding Redirects

The two `run_in_clone` wrappers rewrote a `scripts/regenerate_embeddings.py
--database` subprocess into `--db-url`. PR #940 (b2e764b9) removed that
spawn from acceptance: acceptance now enqueues `narrative_embedding_jobs`
(`nexus/jobs/embeddings.py:50`) and the scheduler embeds in process
(`nexus/jobs/embeddings.py:105`). `git grep regenerate_embeddings -- nexus`
returns nothing. Both tests pass without the wrappers on disposable clones:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/proofs/proof_session_truth.py
1 passed, 9 warnings in 93.22s (0:01:33)
```

(`qa640_775_browser_*` data clone of read-only `save_04`, lane 8014 free
before and after, built reader from `npm --prefix ui ci && npm --prefix ui
run build` inside the worktree.)

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rA tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_character_identity_pg.py
PASSED tests/test_api/test_attempt_manifest_pg.py::test_manifest_reference_privacy_retention_and_readonly
PASSED tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation
PASSED tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset
PASSED tests/test_api/test_attempt_manifest_pg.py::test_inspect_turn_pre_session_chunk_and_duplicate_sessions
...
15 passed, 9 warnings in 37.99s
```

## Gates

- Offline `$PY -m pytest -q`: `1 failed, 4142 passed, 1074 skipped in
  282.32s`. The one failure,
  `tests/test_turn_observation.py::test_attempts_without_manifests_read_the_window_ledger_safely`,
  is a UTC-midnight rollover: the suite ran across 2026-09-30 00:00 UTC and
  the module computes `TODAY` at import (`tests/test_turn_observation.py:44`).
  Rerun alone: `13 passed in 1.25s`. Failure tail from the `-q` run:

  ```
          observation = observe_turn(inspection, slot=4, read_at=READ_AT)

          assert observation["terminal_outcome"] is None
          assert observation["ledger_days_read"] == [str(TODAY)]
          assert observation["wall_time"]["seconds"] == UNKNOWN
  >       (attempt,) = observation["attempts"]
  E       ValueError: not enough values to unpack (expected 1, got 0)

  tests/test_turn_observation.py:825: ValueError
  ```

  The `ledger_days_read == [str(TODAY)]` assertion held: the observation
  read the import-time day's ledger. The attempts list came back empty
  because `record_prompt_window` names its file from the wall clock
  (`nexus/telemetry/usage.py:808-809`, `windows-{day}.jsonl`), so after
  midnight the records landed in the next day's file, which the observation
  did not read.
- PostgreSQL set (`NEXUS_RUN_POSTGRES=1`, gateway variables unset):
  `tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_character_identity_pg.py
  tests/test_orrery/test_tag_library.py tests/test_orrery/test_tag_writer.py
  tests/test_place_tag_manifest.py tests/test_orrery_tag_validation.py` →
  `1 failed, 107 passed, 1 skipped`. The failure is
  `test_tag_library.py::test_contextual_library_save_05_completeness_and_size`
  (`save_05 must contain current entity tags`), and the skip is the save_05
  namespace proof: both are the known empty-slot-5 exemption (#885).
- Prompt readers: `tests/test_prompt_lint.py tests/test_skald_wire.py
  tests/test_lore/test_two_pass_pipeline.py
  tests/test_lore/test_logon_prompt_formatting.py` → `219 passed, 2 skipped`.
- `tests/test_reachability.py` → `38 passed`;
  `scripts/check_reachability.py` reports no newly unreachable modules and no
  baseline entries to add or remove, so the baseline is unchanged.
- Black, flake8 and mypy on the changed Python files. The branch runs are
  in this worktree. The origin/main runs use the same file list in a
  `git archive origin/main` export (094e6063; none of these files changed
  between the merge base 3ca248df and 094e6063), where `files.txt` holds the
  branch command's file list. `$PY` is
  `/Users/pythagor/nexus/.venv/bin/python`.

  Black, branch:

  ```
  $ git diff --name-only origin/main...HEAD -- '*.py' | xargs $PY -m black --check
  All done! ✨ 🍰 ✨
  13 files would be left unchanged.
  ```

  flake8, branch (exit 1):

  ```
  $ git diff --name-only origin/main...HEAD -- '*.py' | xargs $PY -m flake8
  tests/proofs/proof_session_truth.py:71:89: E501 line too long (124 > 88 characters)
  tests/proofs/proof_session_truth.py:78:89: E501 line too long (176 > 88 characters)
  tests/proofs/proof_session_truth.py:99:89: E501 line too long (248 > 88 characters)
  tests/proofs/proof_session_truth.py:127:89: E501 line too long (96 > 88 characters)
  tests/proofs/proof_session_truth.py:175:89: E501 line too long (94 > 88 characters)
  tests/proofs/proof_session_truth.py:240:89: E501 line too long (109 > 88 characters)
  tests/proofs/proof_session_truth.py:257:89: E501 line too long (99 > 88 characters)
  tests/proofs/proof_session_truth.py:396:89: E501 line too long (94 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:71:89: E501 line too long (131 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:122:89: E501 line too long (121 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:126:89: E501 line too long (138 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:130:89: E501 line too long (126 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:146:89: E501 line too long (166 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:151:89: E501 line too long (106 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:227:89: E501 line too long (100 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:248:89: E501 line too long (96 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:394:89: E501 line too long (131 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:402:89: E501 line too long (125 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:433:89: E501 line too long (111 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:437:89: E501 line too long (122 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:463:89: E501 line too long (93 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:480:89: E501 line too long (118 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:500:89: E501 line too long (91 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:8:1: F401 'tests.test_presence_roster_pg.roster_database' imported but unused
  tests/test_orrery/test_character_identity_pg.py:14:59: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:40:55: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:67:5: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:100:89: E501 line too long (98 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:202:5: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:237:72: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:246:68: F811 redefinition of unused 'roster_database' from line 8
  tests/test_orrery/test_character_identity_pg.py:269:89: E501 line too long (92 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:290:89: E501 line too long (115 > 88 characters)
  ```

  flake8, origin/main, same files (exit 1):

  ```
  $ cat files.txt | xargs $PY -m flake8
  tests/proofs/proof_session_truth.py:92:89: E501 line too long (124 > 88 characters)
  tests/proofs/proof_session_truth.py:99:89: E501 line too long (176 > 88 characters)
  tests/proofs/proof_session_truth.py:120:89: E501 line too long (248 > 88 characters)
  tests/proofs/proof_session_truth.py:148:89: E501 line too long (96 > 88 characters)
  tests/proofs/proof_session_truth.py:196:89: E501 line too long (94 > 88 characters)
  tests/proofs/proof_session_truth.py:261:89: E501 line too long (109 > 88 characters)
  tests/proofs/proof_session_truth.py:278:89: E501 line too long (99 > 88 characters)
  tests/proofs/proof_session_truth.py:417:89: E501 line too long (94 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:71:89: E501 line too long (131 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:122:89: E501 line too long (121 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:126:89: E501 line too long (138 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:130:89: E501 line too long (126 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:146:89: E501 line too long (166 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:151:89: E501 line too long (106 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:247:89: E501 line too long (100 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:268:89: E501 line too long (96 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:414:89: E501 line too long (131 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:422:89: E501 line too long (125 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:453:89: E501 line too long (111 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:457:89: E501 line too long (122 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:483:89: E501 line too long (93 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:500:89: E501 line too long (118 > 88 characters)
  tests/test_api/test_attempt_manifest_pg.py:520:89: E501 line too long (91 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:12:1: F401 'tests.test_presence_roster_pg.roster_database' imported but unused
  tests/test_orrery/test_character_identity_pg.py:18:59: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:44:55: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:69:53: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:117:5: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:150:89: E501 line too long (98 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:252:5: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:287:72: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:296:68: F811 redefinition of unused 'roster_database' from line 12
  tests/test_orrery/test_character_identity_pg.py:319:89: E501 line too long (92 > 88 characters)
  tests/test_orrery/test_character_identity_pg.py:340:89: E501 line too long (115 > 88 characters)
  ```

  Every branch finding is on origin/main at a shifted line. The branch has
  one fewer F811 because the deleted identity test is gone.

  mypy, branch, plain command (exit 1). mypy stops at the `test_orrery`
  duplicate-module error before it checks anything:

  ```
  $ git diff --name-only origin/main...HEAD -- '*.py' | xargs $PY -m mypy
  tests/proofs/proof_session_truth.py:12: error: Library stubs not installed for "requests"  [import-untyped]
  tests/proofs/proof_session_truth.py:12: note: Hint: "python3 -m pip install types-requests"
  tests/proofs/proof_session_truth.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
  tests/proofs/proof_session_truth.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
  tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
  tests/test_orrery/__init__.py: error: Source file found twice under different module names: "test_orrery" and "tests.test_orrery"
  Found 3 errors in 3 files (errors prevented further checking)
  ```

  mypy, origin/main, plain command (exit 1), same stop:

  ```
  $ cat files.txt | xargs $PY -m mypy
  tests/proofs/proof_session_truth.py:12: error: Library stubs not installed for "requests"  [import-untyped]
  tests/proofs/proof_session_truth.py:12: note: Hint: "python3 -m pip install types-requests"
  tests/proofs/proof_session_truth.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
  tests/proofs/proof_session_truth.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
  tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
  tests/test_orrery/test_character_identity_pg.py:5: error: Skipping analyzing "asyncpg": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  nexus/api/narrative.py:8: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  scripts/api_openai.py:66: error: Library stubs not installed for "keyboard"  [import-untyped]
  scripts/api_openai.py:66: note: Hint: "python3 -m pip install types-keyboard"
  nexus/agents/lore/lore.py:56: error: Cannot find implementation or library stub for module named "utils.turn_context"  [import-not-found]
  nexus/agents/lore/lore.py:57: error: Cannot find implementation or library stub for module named "utils.turn_cycle"  [import-not-found]
  nexus/agents/lore/lore.py:58: error: Cannot find implementation or library stub for module named "utils.token_budget"  [import-not-found]
  nexus/api/setup_endpoints.py:13: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  nexus/api/runtime_status.py:18: error: Library stubs not installed for "requests"  [import-untyped]
  nexus/api/wizard_chat.py:19: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  tests/test_orrery/__init__.py: error: Source file found twice under different module names: "test_orrery" and "tests.test_orrery"
  tests/test_orrery/__init__.py: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-file-paths-to-modules for more info
  tests/test_orrery/__init__.py: note: Common resolutions include: a) adding `__init__.py` somewhere, b) using `--explicit-package-bases` or adjusting MYPYPATH
  Found 12 errors in 10 files (errors prevented further checking)
  ```

  Because the plain command checks nothing, both trees were also checked
  with `--explicit-package-bases --follow-imports=silent`. This reports
  only errors in the listed files.

  mypy, branch (exit 1):

  ```
  $ git diff --name-only origin/main...HEAD -- '*.py' | xargs $PY -m mypy --explicit-package-bases --follow-imports=silent
  nexus/api/presence_audit.py:138: error: Argument 2 to "diff_presence" has incompatible type "set[int | None]"; expected "set[int]"  [arg-type]
  tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
  tests/proofs/proof_session_truth.py:12: error: Library stubs not installed for "requests"  [import-untyped]
  tests/proofs/proof_session_truth.py:12: note: Hint: "python3 -m pip install types-requests"
  tests/proofs/proof_session_truth.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
  tests/proofs/proof_session_truth.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
  Found 3 errors in 3 files (checked 13 source files)
  ```

  mypy, origin/main (exit 1):

  ```
  $ cat files.txt | xargs $PY -m mypy --explicit-package-bases --follow-imports=silent
  nexus/api/presence_audit.py:138: error: Argument 2 to "diff_presence" has incompatible type "set[int | None]"; expected "set[int]"  [arg-type]
  nexus/api/presence_audit.py:178: error: Argument 2 to "diff_presence" has incompatible type "set[int | None]"; expected "set[int]"  [arg-type]
  tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
  tests/test_orrery/test_character_identity_pg.py:5: error: Skipping analyzing "asyncpg": module is installed, but missing library stubs or py.typed marker  [import-untyped]
  tests/proofs/proof_session_truth.py:12: error: Library stubs not installed for "requests"  [import-untyped]
  tests/proofs/proof_session_truth.py:12: note: Hint: "python3 -m pip install types-requests"
  tests/proofs/proof_session_truth.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
  tests/proofs/proof_session_truth.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
  Found 5 errors in 4 files (checked 13 source files)
  ```

  All three branch errors are on origin/main. The `presence_audit.py:178`
  copy of the `diff_presence` arg-type error went away with the deleted
  `audit_chunk_presence_async`. The `asyncpg` stub error went away with the
  deleted identity test's import.

## Rerun After f97eba5e

The offline suite above finished before f97eba5e changed the stable-seed
reason string (`nexus/agents/orrery/retrograde_vocabulary.py`) and its pin.
These reruns are at ef81ef0f plus the review-fix commit (comment and doc
wording only), started 2026-09-30 00:18 UTC, with gateway variables unset.
Twelve zero-byte untracked files at the worktree root (tool-output debris,
never committed) were deleted first; with them present, the reachability
checker reported them as newly unreachable.

```
$ $PY -m pytest -q tests/test_orrery tests/test_turn_observation.py
1188 passed, 489 skipped, 7 warnings in 8.56s
```

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs tests/test_orrery/test_retrograde_vocabulary.py
28 passed, 5 warnings in 0.47s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rA tests/test_orrery/test_retrograde_vocabulary.py -k live_tag_registry
PASSED tests/test_orrery/test_retrograde_vocabulary.py::test_seed_eligible_vocabulary_can_include_live_tag_registry
1 passed, 27 deselected, 5 warnings in 0.34s
```

```
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 8.48s
```

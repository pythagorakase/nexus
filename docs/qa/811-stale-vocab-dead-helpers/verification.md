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
  Rerun alone: `13 passed in 1.25s`.
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
- Black clean on all changed Python files. flake8 and mypy report only
  findings that already exist on 3ca248df (E501 lines and the
  `roster_database` fixture import in the touched tests; the
  `presence_audit.py:138` `diff_presence` arg-type error, whose twin at the
  deleted async function's line 178 is gone).

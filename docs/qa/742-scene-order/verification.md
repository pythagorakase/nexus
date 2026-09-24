# Scene Order Verification

Baseline captured on `7b70ee63`; implementation commit `e4a0d454`.

Work order 742-B implements chronological scene rendering and the coordinator's
recalled-lane amendments. No prompt prose, configuration defaults, fingerprint
projection, schema, roster wording, or render caps changed.

## PR #932 Review Fixes

The third coordinator amendment is implemented in `7057b084`. After that fix,
`git fetch origin && git merge origin/main` reported `Already up to date.`;
the fetched main is `53ac8fa25c5b3925234d0f329666f904dd8ec50c`.

The shared selection in `nexus/agents/lore/utils/scene_order.py:19` resolves
identities across both sources before the ranked cap. Recent narrative wins
over recalled scenes, then historical context. The next distinct candidate
fills a duplicate's slot. Assembly freezes this selection before hydration
(`nexus/agents/lore/utils/turn_cycle.py:1008`), so budget trimming cannot
resurrect a discarded duplicate. Both seats use the same selector.

Only selected recalled entries are hydrated. Missing or NULL clocks clear any
stale timestamp and render the identity alone (`scene_order.py:90` and `:95`).
Malformed non-NULL clocks still fail visibly. PostgreSQL regression coverage
observes the actual query parameters: with a cap of one the query contains
only chunk 8, excluding the beyond-cap summary's NULL anchor 46; with a cap of
two both anchors are queried and both entries render undated. Other regressions
cover a summary present in both Pass 2 and deep retrieval, duplicate parents,
lane priority, cap refilling, and exact window counts after trimming a duplicate.

### Refreshed Frontier Proof

`review.json`, `review-payload.json`, and `review-{skald_writer,gaia}.txt` are the
current evidence. `before-*` and `after-*` remain the original baseline and
reviewed-head captures. The refreshed probe used disposable clone
`qa640_742_scene_3b3f6d3fcb3c`, TEST rendering, and no generation. Its stored
fingerprint remains
`a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7`.

Both seats have exactly these narrative identities:

```text
HISTORICAL CONTEXT: 34, 36, 28, 37, 27, 35, 26, 33, 21
RECALLED SCENES: 8, 9, 11, 12, 15, 17, retrograde_summary:21, retrograde_summary:27
RECENT NARRATIVE: 40, 41, 42, 43, 44, 45, 46, 47, 48, 49
```

All identities appear once; parent 49 appears only in RECENT NARRATIVE. The
recalled labels and clocks are unchanged from the original proof below and are
also recorded explicitly in `review.json`. The writer roster and user input
still immediately follow the recent scene.

| Block | Reviewed Writer | Fixed Writer | Reviewed Gaia | Fixed Gaia |
|---|---:|---:|---:|---:|
| historical context | 15171 | 9513 | 15171 | 9513 |
| recalled scenes | 6161 | 6161 | 6161 | 6161 |
| recent narrative | 9782 | 9782 | 9782 | 9782 |
| Total | 42942 | 37284 | 40334 | 34676 |

Every other block count is unchanged; all per-block counts are in `review.json`.
Each seat loses exactly 5658 tokens of duplicated historical entries (49, 48,
47, 43, 46, 42), independently counted in `review-duplicate-costs.json`. Thus the
net change from the original preimplementation prompt is -5512 tokens: the
accepted 146-token label cost minus these duplicate copies. This reduction is
the third amendment's required deduplication, not a render-limit change.

The probe asserts unchanged raw selected retrieval identities, prose, historical
rank order, and coverage identities/entity coverage/gaps. Coverage `kept_tokens`
is now 7719 (8252 before the original implementation; 8390 at the reviewed
head), reflecting the rendered entries exactly once. Source save_04 is read
only; `review-cleanup.json` confirms no remaining scene-proof databases and
read-only save_05 counts of zero chunks and zero characters.

The remaining sections document the original implementation and its archived
gates. The review validation commands and current results are recorded below.

## Review Validation

The final offline gate has zero failures. The PostgreSQL subset ran all 109
selected tests; its sole failure remains the explicitly exempt #885 slot-5
coverage test. No other failure is exempt. Black and both commit hooks passed.
No gateway, paid call, UI build, fleet/template migration, or save reset was used.

The initial offline run found 11 fixture failures (`review-offline-initial.txt`):
the minimal assembly fixtures lacked the required `RenderLimits` fields.
Those fixtures now read the actual render limits from `nexus.toml` through the
settings loader. The first fixture rerun (`review-fixtures-initial.txt`) also
exposed one stale assertion that the list itself must be reused. It now asserts
that individual chunk objects are retained; the existing byte-for-byte payload
assertion remains. The next fixture rerun passed 60 tests, and the complete
rerun passed 2714. These are fixture repairs in `9110efd6`, not production
fallbacks or new exemptions. Initial failed logs are preserved under the
`-initial` filenames; their commands were identical to the subsequent reruns.

Commands and verbatim final tails:

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_scene_order_render.py tests/test_lore/test_historical_render.py > docs/qa/742-scene-order/review-focused.txt 2>&1
```

```text
16 passed, 5 warnings in 3.29s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_turn_cycle.py tests/test_orrery/test_ambient.py tests/test_orrery/test_bleed.py > docs/qa/742-scene-order/review-fixtures.txt 2>&1
```

```text
60 passed, 5 warnings in 2.20s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > docs/qa/742-scene-order/review-offline.txt 2>&1
```

```text
2714 passed, 894 skipped, 9 warnings in 134.78s (0:02:14)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore -k 'render or format or window or coverage or warm or recent' > docs/qa/742-scene-order/review-postgres.txt 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
1 failed, 108 passed, 212 deselected, 9 warnings in 22.63s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check . > docs/qa/742-scene-order/review-black.txt 2>&1
```

```text
All done! ✨ 🍰 ✨
667 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-scene-order/probe.py --phase review > docs/qa/742-scene-order/review-probe.log 2>&1
```

```text
REVIEW_PROOF_PASSED: unique identities; parent only in recent; seat parity; fingerprint unchanged; coverage identities unchanged
```

Formatting commands run before the checks:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/lore/utils/scene_order.py nexus/agents/lore/utils/turn_cycle.py nexus/agents/lore/logon_utility.py tests/test_lore/test_scene_order_render.py
```

```text
All done! ✨ 🍰 ✨
2 files reformatted, 2 files left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black docs/qa/742-scene-order/probe.py
```

```text
All done! ✨ 🍰 ✨
1 file reformatted.
```

The probe transcript is archived as `review-probe.txt`. The import check
(`review-import.txt`) prints this worktree's `nexus/__init__.py`.
Read-only cleanup/source-state SQL behind `review-cleanup.json`:

```sql
-- Database: postgres
SELECT datname FROM pg_database
WHERE datname LIKE 'qa640_742_scene_%' OR datname LIKE 'qa640_scene_%'
ORDER BY datname;
-- Zero rows.

-- Database: save_05
SELECT (SELECT count(*) FROM narrative_chunks),
       (SELECT count(*) FROM characters);
-- 0, 0.
```

## Rendering and Accounting

Both seats now use the same narrative order: historical passages, recalled
scenes, recent scene. The recent scene is sorted by numeric chunk id, ending at
the parent; the writer's existing roster line and the user input follow it.
Pass-2 additions are marked only when added to the warm list, preserving
selection, deduplication, and memory identities. Retrograde summaries from
either source list enter the recalled lane. The historical cap selects
the ranked prefix after cross-source deduplication and before lane partitioning.

Recalled narrative labels carry their own story clocks. Summary labels explicitly
say `recorded at chunk` and use that anchor's clock; unanchored summaries remain
undated. Clock hydration reads the selected entries from `narrative_view` in one
query; an entry without a clock renders its id only. Every face uses `clock_face`.

The prompt-window kind is `recalled scenes`. Trimming preserves the existing
selection policy and subtracts from the actual lane; dropping its last entry
also subtracts its heading. Coverage identities and entity coverage stay the
same; `kept_tokens` includes the rendered labels.

## Frontier Proof

The baseline and after probes use disposable `qa640_742_scene_*` clones of
save_04, `LORE.process_turn` with generation disabled, and both real TEST seat
renderers. The source save is read only. No gateway or paid provider is used.
This is an assembly diagnostic: private correspondence is omitted when generation
is disabled, and Gaia includes finished-writer framing without a generated writer
response. These totals are local block estimates, not provider usage.

The stored frontier baseline restores without restamping. Its fingerprint is:

```text
a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7
```

The after probe asserts equality with the current fingerprint function and the
before artifact, equality of selected identities and narrative text, and equality
of historical rank order. Incremental additions originate in a set, so their
pre-render insertion order may differ across Python processes; the new renderer
sorts deterministically. The probe writes before/after coverage rows on the clone
using the same pending retrieval and compares all captured fields except the
accurately changed token count. The before coverage replay counts the archived
old rendered entry format.

Before RECENT NARRATIVE ids (fresh baseline capture):

```text
49, 48, 47, 46, 45, 44, 43, 42, 41, 40,
8, retrograde_summary:27, 9, 11, retrograde_summary:21, 12, 15, 17
```

After RECENT NARRATIVE ids in both seats:

```text
40, 41, 42, 43, 44, 45, 46, 47, 48, 49
```

Recalled entries in both seats:

```text
chunk 8 · 17 Oct 2189 · 19:27
chunk 9 · 17 Oct 2189 · 19:29
chunk 11 · 17 Oct 2189 · 19:36
chunk 12 · 17 Oct 2189 · 19:40
chunk 15 · 17 Oct 2189 · 19:53
chunk 17 · 17 Oct 2189 · 19:58
Retrograde summary 21 · recorded at chunk 46 · 17 Oct 2189 · 22:23
Retrograde summary 27 · recorded at chunk 49 · 17 Oct 2189 · 22:37
```

The exact payloads and writer/Gaia text are in `before-*` and `after-*` artifacts;
`before.json` and `after.json` contain the per-block counts. The after artifact also
records lane identities and the two coverage rows.

| Block | Writer Before | Writer After | Gaia Before | Gaia After |
|---|---:|---:|---:|---:|
| system | 4580 | 4580 | 1900 | 1900 |
| intertitle | 50 | 50 | 50 | 50 |
| scene conditions | 17 | 17 | 17 | 17 |
| recent narrative | 15797 | 9782 | 15797 | 9782 |
| scene roster | 22 | 22 | 0 | 0 |
| user input | 15 | 15 | 15 | 15 |
| entity dossier | 2182 | 2182 | 2182 | 2182 |
| historical context | 15171 | 15171 | 15171 | 15171 |
| recalled scenes | 0 | 6161 | 0 | 6161 |
| world knowledge | 252 | 252 | 252 | 252 |
| orrery tag library | 3742 | 3742 | 3742 | 3742 |
| recent orrery rulings | 210 | 210 | 210 | 210 |
| orrery imminent activity | 264 | 264 | 264 | 264 |
| orrery scene pressure | 316 | 316 | 316 | 316 |
| orrery joint beats | 148 | 148 | 148 | 148 |
| instructions | 30 | 30 | 30 | 30 |
| finished writer framing | 0 | 0 | 94 | 94 |
| Total | 42796 | 42942 | 40188 | 40334 |

Both seat totals rise by **146 TEST tokens**: 138 tokens of identity/clock labels
and eight for the recalled heading. Replayed coverage `kept_tokens` rises from
8252 to 8390; its identities, raw-result count, entity coverage, and gaps are identical.

## Validation

All commands run from this worktree with `PYTHONPATH=$PWD` and the shared
`/Users/pythagor/nexus/.venv/bin/python`. The import check printed:

```text
/Users/pythagor/nexus/.claude/worktrees/742-scene-order/nexus/__init__.py
```

The PostgreSQL subset ran rather than skipping. Its sole failure is the
coordinator's #885 exemption:
`tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection`.
That test hardwires `LIVE_SLOT = 5` at `tests/test_lore/test_retrieval_coverage_live.py:17`
and fails while inserting a character, before rendering, with:

```text
psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp
```

Read-only SQL (`slot5.txt`) confirms zero chunks and zero characters in save_05.
No exemption was applied to any other failure.

The initial offline run found an obsolete mocked retrieval test, the new-module
reachability registration, and two prompt-lint failures caused by #931 removing
blank-line whitespace in a docstring while its exact allowlist retained it. The
trimming regression now uses real memory-state registration and TEST rendering
without mocked retrieval. The production path was added to the reachability
ratchet. Only the lint allowlist's whitespace changed; the actual docstring and
all prompt prose remain untouched. All five initially failing tests passed on
focused rerun (`gate-fixes.txt`).

The first after-probe compared set-derived insertion order across processes and
failed its diagnostic assertion; selected ids and prose were identical. The probe
now compares those by identity, preserves the rank-order assertion for historical
passages, and records the renderer's deterministic lane order. The final probe
also counts repeated appearances in historical context when replaying the old
coverage token count.

No UI/build work, gateway, CLI continuation, or paid inference was needed for this
assembly slice. Disposable fixture clones were removed; `cleanup.txt` records
zero remaining scene-proof databases. Existing repository fixtures own their
PostgreSQL test targets. No fleet/template migration or save reset was performed.

## Commands and Verbatim Tails

The before command used the preimplementation probe. The final after probe exited 0.
All test commands below completed; the PostgreSQL subset exited 1 only for the
explicitly exempt test named above. Offline skips are the repository default
PostgreSQL/live-provider gates, not PostgreSQL proof.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > docs/qa/742-scene-order/offline.txt 2>&1
```

```text
2712 passed, 893 skipped, 9 warnings in 131.24s (0:02:11)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore -k 'render or format or window or coverage or warm or recent' > docs/qa/742-scene-order/postgres.txt 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
1 failed, 105 passed, 212 deselected, 9 warnings in 32.73s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check . > docs/qa/742-scene-order/black.txt 2>&1
```

```text
All done! ✨ 🍰 ✨
667 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_typed_memory_identity.py tests/test_lore/test_seat_window.py tests/test_lore/test_historical_render.py > docs/qa/742-scene-order/focused.txt 2>&1
```

```text
26 passed, 5 warnings in 1.24s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_scene_order_render.py > docs/qa/742-scene-order/scene-tests.txt 2>&1
```

```text
4 passed, 5 warnings in 0.97s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_scene_order_render.py > docs/qa/742-scene-order/scene-postgres.txt 2>&1
```

```text
5 passed, 5 warnings in 2.09s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_turn_cycle.py::test_trimmed_pass2_chunk_is_unregistered_refunded_and_retrievable tests/test_prompt_lint.py::test_python_has_no_embedded_prompt_prose tests/test_prompt_lint.py::test_allowlist_is_exact_and_has_no_stale_entries tests/test_reachability.py::test_repository_reachability_ratchet tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app > docs/qa/742-scene-order/gate-fixes.txt 2>&1
```

```text
5 passed, 5 warnings in 12.17s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-scene-order/probe.py > docs/qa/742-scene-order/before-probe.log 2>&1
```

```text
        "orrery joint beats": 148,
        "instructions": 30,
        "finished writer framing": 94
      },
      "total": 40188
    }
  }
}
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-scene-order/probe.py --phase after > docs/qa/742-scene-order/after-probe.log 2>&1
```

```text
        "covering_chunk_ids": [
          47
        ]
      }
    ],
    "gap_entities": []
  }
}
```

## Coordinator Questions

The separate bot comment [discussion_r4098645540](https://github.com/pythagorakase/nexus/pull/932#discussion_r4098645540)
asks for a warm-window query bounded by an older explicit parent, rather than
filtering the globally newest window. Does the coordinator want that selection
change in a separate order? It is outside this amendment's two specified fixes;
this run proves the save_04 frontier, not historical-parent continuation.

The existing #885 slot-5 fixture failure remains exempt. The branch is for
coordinator review; this run does not merge or wait for review bots.

Codex, running GPT-6 Astra.

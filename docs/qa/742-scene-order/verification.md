# Scene Order Verification

Baseline captured on `7b70ee63`; implementation commit `e4a0d454`.

Work order 742-B implements chronological scene rendering and the coordinator's
recalled-lane amendments. No prompt prose, configuration defaults, fingerprint
projection, schema, roster wording, or render caps changed.

## Rendering and Accounting

Both seats now use the same narrative order: historical passages, recalled
scenes, recent scene. The recent scene is sorted by numeric chunk id, ending at
the parent; the writer's existing roster line and the user input follow it.
Pass-2 additions are marked only when added to the warm list, preserving
selection, deduplication, and memory identities. Retrograde summaries from
either source list enter the recalled lane. The historical cap still selects
the ranked prefix before lane partitioning.

Recalled narrative labels carry their own story clocks. Summary labels explicitly
say `recorded at chunk` and use that anchor's clock; unanchored summaries remain
undated. Clock hydration reads `narrative_view` in one query, fails loudly on an
anchored memory without a clock, and formats every face with `clock_face`.

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

None. The only deferred item is the already exempt #885 slot-5 fixture failure.
The branch is for coordinator review; this run does not merge or wait for review bots.

Codex, running GPT-6 Astra.

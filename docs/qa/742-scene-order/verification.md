# Scene Order Stop Report

Work order 742-B stopped before production edits. Base: `53ac8fa2` on
`claude/742-scene-order`. The frozen order requires every recalled entry,
including Retrograde summaries, to have a chunk id and story clock face. The
actual frontier contains summaries without an event timestamp. Choosing a
recording-time clock instead would introduce temporal semantics that the
coordinator has not specified. No timestamp was invented and no fallback added.

## Blocking Evidence

The unmodified real LORE path restored save_04 frontier 49 on disposable clone
`qa640_742_scene_2142d8d55237`. Input: `Ask Kessa Brin what she remembers.`
Pass-2 added narrative chunks 8, 9, 11, 12, 15, and 17, plus
`retrograde_summary:27` and `retrograde_summary:21`.

`nexus/agents/memnon/utils/db_access.py:77` constructs summary retrieval rows
with a typed summary identity, `recorded_at_chunk_id`, categorical `chronology`,
and wall-clock `created_at`. It supplies neither a narrative `chunk_id` nor a
story timestamp. `nexus/memory/retrieval_coverage.py:64` explicitly distinguishes
recording anchors from narrative identities. The live source confirms the data
gap; it is not merely a missing field in the retrieval projection:

```sql
BEGIN READ ONLY;
SELECT rs.id, rs.recorded_at_chunk_id, rs.chronology,
       we.world_time AS event_time, nv.world_time AS recorded_at_time
FROM retrograde_summaries rs
JOIN world_events we ON we.id = rs.world_event_id
LEFT JOIN narrative_view nv ON nv.id = rs.recorded_at_chunk_id
WHERE rs.id IN (21, 27)
ORDER BY rs.id;
COMMIT;
```

```text
 id | recorded_at_chunk_id | chronology  | event_time |    recorded_at_time
----+----------------------+-------------+------------+------------------------
 21 |                   46 | recent_past |            | 2189-10-17 18:23:00-04
 27 |                   49 | recent_past |            | 2189-10-17 18:37:00-04
```

Across all 27 summary rows, zero joined world events have `world_time`; all 27
have recording anchors. Exact psql output is in [summary-clocks.txt](summary-clocks.txt).
`created_at` is a 2026 storage timestamp, not the 2189 story clock.
`clock_face()` formats an existing aware timestamp; it does not resolve a
relative chronology such as `recent_past` (`nexus/util/clock_face.py:21`).

There is also a proof-condition discrepancy to resolve: the six narrative
entries currently render without id/time labels. Adding the required labels in
the existing bracket style costs 17 TEST tokens per entry, or 102 tokens, before
the eight-token recalled heading or any summary labels. See
[label-costs.json](label-costs.json). This is a label-only calculation against
actual retrieved text, not a claim that an after-render was implemented. The
requested total change of only a few heading tokens cannot describe this label
format. Coverage `kept_tokens` currently counts rendered chunk contributions
(`nexus/memory/manager.py:1026`), so it would also change with added labels even
if retained identities and coverage content remain equal.

## Completed Baseline Probe

The probe cloned save_04 through the repository's `disposable_slot_database`,
restored its existing baseline without restamping, assembled context through
`LORE.process_turn` with generation disabled, and measured both seats through
the real `LogonUtility` TEST route. No paid generation or counting request ran.
Local embedding and reranking models did run.

The stored fingerprint restored successfully:

```text
FINGERPRINT_RESTORE_PASSED a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7
```

No configuration or fingerprint projection was changed. This proves the
starting baseline only; there is no implemented after-state.

The old RECENT NARRATIVE order was:

```text
49, 48, 47, 46, 45, 44, 43, 42, 41, 40,
8, 9, 11, 12, 15, 17, retrograde_summary:27, retrograde_summary:21
```

The following are local block estimates from the unchanged renderer. This is
an assembly diagnostic: generation-disabled LORE omits private storyteller
correspondence, and Gaia has only finished-writer framing, not a generated
writer response. These are not full production request totals or provider
usage. Exact payload, rendered seat text, and counts are preserved in the
adjacent `before-*` files and `before.json`.

| Block | Writer | Gaia |
|---|---:|---:|
| system | 4580 | 1900 |
| intertitle | 50 | 50 |
| scene conditions | 17 | 17 |
| recent narrative | 15797 | 15797 |
| scene roster | 22 | 0 |
| user input | 15 | 15 |
| entity dossier | 2182 | 2182 |
| historical context | 15171 | 15171 |
| world knowledge | 252 | 252 |
| orrery tag library | 3742 | 3742 |
| recent orrery rulings | 210 | 210 |
| orrery imminent activity | 264 | 264 |
| orrery scene pressure | 316 | 316 |
| orrery joint beats | 148 | 148 |
| instructions | 30 | 30 |
| finished writer framing | 0 | 94 |
| Total | 42796 | 40188 |

## Commands and Actual Output

All commands ran from this worktree. No gateway was started. No save or template
was written. The disposable clone was removed by the fixture; [cleanup.txt](cleanup.txt)
records the zero-row database check.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/742-scene-order/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-scene-order/probe.py > docs/qa/742-scene-order/before-probe.log 2>&1
```

Exit 0. Verbatim last eight lines:

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
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black docs/qa/742-scene-order/probe.py
```

```text
reformatted docs/qa/742-scene-order/probe.py

All done! ✨ 🍰 ✨
1 file reformatted.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check docs/qa/742-scene-order/probe.py > docs/qa/742-scene-order/black.txt 2>&1
```

```text
All done! ✨ 🍰 ✨
1 file would be left unchanged.
```

No pytest suite, gateway/CLI continuation, build, or after-render was run. The
requested offline and PostgreSQL proof gates remain unrun, not passed. There
was no authentication hazard or runtime exception causing this stop. The stop
is a data/semantics conflict with the frozen requirements.

## Coordinator Questions

1. Should Retrograde entries keep their typed summary identity and explicitly
   display the **recorded-at chunk and its clock**, while retaining their
   categorical chronology? Alternatively, define an undated form or supply an
   authoritative event-time source. A recording clock must not silently become
   an event clock.
2. May the total increase by the measured id/time label costs as well as the
   heading? Does unchanged coverage mean identical retained ids/entity coverage
   with accurately updated rendered `kept_tokens`?

All runtime changes, regressions, §06.3 changes, and after-state proof are
pending. No PR was opened or merged because the implementation gates were not
reached.

Codex, running GPT-6 Astra.

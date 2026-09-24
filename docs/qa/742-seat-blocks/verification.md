# Seat-Specific Block Verification

Work order 742-C; baseline `df88c7c8` on `claude/742-seat-blocks`.

## Result

The writer now ends with its roster, user input, and the exact registered writer
closer. It receives neither the Orrery tag library nor the three card instruction
paragraphs nor the retired INSTRUCTIONS block. Gaia retains the library and card
instructions and replaces INSTRUCTIONS with its exact registered closer.

`nexus/agents/lore/seat_blocks.py` declares typed, immutable ordered manifests.
The shared renderer applies them and remaps chunk-source indices, preserving
prompt-window accounting and removable-block ownership. Generation (sync and
async) and request measurement explicitly select writer versus single-pass.
Unknown block IDs fail loudly.

The three instruction paragraphs were already separate registry documents after
#930 (`prompts/turn_blocks/{imminent_activity,scene_pressure,joint_beats}.md`).
Their bytes and the card headers are unchanged; only seat inclusion changes.
The two new closer documents have exactly the coordinator's supplied text.
No runtime configuration, schema, migration, fingerprint projection, or rendering
cap changed. The reachability inventory registers the new production module.

## Preserved Behavior and Scope Decisions

- Bootstrap and single-pass share the renderer and retain their previous union,
  order, tag library, card instructions, and INSTRUCTIONS block.
- Gaia's finished writer narrative, choices, scene, presence, operations, and
  private letter remain appended where they rendered previously. Its new closer
  replaces INSTRUCTIONS in the context, before those finished-writer blocks.
- Existing optional private correspondence, ambient seeds, ambient peripherals,
  and the author's note remain available. The latter three precede the roster
  and input; correspondence keeps its existing early position. Gaia still omits
  writer-only ambient seeds through the existing call-site flag. This preserves
  existing features not explicitly addressed in the frozen list; the coordinator
  was asked about this interpretation during implementation.

## Frontier Proof

`probe.py` restores save_04's stamped frontier (parent 49), processes the same
input through LORE with LOGON disabled, and measures both actual TEST seat
requests on disposable clones. No inference or gateway is required. Gaia's
measurement includes the existing empty finished-writer framing and reserves the
writer response allowance; it is not a generated passage.

- Before clone: `qa640_742_seats_63caa906d9bb`.
- After clone: `qa640_742_seats_35b9d4eebf9a`.
- Both restored and recomputed fingerprints match:
  `a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7`.
- Each probe asserts that its clone no longer exists after cleanup.
- `before-{skald_writer,gaia}.txt` and `after-{skald_writer,gaia}.txt` contain the
  rendered prompts; `before.json` and `after.json` contain every block count.

Counts use the configured TEST tokenizer and include the seat's system cost.

| Block | Writer Before | Writer After | Gaia Before | Gaia After |
|---|---:|---:|---:|---:|
| System | 4580 | 4580 | 1900 | 1900 |
| Intertitle | 50 | 50 | 50 | 50 |
| Scene conditions | 17 | 17 | 17 | 17 |
| Entity dossier | 2182 | 2182 | 2182 | 2182 |
| Historical context | 9513 | 9513 | 9513 | 9513 |
| Recalled scenes | 6161 | 6161 | 6161 | 6161 |
| Recent narrative | 9782 | 9782 | 9782 | 9782 |
| World knowledge | 252 | 252 | 252 | 252 |
| Orrery tag library | 3742 | 0 | 3742 | 3742 |
| Recent Orrery rulings | 210 | 210 | 210 | 210 |
| Orrery imminent activity | 264 | 176 | 264 | 264 |
| Orrery scene pressure | 316 | 263 | 316 | 316 |
| Orrery joint beats | 148 | 77 | 148 | 148 |
| Scene roster | 22 | 22 | 0 | 0 |
| User input | 15 | 15 | 15 | 15 |
| Instructions | 30 | 0 | 30 | 0 |
| Seat closer | 0 | 13 | 0 | 14 |
| Finished writer framing | 0 | 0 | 94 | 94 |
| **Total** | **37284** | **33313** | **34676** | **34660** |

Writer saving: **3971 tokens** (3742 library + 212 card instructions + 17 net
closer reduction), approximately **10.65%**. Gaia saves 16 tokens from its closer.
All other per-block counts are unchanged.

The writer artifact ends exactly with:

```text
PRESENT: Mara Vey (player), Kessa Brin · SETTING: Wickglass Dispatch House

=== USER INPUT ===
Ask Kessa Brin what she remembers.
Skald writes the next passage from the user input above.
```

## Validation

All commands ran from this worktree with the shared interpreter. The initial
import check returned:

```text
/Users/pythagor/nexus/.claude/worktrees/742-seat-blocks/nexus/__init__.py
```

New tests use the real renderer, TEST request accounting, and a real save_04
clone for tag-library inclusion. No new mock tests were introduced. Existing
formatting, scene-order, and transport assertions now reflect the intentional
seat differences. The initial PostgreSQL run exposed the outdated shared-prefix
assertion in both Anthropic prompted transport tests; `postgres-initial.txt`
preserves that failure. The assertion now checks the shared context plus each
seat's distinct closer. The first offline run also reported the required
reachability registration for the new module; that inventory is now updated.
`offline-initial.txt` preserves all ten initial failures (eight instances of the
shared-prefix assertion plus two reachability checks).

No paid calls, live gateway, UI changes, fleet/template migrations, save resets,
or writes to the source saves were performed. CLI validation is an entry-point
help smoke check only; the frozen order's actual rendering proof uses TEST on
clones rather than narrative generation through a live gateway.

The final offline gate has zero failures; its 900 skips are the repository's
offline exclusions. All 128 selected PostgreSQL tests ran without skips or
failures. No #885 exemption was needed. Both implementation commit hooks passed.

### Full Offline Gate

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > docs/qa/742-seat-blocks/offline.txt 2>&1
```

```text
2719 passed, 900 skipped, 9 warnings in 129.17s (0:02:09)
```

### PostgreSQL Gate

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore tests/test_skald_wire.py -k 'prompt or format or render or block or seat' > docs/qa/742-seat-blocks/postgres.txt 2>&1
```

```text
128 passed, 296 deselected, 5 warnings in 33.04s
```

### Prompt Lint

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py > docs/qa/742-seat-blocks/prompt-lint.txt 2>&1
```

```text
22 passed, 5 warnings in 15.91s
```

### Black

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check . > docs/qa/742-seat-blocks/black.txt 2>&1
```

```text
All done! ✨ 🍰 ✨
673 files would be left unchanged.
```

### Initial Focused Tests

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_seat_blocks.py tests/test_lore/test_logon_prompt_formatting.py tests/test_lore/test_scene_order_render.py tests/test_prompt_lint.py > docs/qa/742-seat-blocks/focused.txt 2>&1
```

```text
74 passed, 3 skipped, 5 warnings in 17.02s
```

### Transport and Reachability Repairs

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_lore/test_two_pass_pipeline.py > docs/qa/742-seat-blocks/gate-fixes.txt 2>&1
```

```text
70 passed, 5 warnings in 10.08s
```

### Before Capture

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-seat-blocks/probe.py --phase before > docs/qa/742-seat-blocks/before-probe.txt 2>&1
```

```text
FRONTIER_PROOF_PASSED: TEST renders; fingerprint verified; clone removed
```

### After Capture

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-seat-blocks/probe.py --phase after > docs/qa/742-seat-blocks/after-probe.txt 2>&1
```

```text
FRONTIER_PROOF_PASSED: TEST renders; fingerprint verified; clone removed
```

### Archived Prose Comparison

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python docs/qa/742-seat-blocks/check_artifacts.py > docs/qa/742-seat-blocks/artifact-check.txt 2>&1
```

```text
ARTIFACT_PROOF_PASSED: writer suffix exact; common prose and card text unchanged; Gaia library/instructions retained; fingerprint unchanged
```

### CLI Entry-Point Smoke Check

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'from nexus.cli import main; main()' --help > docs/qa/742-seat-blocks/cli-help.txt 2>&1
```

```text
  nexus place-manifest --slot 2  Build place tag manifest
  nexus place-apply --slot 2  Dry-run ready place manifest operations
  nexus backfill-review-packet --slot 2 --faction-manifest faction.json ...
        
```

### Initial Failed Runs

The same offline and PostgreSQL commands ran first with the same output paths;
those completed logs were renamed to `offline-initial.txt` and
`postgres-initial.txt` before the corrected reruns. Their verbatim summary tails:

```text
10 failed, 2709 passed, 900 skipped, 9 warnings in 161.79s (0:02:41)
2 failed, 126 passed, 296 deselected, 5 warnings in 47.38s
```

## Evidence Pointers

- Ordered manifests and legacy union: `nexus/agents/lore/seat_blocks.py:34`.
- Source-index remapping: `nexus/agents/lore/seat_blocks.py:86`.
- Explicit generation seat routing: `nexus/agents/lore/logon_utility.py:879`.
- Registry card paragraphs gated to Gaia and legacy seats:
  `nexus/agents/lore/logon_utility.py:2827`.
- Closer selection and manifest application:
  `nexus/agents/lore/logon_utility.py:2920`.
- Finished output stays in its existing appended position:
  `nexus/agents/lore/logon_utility.py:1357`.
- Exact closer text: `prompts/storyteller_writer_closer.md:1` and
  `prompts/storyteller_gaia_closer.md:1`.
- Live frontier, stored-fingerprint, and cleanup SQL: `probe.py` queries
  `SELECT max(id) FROM narrative_chunks` in the clone, restores that parent's
  baseline, and queries `pg_database` for the exact clone name after teardown.
- `check_artifacts.py` compares all common rendered prose, roster, and card text
  against the before artifacts, as well as exact writer suffix and fingerprint.

## Coordinator Questions

Confirm that the unlisted optional blocks should remain available before user
input, as implemented. No other design or implementation work is deferred.
Gaia's closer replaces INSTRUCTIONS before the unchanged finished-writer suffix,
following the order's instruction to leave that suffix where it renders today.

Codex — GPT-6 (Astra).

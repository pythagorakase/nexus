# Unified chunk references: resumed verification

Implementation: `bc31dbf4`, based on current main `afd034f3`. This is focused
validation, not the combined PostgreSQL merge gate. No owner database was
written. Migration 148 must land after story identity 146 and Natural Earth 147.

## Changes and independent review

Migration 148 backfills the unified table from the three authoritative junctions,
validates every column with EXCEPT ALL, and mirrors subsequent writes with
triggers. Subtype deletion forgets references, subtype renumbering preserves
them, and the wizard reset clears the unified table. The parity tool retains
its view default and adds an explicit unified-table target. An independent
Codex review found no blocking source defect at bc31dbf4; runtime writers do
not truncate the source junctions or mutate subtype entity identities.

The first resumed focused run reported 278 passed, 6 skipped, 4 failed. One new
reset fixture used a protagonist base different from the wizard's base; its
helper now accepts the intended base explicitly. Three existing need-clock
transition tests cloned a template at migration 145 without running pending
migrations; the fixture now runs the normal migration runner. These were test
setup defects, not suppressed assertions.

## Focused proof

Commands run from this worktree, using `/Users/pythagor/nexus/.venv/bin/python`,
`PYTHONPATH=$PWD`, nice 15, and with NEXUS_GATEWAY_PORT, NEXUS_API_URL,
NEXUS_SLOT and NEXUS_RUN_LIVE_LLM unset. PostgreSQL commands enable
`NEXUS_RUN_POSTGRES=1` and `-p tests.dbname_audit`.

- `pytest -q -p tests.dbname_audit tests/test_chunk_entity_references_pg.py
  tests/test_orrery/test_need_clock_anchor_pg.py`: 26 passed, 4 skipped in 20.20s.
  The four corpus cases are opt-in and were then run separately.
- With `NEXUS_RUN_CORPUS=1`, `pytest -q -p tests.dbname_audit
  tests/test_chunk_entity_references_pg.py -k fleet`: 4 passed, 8 deselected
  in 35.38s. Each populated save was dumped read-only into a disposable target;
  exact unified/junction parity held on all four.
- Document freshness and reachability: 96 passed in 14.51s.
- Black passed the four changed Python files. Flake8 has only the inherited
  need-clock line-length diagnostic. Mypy has four inherited need-clock
  optional WizardCache diagnostics, confirmed against origin/main; the other
  three changed Python files are clean. Raw current/baseline logs are adjacent.
- Migration comment and exception disposition checks passed.

Every PostgreSQL run above reported `secret-store guard: active; nexus-api:
 denied` and `dbname audit: owner targets: none`. See r2.log and corpus.log.

## Mutation controls

Each control edited only migration 148 in this worktree, ran one disposable
PostgreSQL test, required exit 1 and the intended failure, and restored the
original in finally. The committed SQL contains none of the plants.

1. Remove the place backfill branch: migration refused with “Migration 148:
   place rows ... differ from their junction: expected 3 rows, found 0”.
2. Remove the faction forget trigger: faction subtype deletion failed its
   assertion that unified references were removed.
3. Raise on the transient character lookup miss during subtype renumbering:
   renumbering failed with the planted exception.

The first attempt at control 2 removed only part of a SQL COMMENT because it
contained an internal semicolon, producing an irrelevant parse failure. The
harness was corrected and controls 2/3 rerun; only the corrected logs count.
The preserved harness contains that corrected removal and runs controls 2/3;
control 1 was run in the earlier pass and its successful failure log is kept.

## Fleet before landing and remaining work

A separate read-only inventory found template and saves 1–5 at migration 145,
with none of the new 146–148 tables present. Character/place/faction reference
counts: save 1 and 2 each 5800/1996/632; save 3 254/42/2; save 4 307/49/3; template
and save 5 zero. Full combined gate, PR review, migration sequencing and any
explicitly authorized fleet application remain coordinator work. No gateway
or owner service was started.

Codex — GPT-6

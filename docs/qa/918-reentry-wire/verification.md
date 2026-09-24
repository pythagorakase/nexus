# Re-Entry Wire Verification

Implemented work order #918 with the coordinator's fixture and tag-scope amendments.
The earlier exact-replay stop is resolved by those amendments. These are minimal
synthetic fixtures, not recovered provider response bodies.

## Baseline Oracles

The initial branch contained `cc1e39fc` (the earlier stop report) over
`03b29882`; production code was unchanged from that main baseline. Before editing
production, the three JSON fixtures reproduced the recorded messages through the
real Pydantic parser, registry validator, and staging boundary on disposable
`qa640_acceptance_*` databases. The baseline oracle test passed all three expected
failures. `baseline-errors.txt` retains their printed messages.

- `fixtures/place.json`: `Unresolved place state update name 'Loading Arcade'`
  from staging, matching `../909-long-absence-probe/live/3A-failed-session.json:8`.
- `fixtures/presence.json`: `Value error, scene_reset cannot be combined with enter or exit`
  from writer parsing, matching the invariant message in
  `../909-long-absence-probe/live/3A-retry-failed-session.json:8`. Pydantic's
  payload preview differs because this fixture is intentionally minimal.
- `fixtures/tag.json`: the full field-qualified `forewarned` duration-override
  error matched `../909-long-absence-probe/live/3A-final-failed-session.json:8`.
  The actor had an active `forewarned` row in the fixture database.

The baseline harness used the same command as the final fixture proof below;
its assertions initially expected these failures, then changed to the ruled
behavior. Its verbatim tail was:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3 passed, 7 warnings in 2.23s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## Resulting Behavior and Evidence

| Case | Result | Evidence |
| --- | --- | --- |
| Unknown Loading Arcade | Gaia validation raises an error naming the place and `new_entities` before staging is invoked; both the place catalog and incubator remain empty for this fixture | `tests/test_api/test_reentry_wire_pg.py:106`; `nexus/agents/logon/orrery_tag_validation.py:1266` |
| Known place, optional alias, same-turn declaration | All stage; the optional alias is canonicalized and staging also resolves it independently | `tests/test_api/test_reentry_wire_pg.py:132`; `nexus/presence/roster.py:444` |
| Reset plus crossings | Enter is folded into the reset, exit is discarded, and canonical-name/alias duplicates become one character by the existing ID-first roster rules | `tests/test_api/test_reentry_wire_pg.py:189`; `nexus/agents/logon/skald_wire.py:151` |
| Active extend-expiry | Dropped from ordinary updates and actor/target replacement additions; staging and acceptance preserve the original tag row and expiry | `tests/test_api/test_reentry_wire_pg.py:234`; `nexus/agents/logon/orrery_tag_validation.py:1192` |
| Inactive extend-expiry | Retained in all three paths and actually applied at acceptance, attributed to the accepted chunk | Same parameterized PostgreSQL proof |
| Contextual vocabulary | Active scene tags carry a direct hint; proposal-only entries carry conditional guidance covering both update and replacement additions | `nexus/agents/orrery/tag_library.py:493`; PostgreSQL vocabulary assertions |
| Attempt accounting | Session, moved/dropped names, tag and path are logged; append-only ledger revisions retain notes, and reads return one latest row per seat/attempt | `nexus/telemetry/usage.py:52`; `nexus/telemetry/prompt_window.py:172` |
| Rejected attempt and CLI | Real TEST provider guard keeps a repair note even when letter validation subsequently rejects the attempt; a second attempt is separate; real `nexus usage --run 918-ledger --json` entrypoint returns both notes | `tests/test_reentry_wire_ledger.py:17` |

`repair-records.json` contains actual logged session IDs and repair notes from the
fixture run. The test also reads each note back from the file ledger. A final
`pg_database` lookup for the 12 database names recorded by that run returned no
remaining databases.

Read-only SQL against `save_04` established that it currently has no
`place_aliases` table and that `forewarned` has
`reapplication_policy='extend_expiry'`, `clearance_kind='semantic'`, and no default
duration:

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('places', 'place_aliases')
ORDER BY table_name, ordinal_position;

SELECT tag, reapplication_policy, clearance_kind, default_duration
FROM tags WHERE tag = 'forewarned';
```

Alias-table coverage creates that optional relation only inside a disposable
fixture database, with comments on its table and columns. There is no production
migration. Existing row locks are retained during place identity resolution.

## Commands and Verbatim Tails

All commands ran from `/Users/pythagor/nexus/.claude/worktrees/918-reentry-wire`.
`PY=/Users/pythagor/nexus/.venv/bin/python` below abbreviates the exact interpreter
used for every test. No Poetry install, Node build, gateway, or provider generation
call was used. The TEST provider's real guard/tokenizer/validator was exercised
without issuing a completion request; the CLI proof invokes its real entrypoint.

Import provenance:

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/918-reentry-wire/nexus/__init__.py
```

Initial staging baseline:

```sh
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_acceptance_staging_pg.py -x
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
18 passed, 7 warnings in 22.99s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Final fixture proof, including actual acceptance for active/inactive tags:

```sh
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s tests/test_api/test_reentry_wire_pg.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 7 warnings in 15.82s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Existing extend-expiry regressions plus the new fixture proofs:

```sh
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_reentry_wire_pg.py tests/test_orrery_tag_validation_pg.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
41 passed, 7 warnings in 17.49s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Ledger and CLI proof:

```sh
$PY -m pytest -q tests/test_reentry_wire_ledger.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 0.77s
```

Required offline gate:

```sh
$PY -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2655 passed, 831 skipped, 9 warnings in 93.39s (0:01:33)
```

Required PostgreSQL gate:

```sh
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_skald_wire.py tests/test_api -k "wire or presence or staging or tag or place"
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner
1 failed, 138 passed, 2 skipped, 341 deselected, 9 warnings in 32.61s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The sole PostgreSQL failure is the work order's explicit #885 exemption,
`tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner`.
It hardwires the empty owner slot 5. The two skipped cases are the empty-slot
presence-baseline read and the opt-in paid live writer test. The disposable
PostgreSQL fixture proofs ran; they were not skipped. Offline PostgreSQL/live
skips are expected for the separately requested offline gate.

Black formatted all 14 changed Python files; the final `--check` reported
`14 files would be left unchanged`. Both pre-commit hooks
(`regenerate-orrery-catalog` and `validate-config`) ran successfully. No
`nexus.toml`, production schema, or prompt file changed.

## Development Corrections

The initial fixture setup lacked tag `source_kind`, then used an invalid source
kind; it was corrected to `llm_generated` before the baseline oracle passed.
The initial presence proof lacked a required baseline; the acceptance extension
initially nested a psycopg transaction context. Both were fixture errors and were
corrected. The first offline gate exposed existing fake-provider/cursor assumptions
and the new-module reachability ratchet. The resolver was placed in the existing
roster module, optional delegates remain supported, existing test contracts were
updated, and the old fake place-tag retry case was replaced by a real PostgreSQL
case. The ledger test explicitly clears inherited `NEXUS_SLOT` for its slotless
TEST route. These development failures are not represented as passing gates.

## Coordinator Follow-Up

No implementation blocker remains. Prompt edits remain the coordinator's pen.
Proposed exact Gaia sentences:

> Resolve place state updates against existing canonical names or aliases; declare a new place in `new_entities` in the same turn before updating it.

> When an `extend_expiry` tag is already active on an entity, omit it from both `updates.*.tags_add` and replacement-state entity tag additions, because this wire cannot express `duration_override`.

The current writer reset guidance remains valid; the repair is defensive. No
fleet/template migration was applied, and no gateway was started. Lane 8016
remained unused. No PR merge or review-bot wait is authorized.

Codex — GPT-6 Astra

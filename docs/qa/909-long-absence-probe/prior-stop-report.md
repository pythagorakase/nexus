# Work Order 909: Stop Report

## Outcome

**STOP: the required PostgreSQL gate fails outside the #885 exemptions.** No live writer or Gaia turn was attempted; no long-absence behavior was measured. This is neither evidence that the failure appeared nor evidence that it did not. No PR was opened because the proof gate did not pass.

Base: `20e2c07b` (`Make Per-Seat Turn Windows Truthful (#903)`). Branch: `claude/909-long-absence-probe`. The required import check printed `/Users/pythagor/nexus/.claude/worktrees/909-long-absence-probe/nexus/__init__.py`.

## Stop Condition and Diagnosis

A fresh focused PostgreSQL run reproduced:

```text
E       AttributeError: <module 'nexus.api.narrative' from '/Users/pythagor/nexus/.claude/worktrees/909-long-absence-probe/nexus/api/narrative.py'> has no attribute '_run_post_commit_orrery_work'

tests/test_api/test_narrative_continue_validation.py:1091: AttributeError
```

The failing test is `test_pending_choice_rolls_back_when_auto_approval_validation_fails`. It creates a disposable `nexus_test_continue_*` database and uses logical slot 3, not the owner's empty slot 5. Its first rollback assertions succeed; the failure occurs while patching a retired post-commit helper before the recovery half. The current gateway wakes the scheduler through `wake_scheduler` (`nexus/api/narrative.py:131`). Diagnosis: stale test hook on the unchanged base, outside this docs-only order; not a measured re-entry defect.

The full gate reached approximately 9% before interruption after non-exempt failures. It also reported failures in `test_correspondence_pg.py`, `test_reader_asset_endpoints.py`, and a scheduler corpus test, plus the exempt `test_orrery_dev_endpoints.py` failures. These additional failures were not individually diagnosed. The full run ended during pytest teardown with `KeyError` and `KeyboardInterrupt`; it has no trustworthy final pass/fail totals and is not a passing gate. The focused rerun supplies the independently confirmed stop condition. Full logs are in [validation.log](validation.log).

## Completed Preparation

- PostgreSQL connected successfully; the Postgres.app trust-permission hazard did not occur.
- Read-only source inspection found **46 rows, maximum chunk ID 49**, not 49 rows. `SELECT current_database()` returned `save_04` before source query steps.
- Created `qa640_909_long_absence` using `CREATE DATABASE ... TEMPLATE template0`, `pg_dump --format=custom`, and `pg_restore --exit-on-error --no-owner --no-acl`. The clone independently returned `('qa640_909_long_absence', 46, 49)`. No fleet/template migration was applied.
- Lane 8018 was free before the launch attempt. A disposable in-process launcher admitted the clone through `slot_utils.VALID_DBNAMES`, routed logical slot 4 to it, and checked its identity again.
- The launch stopped before spawning the gateway: an intentionally strict connection guard rejected `postgres` during the supervisor's slot-lock read. Exact error: `RuntimeError: Probe refused database 'postgres'`. `is_slot_locked` calls the maintenance database at `nexus/api/save_slots.py:139` to query `pg_db_role_setting`; this is an overstrict probe guard, not a production targeting defect. [startup.log](startup.log) preserves the traceback. The unvalidated launcher was discarded after the gate stop; a resumed probe should allow this maintenance read in a read-only connection.
- The full test suite independently used lane 8018 through `tests/scheduler_helpers.py::gateway_lane` and released it. That TEST-provider fixture is not live-probe evidence.

## Subject Census

Source: `baseline.json` → `source_before[1]`. The selection uses the same character-reference source as the shared roster (`nexus/presence/roster.py:152`), restricted to `reference='present'`. Every character with at least one such reference is listed. Gap means **49 minus last-present chunk ID**, not row count; world gaps subtract the last-present `world_time` from chunk 49's `world_time`.

| ID | Character | Last Present | Chunk-ID Gap | World-Time Gap | Summary Exists | Relationship Exists |
|---:|---|---:|---:|---|---|---|
| 11 | Unknown municipal-gray stranger | 21 | 28 | 2:16:00 | Yes | No |
| 4 | Niko Rell | 25 | 24 | 2:02:00 | Yes | Yes |
| 14 | Ora Pell | 25 | 24 | 2:02:00 | Yes | No |
| 2 | Ivo Senn | 48 | 1 | 0:08:00 | Yes | Yes |
| 3 | Elian Rook | 48 | 1 | 0:08:00 | Yes | Yes |
| 5 | Ren Vale | 48 | 1 | 0:08:00 | Yes | Yes |
| 6 | Sister Calyx | 48 | 1 | 0:08:00 | Yes | Yes |
| 8 | Vela Nash | 48 | 1 | 0:08:00 | Yes | Yes |
| 12 | Tam Oris | 48 | 1 | 0:08:00 | Yes | Yes |
| 1 | Mara Vey | 49 | 0 | 0:00:00 | Yes | Yes |
| 18 | Kessa Brin | 49 | 0 | 0:00:00 | Yes | Yes |

The selected three are **Unknown municipal-gray stranger (11), Niko Rell (4), Ora Pell (14)**. Niko and Ora tie; both qualify under the order's explicit summary-or-relationship rule even though their summaries are Retrograde stubs. Niko's directed relationship toward Mara has `valence_current=-0.547004997350` and type `enemy`; Mara's separate directed row toward Niko is positive. The stranger and Ora have no relationship rows, so a numeric relationship-temperature baseline is unavailable for them.

There is a further design ambiguity for the coordinator: the stranger's last `present` reference is chunk 21, but that chunk's prose does not identify the stranger. It describes the qualified relay-chamber account and third receipt. This is a roster/prose mismatch, not proof of a generated continuity failure. Niko and Ora's chunk 25 clearly depicts their planned exit through the west conduit, the biscuit tin passing to Mara, and Ora's refusal to let her route become a rescue story. Full source prose and current character rows are retained in `baseline.json` → `subject_source`.

The frontier is the Wickglass Guild dispatch box adjoining the loading arcade. Source chunk 49 already has a recorded choice containing deliberate false claims about Nera and Tam; a resumed probe must explicitly replace that choice with the intended re-entry input on the clone and document it. No source choice was edited here.

## Per-Turn Evidence and Rubric

No turn ran. Therefore rendered entity-dossier lines, retrieved chunk IDs, accepted probe prose, and provider token counts are **unavailable**, not zero-valued observations. Probe paid attempts: **0 of 8**. Source prose in the baseline is preparation only.

| Planned Turn | Subject | Astra: History / State / Temperature / Fabricated History | Coordinator: Same Four Items |
|---|---|---|---|
| 1A | Municipal-gray stranger | Not run | Pending; no generated artifact |
| 1B | Municipal-gray stranger | Not run | Pending; no generated artifact |
| 2A | Niko Rell | Not run | Pending; no generated artifact |
| 2B | Niko Rell | Not run | Pending; no generated artifact |
| 3A | Ora Pell | Not run | Pending; no generated artifact |
| 3B | Ora Pell | Not run | Pending; no generated artifact |

Do not assign 1 (absent) to a turn that did not occur. On resumption use the specified 0/1/2 scale and record independent columns without averaging; missing valence baselines must be disclosed alongside the temperature scores.

## Validation Commands and Verbatim Tails

Run from this worktree:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/909-long-absence-probe/nexus/__init__.py
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest
```

```text
KeyError: <_pytest.stash.StashKey object at 0x109e99c20>

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/subprocess.py:2011: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -x tests/test_api/test_narrative_continue_validation.py
```

```text
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_continue_validation.py::test_pending_choice_rolls_back_when_auto_approval_validation_fails
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 13 passed, 7 warnings in 11.93s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The discarded launcher was formatted with `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black scripts/qa_shift/long_absence_probe.py`; tail: `1 file reformatted.` No UI build was run; this order changes no UI.

## SQL and Artifacts

[probe.sql](probe.sql) records every distinct probe-authored SQL statement, including introspection and cleanup. Repeated `SELECT current_database()` checks are identified there; [baseline.json](baseline.json) preserves the source/clone results. The repository fixtures' SQL remains in the unchanged tests; `pg_dump`/`pg_restore` perform their normal internal catalog/restore statements. No hand-written mutation targeted any save database.

## Cleanup

The report was written before dropping the clone. Final read-only checks returned `('qa640_909_long_absence', 46, 49)` and `('save_04', 46, 49)`: the source count and frontier are unchanged. `DROP DATABASE qa640_909_long_absence` completed; the catalog query then returned no matching database. Lane cleanup used:

```sh
NEXUS_GATEWAY_PORT=8018 NEXUS_API_URL=http://127.0.0.1:8018 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m nexus.cli down
lsof -nP -iTCP:8018 -sTCP:LISTEN
```

`nexus down` output: `nothing running`. `lsof` returned exit 1 with empty output. [cleanup.json](cleanup.json) preserves the checks. The full gate's fixture-owned temporary databases were left to its teardown; no unrelated database was dropped by hand.

## Recommendation and Coordinator Questions

**The live failure remains unmeasured.** No conclusion for #913 (reconnect summaries), #911 (state-change salience), or #793 (compiled dossier) follows from this stopped run. Preserve the #737 ruling, but do not count this report as its live-evidence gate. There is likewise no new evidence for #912's belief-claim kind.

1. Repair or explicitly exempt the stale `_run_post_commit_orrery_work` test hook and triage the other gate failures before resuming the paid probe.
2. Resolve how to select a last-appearance history fact for the stranger when the roster's last-present chunk lacks the stranger in its prose.
3. Confirm how independent temperature scoring should represent subjects with no `character_relationships` row.

Codex — GPT-6 Astra.

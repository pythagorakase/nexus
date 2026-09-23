# Need-Tick Regression Verification

## Status

The coordinator accepted saturation and authorized the async timestamp repair.
Merged `origin/main` at `34f008ed` (PR #904); its URL repair cleared all six
previous connection errors. The required gates pass under the authorized #885
empty-slot-5 exemptions listed below. No migration, paid call, or manually
started gateway was needed. The lifecycle fixture owned its isolated services.

## Mechanism

`git diff 1099ea5b...82ca8a9d` shows the causal change in
`nexus/agents/orrery/resolver.py:1280`: the old historical query excluded
`cer.reference_type = 'present'`; the new shared `all_references` view includes
historically present characters. Both versions exclude the current anchor's
present actors (`resolver.py:1386`, now via `read_roster`). The roster design
explicitly requires that historical pool; reverting its selection would conceal
the problem and incorrectly narrow offscreen simulation.

There is no changed need-clock anchor in #900. Resolver debt hydration and the
sync/async need writers all call `effective_debt_score` with stored
`last_evaluated_at`. Neither last presence nor `last_fulfilled_at` is the accrual
anchor. New rows inherit canonical chunk world time or `base_timestamp` from
`orrery_sync_character_need_states` (migration 100).

The lifecycle fixture's story base is `1347-06-11T03:21:00Z`
(`tests/fixtures/golden_path_wizard_cache.json:179`). Its empty background anchor
is `2196-07-06T23:00:00Z` (`tests/test_connection_lifecycle.py:97`). Character 1,
previously only referenced as present, now becomes an offscreen actor. Sleep's
collapse branch discharges 4 (`templates.py:3057`):

```text
(2196-07-06T23:00Z - 1347-06-11T03:21Z) / 1 hour = 7442827.65
0 + 7442827.65 * 1 - 4 = 7442823.65
```

`commit_orrery_tick_sync` -> `_apply_state_delta_sync` ->
`_apply_need_fulfillment_sync` -> `_load_need_debt_sync` ->
`effective_debt_score` -> unchanged numeric-domain guard is the complete sync
path (`events.py:906,2237,2981,5480`). The async path mirrors it at
`events.py:1179,2546,3050,5543`. #900's Bleed change selects physical proximity
anchors, and its experience-duration change reads present streaks; neither
feeds the need anchor or debt calculation.

## Production Decision and Fix

Production can select the same historically present actor when absent at the
anchor and still inside the relevance window (or retained by another actor
source). A returning present character gets need pressure rather than automatic
offscreen fulfillment; after departing it is eligible for fulfillment again.
At the default rate, overflow needs roughly 114 world years without sufficient
fulfillment. A month-long absence already creates implausible debt (717 after
one collapse), even though it fits the SQL domain. The fixture's 849-year leap
is unrealistic for its medieval story, but exposes a genuine unbounded-accrual
path. The seed was not moved.

Applicable active characters' needs continue to accrue on the world clock from
`last_evaluated_at`. New accrual saturates at per-need
`orrery.sunhelm.accrual_debt_caps`, defaulting to each critical threshold:
sleep 72, hunger 48, thirst 24, socialize 336, intimacy 720. This models critical
pressure, not an unlimited backlog of missed routine actions. It neither
invents offscreen meals/sleep nor resets timestamps for absence. Only a real
fulfillment advances the persisted anchor and retains the existing chunk,
fulfillment, and resolution provenance. Stored debt above the cap is preserved,
not silently repaired. Numeric-domain validation is unchanged.

The shared function covers resolver reads, sync/async writes, and replay.
Configuration goes through `OrrerySunhelmSettings`, requiring every need and a
cap at least critical and within numeric(8,2). Existing replay's documented
limitation remains: it uses current Sunhelm tuning (`replay.py:2219`), so exact
replay across tuning changes is not claimed. Existing stored high debt is not
migrated. The old domain regression now supplies a malformed fulfillment delta
to exercise the unchanged guard, because elapsed time itself now saturates.

## Disposable SQL/Python Probe

A `qa640_need_probe_*` schema-and-vocabulary clone was seeded with one character
present in the first chunk and an empty 2196 anchor. The probe compared the old
SQL predicate with `compose_actor_bindings`, selected built-in templates, and
called the real synchronous tick. The context manager dropped the clone.

```sql
SELECT DISTINCT entity_id FROM chunk_entity_references_v
WHERE reference_type IS DISTINCT FROM 'present'
  AND chunk_id BETWEEN :first AND :anchor;
SELECT debt_score, last_evaluated_at, last_fulfilled_at
FROM character_need_states
WHERE character_entity_id = :actor AND need_type = 'sleep';
```

```text
PROBE old historical pool: []
PROBE new bindings: ({<Slot.ACTOR: 'actor'>: 1},)
PROBE present at anchor: set()
PROBE resolutions: [('sleep', {'type': 'sleep', 'duration_hours': 4, 'quality': 'collapse_rough', 'discharge_debt': 4})]
PROBE before: (Decimal('0.00'), datetime.datetime(1347, 6, 10, 22, 24, 58, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=68638))), None)
PROBE uncapped debt after discharge: 7442823.65
PROBE after: (Decimal('68.00'), datetime.datetime(2196, 7, 6, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=72000))), datetime.datetime(2196, 7, 6, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=72000))))
```

The server renders timestamps in local offsets (including historical local
mean time); the before timestamp equals `1347-06-11T03:21:00Z`, and the after
timestamp equals `2196-07-06T23:00:00Z`. Selection is unchanged by the fix.

`tests/test_orrery/test_need_absence_pg.py` is the reproducible minimal probe plus
regression: present -> absent 30 days / 310122 days -> present pressure ->
offscreen fulfillment, with real tables and built-in templates. All four sync/async absence cases pass, including persisted debt, world-time
anchors, source chunk, and fulfillment metadata.

Current disposable probe (sync and async, both intervals):

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_orrery/test_need_absence_pg.py -k long_absence
```
```text
historical selection: before=[], after=({<Slot.ACTOR: 'actor'>: 1},)
stored debt=0.00, evaluated=1347-06-10 22:24:58-04:56:02, fulfilled=None
anchor before=1347-06-11T03:21:00+00:00, after=1347-07-10T23:24:58-04:56:02, debt=68.00
historical selection: before=[], after=({<Slot.ACTOR: 'actor'>: 1},)
stored debt=0.00, evaluated=1347-06-10 22:24:58-04:56:02, fulfilled=None
anchor before=1347-06-11T03:21:00+00:00, after=2196-07-11T00:21:00-04:00, debt=68.00
historical selection: before=[], after=({<Slot.ACTOR: 'actor'>: 1},)
stored debt=0.00, evaluated=1347-06-10 22:24:58-04:56:02, fulfilled=None
anchor before=1347-06-11T03:21:00+00:00, after=1347-07-10T23:24:58-04:56:02, debt=68.00
historical selection: before=[], after=({<Slot.ACTOR: 'actor'>: 1},)
stored debt=0.00, evaluated=1347-06-10 22:24:58-04:56:02, fulfilled=None
anchor before=1347-06-11T03:21:00+00:00, after=2196-07-11T00:21:00-04:00, debt=68.00
4 passed, 3 deselected in 4.24s
```

## Async Timestamp Repair

`_need_applies_to_entity_async` first used `$2 IS NULL`, leaving asyncpg unable
to infer the parameter type before the timestamp comparison. Both existing
async absence cases reproduced `AmbiguousParameterError` after merging #904.
The fix explicitly casts the parameter to `timestamptz` in both occurrences.

The same statement family contained two siblings:
`_routine_zone_destination_async` (`events.py:7040`) and
`_location_class_destination_async` (`events.py:7076`). Both now cast their
nullable world clocks too. A real disposable-schema test verifies preferred
place selection with a null clock, before expiry, and at the exact expiry
boundary. No other uncast `$N IS NULL` remains in `events.py`.

## Accepted Policy and Follow-Up

Debt beyond critical carries no additional behavioral meaning in the Orrery;
saturating new accrual loses nothing a package can act on. Stored debt remains
preserved, and the numeric-domain guard at `events.py:2932` is unchanged.
Whether long-absent characters should care for their own needs offscreen is a
taste-side follow-up for the dynamism campaign, not part of this repair.
Replay still uses current tuning; no cross-configuration replay guarantee or
stored-debt migration is added.

## Validation

All commands ran from this worktree with the shared interpreter and no gateway
URL/port overrides. Import proof:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```
```text
/Users/pythagor/nexus/.claude/worktrees/900-need-tick-regression/nexus/__init__.py
```

The first implementation's recorded baseline (commit `79f2b822`) ran the
lifecycle case before edits: `1 failed in 18.41s`. The two synchronous absence
cases against unchanged production code failed with `717.00 > 72.0` and
`NeedDebtScoreDomainError: ... character=1, need=sleep, value=7442925.0`
(`2 failed in 2.24s`). This round independently reproduced the async defect:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_need_absence_pg.py
```
```text
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[True-30]
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[True-310122]
2 failed, 2 passed in 4.34s
```

Final commands and verbatim result tails:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_needs_accrual.py tests/test_orrery/test_need_debt_domain.py tests/test_orrery/test_need_clock_anchor_pg.py
```
```text
43 passed, 5 warnings in 9.94s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```
```text
2633 passed, 776 skipped, 11 warnings in 91.86s (0:01:31)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_connection_lifecycle.py tests/test_orrery/test_resolver.py tests/test_orrery/test_bleed.py tests/test_presence_roster_pg.py
```
```text
134 passed, 5 warnings in 25.72s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery -k 'need or tick or resolver or presence or roster'
```
```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder
FAILED tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier
FAILED tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored
FAILED tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape
FAILED tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_roster_source_respects_reach_roster_liveness_and_opt_in
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
5 failed, 233 passed, 1301 deselected, 9 warnings, 4 errors in 19.29s
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/events.py nexus/agents/orrery/needs.py nexus/config/settings_models.py tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_needs_accrual.py tests/test_orrery/test_need_clock_anchor_pg.py
```
```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.
```

`git diff --check` exited zero. The offline skips are opt-in tests; no test
was skipped in the required PostgreSQL runs. During sibling-test construction,
an invalid textual layer and then a nonexistent layer ID produced fixture
errors (`3 failed, 40 passed, 5 warnings in 10.88s` and
`3 failed, 40 passed, 5 warnings in 10.65s`). Seeding the real parent layer
resolved them. No fixture skip or xfail was introduced.

## Exempt Failures and Coordinator Questions

All nine broad-gate IDs above are empty-slot-5 dependencies covered by #885:
four replay cases cannot fetch their required existing character, three
composition-source cases and the patron case raise `NoResultFound`, and the
reveal case now gets past the repaired URL but cannot fetch an existing place
(`test_reveal_live.py:184`). These failures occur before the repaired need
accrual path. No URL or async parameter error remains.

Read-only evidence, with `PGOPTIONS='-c default_transaction_read_only=on'`:

```sql
SHOW default_transaction_read_only;
-- on
SELECT (SELECT count(*) FROM narrative_chunks),
       (SELECT count(*) FROM characters), base_timestamp
FROM global_variables LIMIT 1;
-- (0, 0, NULL)
```

No blocking coordinator questions remain. Offscreen self-care is the deferred
design question described above. No merge or review-bot wait is authorized.

Codex — GPT-6 Astra

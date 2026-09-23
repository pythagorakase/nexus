# Need-Tick Regression Verification

## Status: Stop-Report

The candidate fix repairs the reproduced synchronous tick. The required broad
PostgreSQL gate is blocked by six non-exempt connection-URL errors and the new
async parity cases expose an existing parameter-typing error. Per the frozen
work order's escape hatch, implementation stopped. No PR was opened or merged.
The failing async cases remain visible for the coordinator; no skips or xfails
were added. No production migration, gateway, or paid-provider call was added.
The required lifecycle fixture owned and shut down its isolated local services.

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

## Production Decision and Candidate Fix

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
offscreen fulfillment, with real tables and built-in templates. The sync cases
pass. Async cases stop in the pre-existing applicability query before accrual.

## Validation

All commands ran from this worktree using the shared interpreter. Import proof:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```
```text
/Users/pythagor/nexus/.claude/worktrees/900-need-tick-regression/nexus/__init__.py
```

Initial reproduction, before edits:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
```
```text
FAILED tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
1 failed in 18.41s
```

New synchronous regression against unchanged production code:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_need_absence_pg.py
```
```text
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[30]
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[310122]
2 failed in 2.24s
```

Failures were stored debt `717.00 > 72.0` and
`NeedDebtScoreDomainError: ... character=1, need=sleep, value=7442925.0`.
An earlier `-q -s` development run failed on an incorrect tuple/list assertion
(`2 failed in 1.85s`); that assertion was corrected before the baseline above.

Focused candidate validation, before adding async parity/config cases:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_needs_accrual.py tests/test_orrery/test_need_debt_domain.py
```
```text
16 passed in 2.04s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```
```text
2633 passed, 770 skipped, 11 warnings in 98.27s (0:01:38)
```

This offline run collected before adding the two async parameter cases. Its
skips are opt-in tests, not PostgreSQL proof. The broad run below collected the
final tests, including both async cases.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_connection_lifecycle.py tests/test_orrery/test_resolver.py tests/test_orrery/test_bleed.py tests/test_presence_roster_pg.py
```
```text
134 passed, 5 warnings in 27.33s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery -k 'need or tick or resolver or presence or roster'
```
```text
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[True-30]
FAILED tests/test_orrery/test_need_absence_pg.py::test_long_absence_reappearance_and_offscreen_need_tick[True-310122]
FAILED tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder
FAILED tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier
FAILED tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored
FAILED tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_roster_source_respects_reach_roster_liveness_and_opt_in
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity
ERROR tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick
ERROR tests/test_orrery/test_geo_resolver_live.py::test_covering_zone_wins_over_nearer_noncovering_zone
ERROR tests/test_orrery/test_geo_resolver_live.py::test_nearest_boundary_wins_outside_all_zones
ERROR tests/test_orrery/test_geo_resolver_live.py::test_zone_id_breaks_equal_distance_tie
ERROR tests/test_orrery/test_geo_resolver_live.py::test_no_bounded_zone_raises
ERROR tests/test_orrery/test_geo_resolver_live.py::test_story_active_zone_and_corruption_raise
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
6 failed, 223 passed, 1301 deselected, 9 warnings, 10 errors in 16.47s
```

An initial attempt of this broad command hit a new-test import typo
(`commit_orrery_tick` instead of `commit_orrery_tick_async`):
`1301 deselected, 9 warnings, 1 error in 3.09s`. That typo was fixed before the
complete run above.

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/needs.py nexus/config/settings_models.py tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_needs_accrual.py tests/test_orrery/test_need_clock_anchor_pg.py
```
```text
All done! ✨ 🍰 ✨
5 files would be left unchanged.
```

`git diff --check` exited zero.

## Blockers and Coordinator Questions

Eight broad-gate cases match #885's empty-slot-5 class: the four replay cases,
three composition-source cases, and polymorphic-patron case listed above. They
raise `TypeError: cannot unpack non-iterable NoneType object` or `NoResultFound`.

Six additional errors are **not** claimed as #885 exemptions: the five geo
resolver cases and the reveal case fail with:

```text
psycopg2.OperationalError: connection to server on socket "/tmp/.s.PGSQL.5432" failed: FATAL:  unrecognized configuration parameter "+TimeZone"
```

The untouched fixtures pass `get_slot_db_url(...)` directly to psycopg2
(`test_geo_resolver_live.py:22` and the reveal fixture). The latest #885 comment
explicitly separates this #897 URL regression from the exempt class and says
it is being repaired separately. Which prerequisite repair should be integrated?

The two added async cases fail with:

```text
asyncpg.exceptions.AmbiguousParameterError: could not determine data type of parameter $2
```

The unchanged `_need_applies_to_entity_async` query uses `$2 IS NULL` before
its timestamp comparison (`events.py:5647`). No new accrual code has executed
at that point. Should its explicit timestamp-typing repair join this order,
or be handled as a prerequisite? This run leaves it unchanged and records the
failing real-path coverage.

The candidate uses critical thresholds as default saturation limits. Claude
should review that behavioral choice before resuming validation and opening a
PR. No claim of completed proof gates or async execution parity is made.

Codex — GPT-6 Astra

# Verification for #785 S1a: Travel Reachability Probe

Branch `claude/785-travel-reachability-probe`, cut from `origin/main` at 9fff6a75 (still the newest `origin/main` when this was written). All commands ran from the worktree root with the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) and `PYTHONPATH=$PWD`; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` were unset. The import check printed `/Users/pythagor/nexus/.claude/worktrees/785-travel-reachability-probe/nexus/__init__.py`. No migration, no gateway, no paid call; `save_02`, `save_03` and `save_04` were only read.

## Cited Lines (Checked at 9fff6a75)

The work order cited these at 41783c1d. None of the cited files changed between 41783c1d and 9fff6a75 (`git diff 41783c1d 9fff6a75 --stat` over `nexus/agents/orrery/`, `nexus/api/orrery_dev_endpoints.py`, `nexus/database.py` and `nexus.toml` is empty), and every citation holds except one line number noted below.

- Travel-starting branches: `nexus/agents/orrery/templates.py:1811-1839` (commute to work), `:1840-1867` (commute home), `:1995-2019` (charter), `:2020-2049` (covert), `:2050-2078` (planned departure), `:3434-3474` ("Seek company after extended isolation"), `:3529-3567` ("Set out toward public company"); `travel.start` keys at `:1826`, `:1854`, `:2010`, `:2040`, `:2069`, `:3454`, `:3547`.
- Relocation handoff: `advance_relocation_plan` "Commit to the road" at `templates.py:4448-4471` (`project.complete`, preemptive); `nexus/agents/orrery/events.py:4803` and `:4898` start travel for a completed `plan_relocation` project.
- `start_relocation_plan` at `templates.py:4351-4415`, the only `project.start` with `project_type: plan_relocation` (`:4400-4404`); its gate requires `at_routine_anchor("home")` (`:4368`); `_at_routine_anchor` returns False without an anchor row (`nexus/agents/orrery/substrate.py:1756-1771`).
- Retrograde seeding: `_insert_seeded_project` at `nexus/agents/orrery/retrograde_persistence.py:1542-1579`; `RetrogradeProjectType` lists `plan_relocation` (`nexus/agents/orrery/retrograde_seed_candidates.py:26-33`); the open-project statuses `('active', 'paused', 'stalled')` at `retrograde_persistence.py:1533`.
- Social gates: `has_need_debt_at_or_above("socialize", 24)` at `templates.py:3391`; accrual in world hours at `nexus/agents/orrery/needs.py:285-315` and `nexus.toml:661` (`socialize = 1.0`); `can_move_publicly` at `substrate.py:1019-1044` with `PUBLIC_PLACE_CLASSES` at `:135`; `has_location_class_destination` at `substrate.py:1166-1200`; the leaf name format at `substrate.py:1136`.
- Hydration: `hydrate_world_state` at `nexus/agents/orrery/resolver.py:515-822`; locations only for characters with `current_location` (`:568-581`); place classes from `places.type` and live place tags (`:583-629`); need debt (`:746-753`, `_load_need_debt_scores` at `:2940-2979`); routine anchors (`:859-889`); travel rows (`:892-941`); `compose_actor_bindings` at `:1320`.
- Production parity: `explain_dry_run` policy derivation and hydration at `nexus/agents/orrery/audit.py:569-592`, templates at `:594`, roster at `:626-630`, actor-only stacks at `:595-597` and `:712-719`; the dashboard's settings and anchor at `nexus/api/orrery_dev_endpoints.py:253-263`, `:282-294` and `:456-473`; `playable_narrative_predicate` at `nexus/agents/orrery/reconstruction.py:28`.
- The audit dashboard traces branches only behind a passing gate: `if gate_passed:` is at `nexus/agents/orrery/explain.py:288` (the order says `:289`, which is the `select_branch` call inside it); unconsidered branches get `BranchTrace(considered=False, trace=None)` inside the loop at `:314-329` (`if not considered:` at `:317`).
- Threshold source: `resolve_evidence` at `nexus/agents/orrery/evidence.py:2001`, the `has_need_debt_at_or_above` resolver at `:682-695`.
- Read-only session: `create_slot_engine` at `nexus/database.py:86-119`; explicit options take precedence over `PGOPTIONS` at `:250-262`.

The order's slot table was rechecked read-only on 2026-09-30 (`PGOPTIONS='-c default_transaction_read_only=on' psql -d <db>`): `save_02|35|35|77|0|35|0|0|138`, `save_03|17|10|5|0|0|0|75|138`, `save_04|23|10|7|0|0|0|103|138` (active characters, with `current_location`, places, routine anchors, travel rows, `plan_relocation` projects, Orrery resolutions, newest migration). The premise holds.

## Probe Output

`PGOPTIONS='-c default_transaction_read_only=on' PYTHONPATH=$PWD $PY scripts/qa_shift/travel_reachability.py --dbname save_02 --dbname save_03 --dbname save_04` (exit 0; stderr carried only the three `INFO Probing <db> at anchor chunk <id>` lines). The anchor world times print in UTC: `save_03` and `save_04` end at 18:07 and 18:37 Eastern, as the order states. No statement raised a read-only violation, so hydration and roster composition issued no write.

### save_02

anchor chunk: 1425 (2073-10-31T13:04:00+00:00); active characters: 35; with current_location: 35; places: 77; social-class places: 0; routine anchors: 0; travel rows: at_place 35; open plan_relocation projects: 0; max socialize debt: 0.00 (gate 24); roster: 2

| Row | Roster actors | Gate passes | Branch passes | Both pass | Blocking predicates | Winners when both pass |
|---|---|---|---|---|---|---|
| routine_commute / Commute to the scheduled workplace | 2 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (2); away_from_routine_anchor(work@actor) (2); has_routine_anchor(home@actor) (2); has_routine_anchor(work@actor) (2); routine_anchor_due(home@actor) (2); routine_anchor_due(work@actor) (2); routine_anchor_has_destination(work@actor) (2) |  |
| routine_commute / Commute home after the day's obligations | 2 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (2); away_from_routine_anchor(work@actor) (2); has_routine_anchor(home@actor) (2); has_routine_anchor(work@actor) (2); routine_anchor_due(home@actor) (2); routine_anchor_due(work@actor) (2); routine_anchor_has_destination(home@actor) (2) |  |
| travel / Charter private transport | 2 | 0 | 0 | 0 | has_travel_destination(@actor) (2); is_in_transit(@actor) (2); resources_at_or_above(wealthy@actor) (2) |  |
| travel / Slip out along covert routes | 2 | 0 | 0 | 0 | fame_at_or_above(renowned@actor) (2); has_tag(route_familiar@actor) (2); has_tag(travel_provisioned@actor) (2); has_tag(travel_ready@actor) (2); has_travel_destination(@actor) (2); is_in_transit(@actor) (2) |  |
| travel / Depart toward the planned destination | 2 | 0 | 0 | 0 | has_tag(route_familiar@actor) (2); has_tag(travel_provisioned@actor) (2); has_tag(travel_ready@actor) (2); has_travel_destination(@actor) (2); in_location_class(transit@actor) (2); is_in_transit(@actor) (2) |  |
| socialize / Seek company after extended isolation | 2 | 0 | 0 | 0 | can_move_publicly(@actor) (2); has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (2); has_need_debt_at_or_above(socialize,168@actor) (2); has_need_debt_at_or_above(socialize,24@actor) (2); NOT(count_co_located(1@actor)) (1) |  |
| socialize / Set out toward public company | 2 | 0 | 0 | 0 | can_move_publicly(@actor) (2); has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (2); has_need_debt_at_or_above(socialize,24@actor) (2); NOT(count_co_located(1@actor)) (1) |  |
| advance_relocation_plan / Commit to the road | 2 | 0 | 0 | 0 | project_due(plan_relocation,completion@actor) (2); project_due(plan_relocation,ready@actor) (2) |  |
| start_relocation_plan / Begin putting something aside | 2 | 0 | 2 | 0 | at_routine_anchor(home@actor) (2); count_recent_events_at_least(errands_run,>=2,<=30@actor) (2); count_recent_events_at_least(recreation_taken,>=2,<=30@actor) (2); count_recent_events_at_least(upkeep_done,>=2,<=30@actor) (2); count_recent_events_at_least(work_performed,>=2,<=30@actor) (2); recent_event(contact_deferred,<=12,actor=actor) (2); recent_event(retaliation_attempted,<=12,target=actor) (2); recent_event(threat_issued,<=12,target=actor) (2); recent_event(travel_delayed,<=12,actor=actor) (2) |  |

### save_03

anchor chunk: 100 (2189-10-17T22:07:00+00:00); active characters: 17; with current_location: 10; places: 5; social-class places: 0; routine anchors: 0; travel rows: 0; open plan_relocation projects: 0; max socialize debt: 2.87 (gate 24); roster: 4

| Row | Roster actors | Gate passes | Branch passes | Both pass | Blocking predicates | Winners when both pass |
|---|---|---|---|---|---|---|
| routine_commute / Commute to the scheduled workplace | 4 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (4); away_from_routine_anchor(work@actor) (4); has_routine_anchor(home@actor) (4); has_routine_anchor(work@actor) (4); routine_anchor_due(home@actor) (4); routine_anchor_due(work@actor) (4); routine_anchor_has_destination(work@actor) (4) |  |
| routine_commute / Commute home after the day's obligations | 4 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (4); away_from_routine_anchor(work@actor) (4); has_routine_anchor(home@actor) (4); has_routine_anchor(work@actor) (4); routine_anchor_due(home@actor) (4); routine_anchor_due(work@actor) (4); routine_anchor_has_destination(home@actor) (4) |  |
| travel / Charter private transport | 4 | 0 | 0 | 0 | has_travel_destination(@actor) (4); is_in_transit(@actor) (4); resources_at_or_above(wealthy@actor) (4) |  |
| travel / Slip out along covert routes | 4 | 0 | 0 | 0 | fame_at_or_above(renowned@actor) (4); has_tag(route_familiar@actor) (4); has_tag(travel_provisioned@actor) (4); has_tag(travel_ready@actor) (4); has_travel_destination(@actor) (4); is_in_transit(@actor) (4) |  |
| travel / Depart toward the planned destination | 4 | 0 | 0 | 0 | has_travel_destination(@actor) (4); is_in_transit(@actor) (4); has_tag(route_familiar@actor) (3); has_tag(travel_provisioned@actor) (3); has_tag(travel_ready@actor) (3); in_location_class(transit@actor) (3) |  |
| socialize / Seek company after extended isolation | 4 | 0 | 0 | 0 | has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (4); has_need_debt_at_or_above(socialize,168@actor) (4); has_need_debt_at_or_above(socialize,24@actor) (4); can_move_publicly(@actor) (3); NOT(count_co_located(1@actor)) (1) |  |
| socialize / Set out toward public company | 4 | 0 | 0 | 0 | has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (4); has_need_debt_at_or_above(socialize,24@actor) (4); can_move_publicly(@actor) (3); NOT(count_co_located(1@actor)) (1) |  |
| advance_relocation_plan / Commit to the road | 4 | 0 | 0 | 0 | project_due(plan_relocation,completion@actor) (4); project_due(plan_relocation,ready@actor) (4); NOT(has_need_debt_at_or_above(thirst,2@actor)) (2) |  |
| start_relocation_plan / Begin putting something aside | 4 | 0 | 4 | 0 | at_routine_anchor(home@actor) (4); count_recent_events_at_least(errands_run,>=2,<=30@actor) (4); count_recent_events_at_least(recreation_taken,>=2,<=30@actor) (4); count_recent_events_at_least(upkeep_done,>=2,<=30@actor) (4); count_recent_events_at_least(work_performed,>=2,<=30@actor) (4); recent_event(contact_deferred,<=12,actor=actor) (4); recent_event(retaliation_attempted,<=12,target=actor) (4); recent_event(threat_issued,<=12,target=actor) (4); recent_event(travel_delayed,<=12,actor=actor) (4); project_due(plan_relocation,start@actor) (1) |  |

### save_04

anchor chunk: 49 (2189-10-17T22:37:00+00:00); active characters: 23; with current_location: 10; places: 7; social-class places: 0; routine anchors: 0; travel rows: 0; open plan_relocation projects: 0; max socialize debt: 3.37 (gate 24); roster: 16

| Row | Roster actors | Gate passes | Branch passes | Both pass | Blocking predicates | Winners when both pass |
|---|---|---|---|---|---|---|
| routine_commute / Commute to the scheduled workplace | 16 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (16); away_from_routine_anchor(work@actor) (16); has_routine_anchor(home@actor) (16); has_routine_anchor(work@actor) (16); routine_anchor_due(home@actor) (16); routine_anchor_due(work@actor) (16); routine_anchor_has_destination(work@actor) (16); has_minimal_context(@actor) (1) |  |
| routine_commute / Commute home after the day's obligations | 16 | 0 | 0 | 0 | away_from_routine_anchor(home@actor) (16); away_from_routine_anchor(work@actor) (16); has_routine_anchor(home@actor) (16); has_routine_anchor(work@actor) (16); routine_anchor_due(home@actor) (16); routine_anchor_due(work@actor) (16); routine_anchor_has_destination(home@actor) (16); has_minimal_context(@actor) (1) |  |
| travel / Charter private transport | 16 | 0 | 0 | 0 | has_travel_destination(@actor) (16); is_in_transit(@actor) (16); resources_at_or_above(wealthy@actor) (16) |  |
| travel / Slip out along covert routes | 16 | 0 | 0 | 0 | fame_at_or_above(renowned@actor) (16); has_tag(route_familiar@actor) (16); has_tag(travel_provisioned@actor) (16); has_tag(travel_ready@actor) (16); has_travel_destination(@actor) (16); is_in_transit(@actor) (16) |  |
| travel / Depart toward the planned destination | 16 | 0 | 0 | 0 | has_travel_destination(@actor) (16); is_in_transit(@actor) (16); has_tag(route_familiar@actor) (8); has_tag(travel_provisioned@actor) (8); has_tag(travel_ready@actor) (8); in_location_class(transit@actor) (8) |  |
| socialize / Seek company after extended isolation | 16 | 0 | 0 | 0 | has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (16); has_need_debt_at_or_above(socialize,168@actor) (16); has_need_debt_at_or_above(socialize,24@actor) (16); NOT(count_co_located(1@actor)) (8); can_move_publicly(@actor) (8) |  |
| socialize / Set out toward public company | 16 | 0 | 0 | 0 | has_location_class_destination(commerce,entertainment,meeting,place_open@actor) (16); has_need_debt_at_or_above(socialize,24@actor) (16); NOT(count_co_located(1@actor)) (8); can_move_publicly(@actor) (8) |  |
| advance_relocation_plan / Commit to the road | 16 | 0 | 0 | 0 | project_due(plan_relocation,completion@actor) (16); project_due(plan_relocation,ready@actor) (16); NOT(has_need_debt_at_or_above(thirst,2@actor)) (4) |  |
| start_relocation_plan / Begin putting something aside | 16 | 0 | 16 | 0 | at_routine_anchor(home@actor) (16); recent_event(contact_deferred,<=12,actor=actor) (16); recent_event(retaliation_attempted,<=12,target=actor) (16); recent_event(threat_issued,<=12,target=actor) (16); recent_event(travel_delayed,<=12,actor=actor) (16); count_recent_events_at_least(errands_run,>=2,<=30@actor) (9); count_recent_events_at_least(recreation_taken,>=2,<=30@actor) (9); count_recent_events_at_least(upkeep_done,>=2,<=30@actor) (9); count_recent_events_at_least(work_performed,>=2,<=30@actor) (9); has_minimal_context(@actor) (1); project_due(plan_relocation,start@actor) (1) |  |

## JSON Summary Counts

The same command with `--json` wrote a 507,019-byte document (exit 0). Counts over every probed actor, roster or not:

| Database | Actors | In roster | Actor rows | Gate passes | Branch passes | Both pass |
|---|---|---|---|---|---|---|
| `save_02` | 35 | 2 | 315 | 0 | 35 | 0 |
| `save_03` | 17 | 4 | 153 | 0 | 17 | 0 |
| `save_04` | 23 | 16 | 207 | 0 | 23 | 0 |

Every branch pass is the `start_relocation_plan` "Begin putting something aside" branch, whose condition is `ALWAYS`; its gate fails for every actor. No actor passes any probed gate, so no `explain_stack` ran and every `winner_id` and `selection_window_ids` is `null`.

The `substrate` object of each database in the JSON:

```
save_02 {"active_characters": 35, "with_current_location": 35, "places": 77, "social_class_places": 0, "routine_anchors": 0, "travel_rows_by_status": {"at_place": 35}, "open_plan_relocation_projects": 0, "max_socialize_debt": 0.0, "socialize_gate_threshold": 24.0, "roster_size": 2}
save_03 {"active_characters": 17, "with_current_location": 10, "places": 5, "social_class_places": 0, "routine_anchors": 0, "travel_rows_by_status": {}, "open_plan_relocation_projects": 0, "max_socialize_debt": 2.8666666666666667, "socialize_gate_threshold": 24.0, "roster_size": 4}
save_04 {"active_characters": 23, "with_current_location": 10, "places": 7, "social_class_places": 0, "routine_anchors": 0, "travel_rows_by_status": {}, "open_plan_relocation_projects": 0, "max_socialize_debt": 3.3666666666666667, "socialize_gate_threshold": 24.0, "roster_size": 16}
```

`save_02` is a retrofitted slot; its whole section, the 35 `at_place` travel rows included, is retrofit evidence, not native evidence. None of the three slots reaches the socialize debt gate (24), so the high-debt case of #785 (785-R9, `ref_codex_bakeoff_2026_07`) is not diagnosed by this probe.

## Test and Lint Tails

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_travel_reachability_pg.py tests/test_travel_reachability.py tests/test_owner_target_guard.py` (rerun at 81e8ede9, after the anchor-blockers test gained the protagonist `in_roster` false and `roster_size == 1` assertions):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_785_reach_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
85 passed, 2 warnings in 10.78s
```

The two CLI tests (`test_probe_reports_anchor_blockers`, `test_social_class_destination_differential`) run the probe as a child process, which is outside the dbname audit (`tests/dbname_audit.py:59`), so the audit lines above record the fixtures and `test_session_is_read_only`, not the probe's own connections; those are bounded by the explicit `--dbname <clone>`, the probe's own `current_database()` check (`scripts/qa_shift/travel_reachability.py:114-118`), and the `database['dbname'] == dbname` assertion in `test_probe_reports_anchor_blockers`.

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2655 passed, 423 skipped, 8 warnings in 421.02s (0:07:01)
```

`$PY -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 742 skipped, 7 warnings in 38.20s
```

`$PY -m pytest -q tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.96s
```

`$PY -m black`, `$PY -m flake8` and `$PY -m mypy` on `scripts/qa_shift/travel_reachability.py`, `tests/test_travel_reachability.py` and `tests/test_travel_reachability_pg.py`: `3 files left unchanged.`; no flake8 output; `Success: no issues found in 3 source files`.

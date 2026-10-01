# 783-S6 Verification and Stop Report

Status: **STOP — Required Changed-File Gates Fail on Untouched HEAD**. No push or PR.

Inspected implementation commit: `c357ef46db4ab638ed9d8e85733ede33de0ab541`.
Baseline and latest fetched `origin/main`: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`.
`git fetch origin main` succeeded; `git rebase origin/main` reported:

```text
Current branch claude/783-routine-clock-required is up to date.
```

LG-Q1's issue-recorded decision is **B. Release all three now**. The live
`gh issue view 783 --repo pythagorakase/nexus --comments` record was read after
the common rules, frozen order, and issue snapshot. It releases this doctrine
fix without changing the feature sequencing or the settled Q9 semantics.

## Stop Reason

The common rules require: “if honest attempts cannot satisfy a rule or a gate,
STOP and write a stop-report (what you tried, exact errors, your diagnosis).”
The exact changed-file mypy gate fails with 26 errors in four files. Replaying
untouched HEAD using mypy's `--shadow-file` produces the same 26 error kinds
at the corresponding original lines. The flake8 gate has one pre-existing
E501 in `resolver.py`: current line 1355, baseline line 1347. Its 133-character
SQL literal is unchanged. No exception for these failures is recorded in the
frozen order; #885's exempt slot-5 failures do not apply. Fixing the affected
unrelated sorting, binding-name, fixture-index, and dictionary typing code
would expand the frozen slice. Those fixes are deferred to the coordinator.

The new test's own E501 was corrected by splitting one SQL string into
adjacent literals; the resulting SQL is identical. Black passes all nine files.
The complete PostgreSQL proof set and both offline suites passed. An earlier
proof run failed in the changed evidence fixture because `seed_protagonist`
would reset the seeded 2073 base timestamp to its default 2100 timestamp.
Passing the seeded timestamp explicitly corrected that fixture; the complete
proof rerun passed. No existing assertion was removed except the exact obsolete
weather test named in the order.

## Current Behavior and Safety Trace

- `substrate.py:1807-1808` refuses clockless schedules first. Remaining schedule
  branches at 1809-1823 are unchanged from baseline. `routine_anchor_due` retains
  the non-evaluation guards at 1685-1692.
- `resolver.py:548-555` chooses override or stored clock and refuses None before
  entity hydration at 558. `load_anchor_world_time` remains optional at
  2912-2934; absence of an id, metadata row, or stored clock still returns None
  for non-resolver readers.
- `resolver.py:2436` and `audit.py:579` share hydration. The production resolver
  has no catch there; the developer endpoint catches only
  `OverrideValidationError` at 475-478. LORE's existing broad turn handler at
  `lore.py:419-428` returns an error string for non-generation failures; this
  slice adds no handler.
- Gateway opening: `narrative.py:992-1026` dispatches bootstrap (`parent=0`) to
  `generate_narrative_async`; `narrative_generation.py:261-280` uses the existing
  direct bootstrap path. `generate_bootstrap_narrative` at 641-815 calls LOGON
  directly and has no hydration or resolver caller. No bypass was added.
- Wizard genesis: `wizard_chat.py:1355-1360` requires the base timestamp;
  1393-1398 calls `perform_transition_with_retrograde`. That flow at
  `new_story_flow.py:451-545` runs dedicated Retrograde generation/persistence,
  with no direct hydration/resolver caller. Searches in `nexus/` found no such
  caller in Retrograde modules. Its prologue is excluded by
  `reconstruction.py:28-48`; it is not the playable turn anchor.
- First continuation after bootstrap: `commit_handler_sync.py:577-592` inserts
  metadata and requires its trigger-authored clock before acceptance.
  `narrative_generation.py:287-318` sends the explicit parent id to
  `LORE.process_turn`; `lore.py:358-365,394` sends it through TurnContext to
  the Orrery phase. The phase forwards no clock override. A damaged or NULL
  parent clock now refuses; an ordinary accepted bootstrap supplies its clock.
- Empty/pre-playable callers that directly reach the turn selector can obtain
  None (`turn_cycle.py:887-915`). Both it and the developer selector
  (`orrery_dev_endpoints.py:282-294`) are proven on a real empty clone by
  `test_turn_and_dev_anchor_selection_can_return_none`.
- New real-DB tests at `test_routine_clock_required_pg.py:74-202` cover all three
  clockless entry points, rolled-back metadata deletion and NULL clocks, stored
  clocks, exclusive-end overrides, and anchorless what-if hydration. Fixtures
  at 40-56 own only `qa640_783s6_*` clones via `tests.pg_fixtures`.

No production gateway new-story path reaching clockless hydration was found.
The standalone LORE CLI diagnostic/interactive caller (`lore.py:831,869`) omits
its parent id and can hit the selector in an empty database; it is not the
wizard/gateway bootstrap path and has not been exercised against an owner slot.

## Read-Only Schema Evidence

A connection made through `tests.pg_fixtures.connect('NEXUS_template')` used
`conn.set_session(readonly=True)` before executing these reads, then rolled back:

```sql
SHOW transaction_read_only;
SELECT table_name, column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='chunk_metadata'
  AND column_name='world_time';
```

Verbatim output:

```text
transaction_read_only=on
chunk_metadata | world_time | YES | timestamp with time zone
```

## Caller Inventory

Searched `nexus/`, `scripts/`, `tests/`, and `ir_eval/` with
`rg -n 'hydrate_world_state|resolve_dry_run|explain_dry_run' nexus scripts tests ir_eval`,
then inspected Python AST calls and imported aliases. No renamed import alias
was found. No direct caller was found in `ir_eval/`, genesis, or Retrograde.
There are 149 direct symbol call sites and one higher-order entry-point dispatch,
grouped by identical anchor/clock expression below. Shared dictionaries are
expanded for clock-bearing keys, including `kwargs` in composition and
communication tests; membership `sections` carries settings only. Wrappers
in production resolver/audit forward their optional parameters. Every stored
clock lookup is `load_anchor_world_time(session, anchor_chunk_id=...)` at
`resolver.py:548-550`, and every row reaches the refusal at 551-555.

**Incomplete at STOP:** production provenance was traced, but the detailed
fixture provenance and None-possibility for every variable-valued test anchor
has not been fully verified. Those rows record the actual expression and
shared refusal without claiming a complete fixture proof. This inventory must
be completed before a PR, as item 3 requires.

| Caller (Current Lines) | Entry Point | Anchor Source; Can Be None? | Effective Clock | Refusal or Clock Proof |
| --- | --- | --- | --- | --- |
| `nexus/agents/lore/utils/turn_cycle.py:776` | `resolve_dry_run` | target chunk, else max playable id (887-915); yes in pre-playable/empty state | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `nexus/agents/orrery/audit.py:579` | `hydrate_world_state` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `world_time_override` | explicit override; hydration refuses if override and stored lookup are both None |
| `nexus/agents/orrery/coverage.py:420` | `explain_dry_run` | each supplied `Sequence[int]` member (373-398, 419); no under its typed contract | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `nexus/agents/orrery/resolver.py:2436` | `hydrate_world_state` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `world_time_override` | explicit override; hydration refuses if override and stored lookup are both None |
| `nexus/api/orrery_dev_endpoints.py:456` | `explain_dry_run` | request anchor, else max playable id (450-454, 282-294); yes for empty state | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `scripts/orrery_sample.py:682` | `hydrate_world_state` | integer `sample_anchor` parameter (663-670); no under its typed contract | `world_time_override` | explicit override; hydration refuses if override and stored lookup are both None |
| `scripts/qa_shift/travel_reachability.py:424` | `hydrate_world_state` | explicit anchor, else max playable id (417-421); default absence raises (298-300) | stored anchor clock (`world_time_override=None`) | default anchor refusal, then shared hydration clock refusal |
| `tests/pg_fixtures.py:2181` | `resolve_dry_run` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_api/test_orrery_dev_endpoints.py:247` | `resolve_dry_run` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_connection_lifecycle.py:136` | `resolve_dry_run` | `chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_live_gate_clones_pg.py:115` | `resolve_dry_run` | `story.anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_lore/test_recent_orrery_rulings_pg.py:117` | `resolve_dry_run` | `tick_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_ambient.py:168` | `resolve_dry_run` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_card_identity.py:141` | `resolve_dry_run` | `anchor (shared `{key + '_settings': config[value] for key, value in {'sunhelm': 'sunhelm', 'selection': 'selection', 'habituation': 'habituation', 'package_selection': 'package_selection', 'project': 'projects', 'epistemics': 'epistemics', 'fanout': 'fanout', 'contagion': 'contagion', 'weather': 'weather', 'mood': 'mood', 'composition': 'composition'}.items()}`)`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_character_experiences_pg.py:245` | `resolve_dry_run` | `parent_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_birth_coverage_pg.py:291` | `resolve_dry_run` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption.py:161,183` | `hydrate_world_state` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:588,607` | `explain_dry_run` | `drain_chunk`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:231,356` | `hydrate_world_state` | `chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:439` | `hydrate_world_state` | `drain_chunk`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:499` | `hydrate_world_state` | `head_anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:492` | `hydrate_world_state` | `historical_anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_claim_consumption_live.py:580,599` | `resolve_dry_run` | `drain_chunk`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_communication_graph_live.py:707` | `explain_dry_run` | `None (shared `kwargs`)`; yes | `WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_communication_graph_live.py:706` | `resolve_dry_run` | `None (shared `kwargs`)`; yes | `WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_composition_sources_live.py:398,464` | `explain_dry_run` | `None (shared `kwargs`)`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_composition_sources_live.py:327` | `hydrate_world_state` | `None`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_composition_sources_live.py:600` | `resolve_dry_run` | `None`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_composition_sources_live.py:397,463` | `resolve_dry_run` | `None (shared `kwargs`)`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_epistemics.py:905,977` | `hydrate_world_state` | `anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_event_sources_pg.py:158` | `hydrate_world_state` | `anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_evidence.py:512` | `explain_dry_run` | `None`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_faction_membership_roles_pg.py:251` | `explain_dry_run` | `None (shared `sections`)`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_faction_membership_roles_pg.py:131,146,165,173` | `hydrate_world_state` | `None`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_faction_membership_roles_pg.py:239` | `resolve_dry_run` | `None (shared `sections`)`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_faction_project_contexts_live.py:751` | `explain_dry_run` | `chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_faction_project_contexts_live.py:419` | `hydrate_world_state` | `int(db['chunk_id'])`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_faction_project_contexts_live.py:744` | `resolve_dry_run` | `chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_faction_project_contexts_live.py:724,725` | `resolve_dry_run` | `chunk_id (shared `kwargs`)`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_faction_project_contexts_live.py:385,430,479,493,524,571,585,623` | `resolve_dry_run` | `int(db['chunk_id'])`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_live_cycle.py:211` | `resolve_dry_run` | `anchor_chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_narration_job_fencing_pg.py:190` | `resolve_dry_run` | `chunk_id`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_need_absence_pg.py:132` | `resolve_dry_run` | `departing`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_need_absence_pg.py:118` | `resolve_dry_run` | `returning`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_orbit_distance_live.py:176` | `hydrate_world_state` | `None`; yes | `WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_orbit_distance_parity.py:81` | `explain_dry_run` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_orbit_distance_parity.py:75` | `resolve_dry_run` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_package_selection.py:284` | `resolve_dry_run` | `4242`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_pair_tag_substrate.py:156,184,227,300` | `hydrate_world_state` | `None`; yes | `STORY_WORLD_TIME` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_polymorphic_patron_live.py:222` | `resolve_dry_run` | `db['chunk']`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_recall_disclosure_pg.py:1115` | `resolve_dry_run` | `anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_recruit_ally_projects.py:977,1023` | `resolve_dry_run` | `anchors[0]`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_resolver.py:2856` | `explain_dry_run` | `100`; no (integer literal) | `override_world_time` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_resolver.py:2795` | `explain_dry_run` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_resolver.py:1328,1449,1465,1539,1579,1605,1642,1675,1712,1758` | `hydrate_world_state` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_resolver.py:2849` | `resolve_dry_run` | `100`; no (integer literal) | `override_world_time` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_resolver.py:70,96,523,539,553,670,685,707,730,753,774,806,835,862,887,923,966,993,1011,1037,1079,1110,1143,1183,1230,1292,1364,1390,1398,1771,1806,1838,1877,1896,1927,1976,2037,2067,2124,2392,2607,2613,2788,3067,3160,3195,3234,3280,3310,3372,3410,3445,3489,3517` | `resolve_dry_run` | `100`; no (integer literal) | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_retrograde_projects_live.py:1020` | `resolve_dry_run` | `advance_chunk`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_routine_clock_required_pg.py:70` | `all three via entry_point` | `anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_routine_clock_required_pg.py:173` | `hydrate_world_state` | `anchor`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_orrery/test_routine_clock_required_pg.py:178` | `hydrate_world_state` | `selected_anchor`; caller-supplied; optional values reach the guard | `end` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_stage2a_status_live.py:587` | `hydrate_world_state` | `chunk_id`; caller-supplied; optional values reach the guard | `datetime(2073, 8, 1, tzinfo=timezone.utc)` | explicit override; hydration refuses if override and stored lookup are both None |
| `tests/test_orrery/test_weather_live.py:254,260` | `hydrate_world_state` | `int(anchor['chunk_id'])`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |
| `tests/test_player_identity_consumers_pg.py:537,575` | `resolve_dry_run` | `fixture['chunk_id']`; caller-supplied; optional values reach the guard | `stored anchor clock` | shared hydration refuses None before entity/tag/routine reads; no alternate clock |

### Import and Alias Sites

- `nexus/agents/lore/utils/turn_cycle.py:56` imports `resolve_dry_run`
- `nexus/agents/lore/utils/turn_cycle.py:89` imports `resolve_dry_run`
- `nexus/agents/orrery/audit.py:62` imports `hydrate_world_state`
- `nexus/agents/orrery/coverage.py:34` imports `explain_dry_run`
- `nexus/api/orrery_dev_endpoints.py:26` imports `explain_dry_run`
- `scripts/orrery_sample.py:23` imports `hydrate_world_state`
- `scripts/qa_shift/travel_reachability.py:37` imports `hydrate_world_state`
- `tests/pg_fixtures.py:2169` imports `resolve_dry_run`
- `tests/test_api/test_orrery_dev_endpoints.py:50` imports `resolve_dry_run`
- `tests/test_connection_lifecycle.py:97` imports `resolve_dry_run`
- `tests/test_live_gate_clones_pg.py:29` imports `resolve_dry_run`
- `tests/test_lore/test_recent_orrery_rulings_pg.py:24` imports `resolve_dry_run`
- `tests/test_orrery/test_ambient.py:20` imports `resolve_dry_run`
- `tests/test_orrery/test_card_identity.py:27` imports `resolve_dry_run`
- `tests/test_orrery/test_character_experiences_pg.py:53` imports `resolve_dry_run`
- `tests/test_orrery/test_claim_birth_coverage_pg.py:27` imports `resolve_dry_run`
- `tests/test_orrery/test_claim_consumption.py:5` imports `hydrate_world_state`
- `tests/test_orrery/test_claim_consumption_live.py:13` imports `explain_dry_run`
- `tests/test_orrery/test_claim_consumption_live.py:22` imports `hydrate_world_state`
- `tests/test_orrery/test_claim_consumption_live.py:22` imports `resolve_dry_run`
- `tests/test_orrery/test_communication_graph_live.py:14` imports `explain_dry_run`
- `tests/test_orrery/test_communication_graph_live.py:21` imports `resolve_dry_run`
- `tests/test_orrery/test_composition_sources_live.py:12` imports `explain_dry_run`
- `tests/test_orrery/test_composition_sources_live.py:14` imports `hydrate_world_state`
- `tests/test_orrery/test_composition_sources_live.py:14` imports `resolve_dry_run`
- `tests/test_orrery/test_epistemics.py:27` imports `hydrate_world_state`
- `tests/test_orrery/test_event_sources_pg.py:20` imports `hydrate_world_state`
- `tests/test_orrery/test_evidence.py:458` imports `explain_dry_run`
- `tests/test_orrery/test_faction_membership_roles_pg.py:22` imports `explain_dry_run`
- `tests/test_orrery/test_faction_membership_roles_pg.py:23` imports `hydrate_world_state`
- `tests/test_orrery/test_faction_membership_roles_pg.py:23` imports `resolve_dry_run`
- `tests/test_orrery/test_faction_project_contexts_live.py:14` imports `explain_dry_run`
- `tests/test_orrery/test_faction_project_contexts_live.py:21` imports `hydrate_world_state`
- `tests/test_orrery/test_faction_project_contexts_live.py:21` imports `resolve_dry_run`
- `tests/test_orrery/test_live_cycle.py:40` imports `resolve_dry_run`
- `tests/test_orrery/test_narration_job_fencing_pg.py:25` imports `resolve_dry_run`
- `tests/test_orrery/test_need_absence_pg.py:19` imports `resolve_dry_run`
- `tests/test_orrery/test_orbit_distance_live.py:21` imports `hydrate_world_state`
- `tests/test_orrery/test_orbit_distance_parity.py:7` imports `explain_dry_run`
- `tests/test_orrery/test_orbit_distance_parity.py:8` imports `resolve_dry_run`
- `tests/test_orrery/test_package_selection.py:237` imports `resolve_dry_run`
- `tests/test_orrery/test_pair_tag_substrate.py:21` imports `hydrate_world_state`
- `tests/test_orrery/test_polymorphic_patron_live.py:19` imports `resolve_dry_run`
- `tests/test_orrery/test_recall_disclosure_pg.py:39` imports `resolve_dry_run`
- `tests/test_orrery/test_recruit_ally_projects.py:823` imports `resolve_dry_run`
- `tests/test_orrery/test_resolver.py:11` imports `explain_dry_run`
- `tests/test_orrery/test_resolver.py:12` imports `hydrate_world_state`
- `tests/test_orrery/test_resolver.py:12` imports `resolve_dry_run`
- `tests/test_orrery/test_retrograde_projects_live.py:26` imports `resolve_dry_run`
- `tests/test_orrery/test_routine_clock_required_pg.py:21` imports `explain_dry_run`
- `tests/test_orrery/test_routine_clock_required_pg.py:22` imports `hydrate_world_state`
- `tests/test_orrery/test_routine_clock_required_pg.py:22` imports `resolve_dry_run`
- `tests/test_orrery/test_stage2a_status_live.py:22` imports `hydrate_world_state`
- `tests/test_orrery/test_weather_live.py:12` imports `hydrate_world_state`
- `tests/test_player_identity_consumers_pg.py:35` imports `resolve_dry_run`

## Exact Gate Commands and Verbatim Tails

Commands below were executed from this worktree by the scratch `run_gate.py`
wrapper with `subprocess.run(..., timeout=590)`. The wrapper stores the full
log and exact expanded argv under the order scratch directory; its exit-status
annotation is separate from the pytest tail. No gate ran with live LLM opt-in.

### postgres

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 49%]
........................................................................ [ 66%]
........................................................................ [ 82%]
........................................................................ [ 99%]
...                                                                      [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 17 targets: postgres, qa640_783s6_* x11, qa640_membership_roles_*, qa640_pair_tag_substrate_*, qa885_composition_sources_*, qa885_evidence_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
435 passed in 26.68s
```

### offline-other

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
................s..s.............................ssss.................ss [ 94%]
sss...................................sssss...................sss....... [ 97%]
.......ssss.....................................................ssssssss [ 99%]
sssssssssssssssssss                                                      [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2732 passed, 457 skipped, 8 warnings in 447.46s (0:07:27)
```

### offline-api-orrery

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```text
..............ssssssss.................................................. [ 80%]
...................................s.................ssss...s........... [ 83%]
.......................................sssssssssssssssssssssssss........ [ 86%]
................................................sssssssssssss.s......s.. [ 88%]
.................s....sssssssssssssssssssss.....ss...............ssss... [ 91%]
...................................ss....sssssssssss.................... [ 94%]
.................................................................sssssss [ 97%]
ssss........................ssssssssssss.............sssss..........s.   [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1833 passed, 757 skipped, 7 warnings in 38.73s
```

### reachability

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
......................................................                   [100%]
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.62s
```

### black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
All done! ✨ 🍰 ✨
9 files would be left unchanged.
```

### flake8

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
nexus/agents/orrery/resolver.py:1355:89: E501 line too long (133 > 88 characters)
tests/test_orrery/test_routine_clock_required_pg.py:120:89: E501 line too long (90 > 88 characters)
```

### mypy

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
nexus/agents/orrery/resolver.py:2755: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryJointBeat], int | None]"; expected "Callable[[OrreryJointBeat], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/resolver.py:2755: error: Value of type variable "SupportsRichComparisonT" of "min" cannot be "int | None"  [type-var]
nexus/agents/orrery/resolver.py:2755: error: Incompatible return value type (got "int | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
nexus/agents/orrery/resolver.py:2823: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryResolutionDraft], float | None]"; expected "Callable[[OrreryResolutionDraft], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/resolver.py:2823: error: Incompatible return value type (got "float | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
nexus/agents/orrery/resolver.py:2841: error: Argument 1 to "get" of "Mapping" has incompatible type "int | None"; expected "int"  [arg-type]
tests/test_orrery/test_pair_tag_substrate.py:114: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_pair_tag_substrate.py:283: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_substrate.py:1116: error: Dict entry 1 has incompatible type "str": "int"; expected "Slot": "Any"  [dict-item]
tests/test_orrery/test_substrate.py:1117: error: Dict entry 0 has incompatible type "str": "int"; expected "Slot": "Any"  [dict-item]
tests/test_orrery/test_composition_sources_live.py:397: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:397: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:397: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:397: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "bool | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:398: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:398: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:398: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:398: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "WorldStateOverrides | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:463: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:463: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:463: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:463: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "bool | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:464: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:464: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:464: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:464: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | datetime | None]"; expected "WorldStateOverrides | None"  [arg-type]
tests/test_orrery/test_resolver.py:245: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/test_orrery/test_resolver.py:246: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/test_orrery/test_resolver.py:247: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Found 26 errors in 4 files (checked 9 source files)
```

### mypy-baseline

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --shadow-file nexus/agents/orrery/substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_0.py --shadow-file nexus/agents/orrery/resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_1.py --shadow-file tests/test_orrery/test_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_2.py --shadow-file tests/test_orrery/test_resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_3.py --shadow-file tests/test_orrery/test_composition_sources_live.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_4.py --shadow-file tests/test_orrery/test_faction_membership_roles_pg.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_5.py --shadow-file tests/test_orrery/test_pair_tag_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_6.py --shadow-file tests/test_orrery/test_evidence.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_7.py nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
nexus/agents/orrery/resolver.py:2747: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryJointBeat], int | None]"; expected "Callable[[OrreryJointBeat], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/resolver.py:2747: error: Value of type variable "SupportsRichComparisonT" of "min" cannot be "int | None"  [type-var]
nexus/agents/orrery/resolver.py:2747: error: Incompatible return value type (got "int | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
nexus/agents/orrery/resolver.py:2815: error: Argument "key" to "sorted" has incompatible type "Callable[[OrreryResolutionDraft], float | None]"; expected "Callable[[OrreryResolutionDraft], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
nexus/agents/orrery/resolver.py:2815: error: Incompatible return value type (got "float | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
nexus/agents/orrery/resolver.py:2833: error: Argument 1 to "get" of "Mapping" has incompatible type "int | None"; expected "int"  [arg-type]
tests/test_orrery/test_pair_tag_substrate.py:105: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_pair_tag_substrate.py:271: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_composition_sources_live.py:395: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:395: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:395: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:395: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "bool | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:396: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:396: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:396: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:396: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "WorldStateOverrides | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:460: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:460: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:460: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:460: error: Argument 3 to "resolve_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "bool | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:461: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:461: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "int"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:461: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "datetime | None"  [arg-type]
tests/test_orrery/test_composition_sources_live.py:461: error: Argument 3 to "explain_dry_run" has incompatible type "**dict[str, dict[str, int] | int | None]"; expected "WorldStateOverrides | None"  [arg-type]
tests/test_orrery/test_substrate.py:1064: error: Dict entry 1 has incompatible type "str": "int"; expected "Slot": "Any"  [dict-item]
tests/test_orrery/test_substrate.py:1065: error: Dict entry 0 has incompatible type "str": "int"; expected "Slot": "Any"  [dict-item]
tests/test_orrery/test_resolver.py:245: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/test_orrery/test_resolver.py:246: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/test_orrery/test_resolver.py:247: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Found 26 errors in 4 files (checked 8 source files)
```

### flake8-final

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
nexus/agents/orrery/resolver.py:1355:89: E501 line too long (133 > 88 characters)
```

### flake8-baseline

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_1.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/baseline_1.py:1347:89: E501 line too long (133 > 88 characters)
```

### black-final

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
All done! ✨ 🍰 ✨
9 files would be left unchanged.
```

### Earlier PostgreSQL Runs

The access preflight used:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_faction_membership_roles_pg.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_membership_roles_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
5 passed in 2.05s
```

The initial full proof used the identical `postgres` command above, prefixed by
`perl -e 'alarm 590; exec @ARGV'`. Its selected verbatim failure and terminal tail:

```text
E               AssertionError: seed_protagonist would reset base_timestamp from 2073-08-01 12:00:00+00:00 to 2100-01-01 00:00:00+00:00; run it before seed_story_clock, or pass the clock already set

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 17 targets: postgres, qa640_783s6_* x11, qa640_membership_roles_*, qa640_pair_tag_substrate_*, qa885_composition_sources_*, qa885_evidence_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
1 failed, 434 passed in 26.75s
```

Import preflight:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/783-routine-clock-required/nexus/__init__.py
```

## Landing Notes and Open Questions

No migration, fleet application, prompt, UI, package, or tunable change. Do not
land this stopped slice yet. After eventual landing, restart the owner's gateway
by name with `nexus restart gateway`; no client rebuild. The coordinator runs the
whole-tree PostgreSQL gate at the final commit. Keep issue #783 open. No PR was
created, no branch pushed, and no merge performed.

Coordinator: should the baseline mypy/flake8 failures receive an explicit gate
exception for this frozen order, or be repaired by a separate order before
783-S6 resumes? Finish test-anchor provenance in item 3 before opening its PR.
The host exposes GPT-6 as the model family but no exact Sol/Astra runtime ID;
commit/report signatures therefore name that exposed family without guessing.

Codex — GPT-6 (exact runtime variant not exposed)

# 783-S6 Verification Record

Status: **Required Proof Passed; Static Gate Adds No Diagnostics**. The supplemental
caller-audit probe has three out-of-scope fixture errors, reported below for
coordinator triage under the common rules. No merge authorized or performed.

Inspected rebased implementation: `92118d71`. Final gates ran at `ab598bced1487745ca6cbdb68584e6194d0bde4e`.
Latest fetched `origin/main`: `36ec0b2601811a0f89972542352e36c272be90c7`. The existing commit sequence was replayed
without squashing or amending. Original c357ef46 and 711b7690 remain retained by
local ref `refs/archive/783-S6-stop-report`; their rebased equivalents are
92118d71 and 03328a45.
`git fetch origin main` and `git rebase origin/main` ran from this worktree:

```text
From https://github.com/pythagorakase/nexus
 * branch              main       -> FETCH_HEAD
Successfully rebased and updated refs/heads/claude/783-routine-clock-required.
```

LG-Q1 applies verbatim: **B. Release all three now**. This is the 783-R11 doctrine
fix. Missing world time is an error, never due; present-clock schedule behavior
is unchanged. This slice neither implements the writers nor reopens Q9.
The 2026-10-01 common-rules addition and the coordinator's resume instruction
resolve the earlier static-check stop: baseline diagnostics are reported, not
fixed, and the gate is no new diagnostics. Resume edits are evidence only; upstream #1063 changes were preserved.

## Behavior and Story-Opening Trace

`substrate.py:1807-1808` refuses clockless schedule evaluation before any empty,
partial, weekday, or hour branch. `routine_anchor_due` keeps its unbound actor,
missing anchor, none-policy and nomadic-policy false results at :1685-1692.
`resolver.py:548-555` chooses the explicit override or stored anchor clock, then
refuses None before entity, tag, routine, weather or composition hydration.
`load_anchor_world_time` remains optional at :2912-2934 for non-resolver readers.
A supplied clock still supports an anchorless what-if.

The following indirect entries were traced in addition to every direct call in
the caller table. No bootstrap/genesis/Retrograde module directly calls any of
the three entry points. No production story-opening path was found that reaches
hydration without an anchor clock or an explicit override.

| Story Entry | Indirect Route | Anchor; None Possibility | Clock and Refusal/Proof |
| --- | --- | --- | --- |
| Gateway bootstrap / first narrated opening | narrative.py:991-1026 → narrative_generation.py:261-280 → generate_bootstrap_narrative (:641-815) → LOGON | parent 0 selects existing dedicated bootstrap flow; no Orrery hydration | No resolver clock is consumed. Calls LOGON directly with seed context; this branch predates this change. No new skip or empty-proposal bypass was added |
| Wizard genesis / cold-start Retrograde | wizard_chat.py:1355-1360,1393-1398 → perform_transition_with_retrograde (new_story_flow.py:451,500-655) → dedicated generate/persist/embed Retrograde history → mapper.perform_transition | No turn-cycle hydration entry; pre-playable prologue is excluded by reconstruction.py:28-48 | Wizard requires base_timestamp. Dedicated Retrograde generation/persistence is independent of dry-run hydration. Neither the enabled Retrograde path nor existing disabled/TEST paths call these entry points |
| First continuation after accepting the opening | narrative_generation.py:287-318 → LORE.process_turn (lore.py:329,358-365,394) → TurnCycleManager.resolve_orrery (:776) → resolve_dry_run → hydration | Explicit parent passed as target_chunk_id; ordinary accepted parent is an integer. Selector can otherwise return None on a pre-playable/empty slot | commit_handler_sync.py:577-592 inserts parent metadata and requires its trigger-authored clock before acceptance. No override is forwarded. Missing/damaged metadata or a NULL clock now refuses |
| User CLI new-story / continuation | cli.py:2653,2850 → wizard transition HTTP; cli.py:2139,2923 → narrative/continue HTTP | Uses the same routes above | Same bootstrap/genesis/accepted-parent proof; no separate direct resolver entry |
| Standalone LORE diagnostic / interactive driver | lore.py:831,869 → process_turn → resolve_orrery | No explicit parent; max playable can be None | process_turn docstring (:344-347) identifies standalone diagnostics and requires a distinct canonical attempt UUID. This diagnostic driver does not create/persist a story or accept an opening; clockless use refuses. It is not a second gateway/bootstrap implementation |

Both empty-slot selectors were exercised on a real disposable clone by
`test_turn_and_dev_anchor_selection_can_return_none`. All three clockless entry
points, absent metadata and NULL clocks were exercised with real SQLAlchemy
sessions and rolled-back damage. Clocked routine boundaries and explicit,
anchorless overrides also passed. No provider was called by these new cases.

## Read-Only Schema Evidence

The previous run at original implementation c357ef46 read the canonical schema
through `tests.pg_fixtures.connect('NEXUS_template')`, with
`conn.set_session(readonly=True)` before reads, then rolled back. This historical
schema evidence is retained; no direct schema probe was repeated on resume.
Disposable fixtures read the template to create their clones; no save/template
write is authorized or performed.

```sql
SHOW transaction_read_only;
SELECT table_name, column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='chunk_metadata'
  AND column_name='world_time';
```

```text
transaction_read_only=on
chunk_metadata | world_time | YES | timestamp with time zone
```

## Complete Caller Inventory

Search command:

```sh
rg -n 'hydrate_world_state|resolve_dry_run|explain_dry_run' nexus scripts tests ir_eval
```

Python AST calls/imports were cross-checked against the table with the scratch
`complete_inventory.py`: **149 direct symbol call sites, one higher-order
entry_point dispatch, 55 imported symbols, no renamed imports**. An exact set
comparison verifies every direct file:line/function appears below. No direct
caller occurs under `ir_eval/`. The ENTRY_POINTS tuple at
`test_routine_clock_required_pg.py:38` supplies the higher-order dispatcher at
:70, including empty/damaged clocks and the two empty-selector helper calls at
:197-198. The coverage test's monkeypatch at
`test_coverage_accounting.py:101` substitutes a lambda; it is not a hydration
call. Shared dictionaries and settings comprehensions are included below.

For every real stored-clock row, the effective clock is read through
`load_anchor_world_time(session, anchor_chunk_id=...)` at resolver.py:548-550.
An integer anchor alone never proves a present clock; missing metadata/NULL
clocks take the shared refusal at :551-555. Fixture proof below describes the
actual setup, not an implicit promise by that integer. Existing FakeSession
unit tests are labeled as such; no new mocks were introduced.

| Caller (Current Lines) | Entry Point | Anchor Source; Can Be None? | Effective Clock | Refusal or Clock Proof |
| --- | --- | --- | --- | --- |
| `nexus/agents/lore/utils/turn_cycle.py:776` | `resolve_dry_run` | target_chunk_id, else max playable ID (:887-915); yes in empty/pre-playable state | stored anchor clock | Stored parent clock; accepted bootstrap commit requires it at commit_handler_sync.py:577-592. Empty/missing/NULL clocks refuse at resolver.py:551-555 |
| `nexus/agents/orrery/audit.py:579` | `hydrate_world_state` | Optional caller parameter (:539); yes | world_time_override | Override first, else anchor metadata; shared refusal at resolver.py:551-555 |
| `nexus/agents/orrery/coverage.py:420` | `explain_dry_run` | each Sequence[int] member (:373,419); no under typed contract; empty sequence raises (:397-398) | stored anchor clock | No override; anchor metadata clock is not guaranteed by an integer. Shared refusal for missing/NULL metadata |
| `nexus/agents/orrery/resolver.py:2436` | `hydrate_world_state` | Optional caller parameter (:2403); yes | world_time_override | Override first, else anchor metadata; shared refusal at :551-555 |
| `nexus/api/orrery_dev_endpoints.py:456` | `explain_dry_run` | request anchor, else max playable ID (:450-454,282-294); yes | stored anchor clock | No hydration override; stored clock must exist. Only OverrideValidationError is caught (:475-478), so clock refusal propagates |
| `scripts/orrery_sample.py:682` | `hydrate_world_state` | sample_anchor integer argument (:663-670); no under typed contract | world_time_override | Optional what-if override, else metadata; shared refusal if neither exists |
| `scripts/qa_shift/travel_reachability.py:424` | `hydrate_world_state` | explicit integer or default max playable (:417-421); no after default absence raises (:298-300) | stored anchor clock (`world_time_override=None`) | No override; integer alone does not prove metadata. Shared missing-clock refusal |
| `tests/pg_fixtures.py:2181` | `resolve_dry_run` | int parameter from seed_pending_turn parent (:2335-2341); no; only non-bootstrap continuations enter | stored anchor clock | Stored accepted parent clock; seed_played_story (:2501) accepts bootstrap/continuations through the real commit, which requires the clock |
| `tests/test_api/test_orrery_dev_endpoints.py:247` | `resolve_dry_run` | max playable SQL (:240-246); query can yield None; seeded_story uses seed_played_story (:137) | stored anchor clock | No override; accepted fixture chunks have clocks. If helper is used on an empty/damaged clone, shared refusal |
| `tests/test_connection_lifecycle.py:136` | `resolve_dry_run` | insert RETURNING id (:106-107); no after successful insert; isolated two-cluster fixture (:1-5) | stored anchor clock | Metadata inserted, then world_time explicitly updated to 2196-07-06T23:00Z (:109-117); stored clock |
| `tests/test_live_gate_clones_pg.py:115` | `resolve_dry_run` | story.anchor_chunk_id from seed_live_cycle_story (:107; test_live_cycle.py:111,167); no | stored anchor clock | seed_played_story accepted clocks; no override |
| `tests/test_lore/test_recent_orrery_rulings_pg.py:117` | `resolve_dry_run` | int tick parameter from chunk_ids[1..3] (:234-257), inserted by _insert_accepted_chunk_after_rollback_gap (:44-81); no | stored anchor clock | NO metadata insert in that helper, no override: shared refusal. Confirmed three fixture errors in resume-rulings-probe; deferred to coordinator |
| `tests/test_orrery/test_ambient.py:168` | `resolve_dry_run` | _resolve int parameter defaults to 100 (:161); all supplied anchors are integers; no | stored anchor clock | AmbientFakeSession inherits FakeSession clock behavior (test_resolver.py:222-226,445-447); present fixture clock, no override |
| `tests/test_orrery/test_card_identity.py:141` | `resolve_dry_run` | max narrative ID (:138-140) in data-bearing save_04 corpus clone (:114); yes if corpus empty | stored anchor clock; **settings comprehension (:145-160) contains no clock/anchor keys | No override; corpus clocks are not guaranteed by max(id). Shared refusal for absent/NULL metadata |
| `tests/test_orrery/test_character_experiences_pg.py:245` | `resolve_dry_run` | _resolve_sleep int parent parameter (:238), from _insert_chunk (:151-168); no | stored anchor clock | Helper inserts metadata and explicitly sets 2196-07-06T23:00Z (:165-168); stored clock |
| `tests/test_orrery/test_claim_birth_coverage_pg.py:291` | `resolve_dry_run` | _resolve int parameter (:287), callers use _insert_chunk (:159-181); no | stored anchor clock | Metadata trigger stamps base 2200-01-01T00:00Z plus primary deltas; _seed_world sets base (:189-195); shared refusal if damaged |
| `tests/test_orrery/test_claim_consumption.py:161,183` | `hydrate_world_state` | literal 100; no | stored anchor clock | FakeSession supplies default 2073-10-31T12:00Z (:test_resolver.py:222-226,445-447); no override |
| `tests/test_orrery/test_claim_consumption_live.py:588,607` | `explain_dry_run` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_claim_consumption_live.py:231,356` | `hydrate_world_state` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_claim_consumption_live.py:439` | `hydrate_world_state` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_claim_consumption_live.py:499` | `hydrate_world_state` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_claim_consumption_live.py:492` | `hydrate_world_state` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_claim_consumption_live.py:580,599` | `resolve_dry_run` | integer returned by claim_accounts_test_support._insert_chunk (:270-308); no; chunk_id, drain_chunk, historical_anchor and head_anchor are separate returned IDs | stored anchor clock | consumption_slot seeds WORLD_TIME (:58); helper inserts metadata, reads world_time and asserts non-NULL (:304-308); stored clock |
| `tests/test_orrery/test_communication_graph_live.py:707` | `explain_dry_run` | shared kwargs (:699-705) explicitly anchor_chunk_id=None; yes | WORLD_TIME | kwargs explicitly supplies WORLD_TIME (:702), a timezone-aware datetime (:36); fixture seeds same clock (:51) |
| `tests/test_orrery/test_communication_graph_live.py:706` | `resolve_dry_run` | shared kwargs (:699-705) explicitly anchor_chunk_id=None; yes | WORLD_TIME | kwargs explicitly supplies WORLD_TIME (:702), a timezone-aware datetime (:36); fixture seeds same clock (:51) |
| `tests/test_orrery/test_composition_sources_live.py:398,464` | `explain_dry_run` | explicit None, including shared kwargs (:391-396,457-462); yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:56), explicitly supplied (also in kwargs); composition clone seeds same clock (:155) |
| `tests/test_orrery/test_composition_sources_live.py:327` | `hydrate_world_state` | explicit None, including shared kwargs (:391-396,457-462); yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:56), explicitly supplied (also in kwargs); composition clone seeds same clock (:155) |
| `tests/test_orrery/test_composition_sources_live.py:600` | `resolve_dry_run` | explicit None, including shared kwargs (:391-396,457-462); yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:56), explicitly supplied (also in kwargs); composition clone seeds same clock (:155) |
| `tests/test_orrery/test_composition_sources_live.py:397,463` | `resolve_dry_run` | explicit None, including shared kwargs (:391-396,457-462); yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:56), explicitly supplied (also in kwargs); composition clone seeds same clock (:155) |
| `tests/test_orrery/test_epistemics.py:905,977` | `hydrate_world_state` | max ID cast to int after equality to seeded fixture ID (:845-849,937-941); no on successful fixture | stored anchor clock | epistemics_clone seed_story_clock(STORY_CLOCK) (:118) asserts its stored clock through the shared seed helper; no override |
| `tests/test_orrery/test_event_sources_pg.py:158` | `hydrate_world_state` | _insert_prologue_chunk + _ensure_prologue_metadata (:81-82); no after successful insert | stored anchor clock | seed_protagonist sets base (:56); _ensure_prologue_metadata (retrograde_persistence.py:2561-2585) inserts zero-delta retrograde metadata; trigger stamps base clock; no override |
| `tests/test_orrery/test_evidence.py:512` | `explain_dry_run` | explicit None (:515); yes | STORY_WORLD_TIME | STORY_WORLD_TIME timezone-aware datetime (:466), seeded before protagonist (:467-469), supplied explicitly (:516) |
| `tests/test_orrery/test_faction_membership_roles_pg.py:251` | `explain_dry_run` | explicit None; sections dictionary (:197-216) contains configuration only; yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:40), seeded (:51), supplied explicitly to all entry points, outside sections |
| `tests/test_orrery/test_faction_membership_roles_pg.py:131,146,165,173` | `hydrate_world_state` | explicit None; sections dictionary (:197-216) contains configuration only; yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:40), seeded (:51), supplied explicitly to all entry points, outside sections |
| `tests/test_orrery/test_faction_membership_roles_pg.py:239` | `resolve_dry_run` | explicit None; sections dictionary (:197-216) contains configuration only; yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:40), seeded (:51), supplied explicitly to all entry points, outside sections |
| `tests/test_orrery/test_faction_project_contexts_live.py:751` | `explain_dry_run` | db['chunk_id'] from faction_context_clone seed_story_clock (:187,236), cast to int locally; kwargs (:719-723) forwards same ID; no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:187), asserted by shared seed helper; kwargs contains no override |
| `tests/test_orrery/test_faction_project_contexts_live.py:419` | `hydrate_world_state` | db['chunk_id'] from faction_context_clone seed_story_clock (:187,236), cast to int locally; kwargs (:719-723) forwards same ID; no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:187), asserted by shared seed helper; kwargs contains no override |
| `tests/test_orrery/test_faction_project_contexts_live.py:744` | `resolve_dry_run` | db['chunk_id'] from faction_context_clone seed_story_clock (:187,236), cast to int locally; kwargs (:719-723) forwards same ID; no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:187), asserted by shared seed helper; kwargs contains no override |
| `tests/test_orrery/test_faction_project_contexts_live.py:724,725` | `resolve_dry_run` | db['chunk_id'] from faction_context_clone seed_story_clock (:187,236), cast to int locally; kwargs (:719-723) forwards same ID; no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:187), asserted by shared seed helper; kwargs contains no override |
| `tests/test_orrery/test_faction_project_contexts_live.py:385,430,479,493,524,571,585,623` | `resolve_dry_run` | db['chunk_id'] from faction_context_clone seed_story_clock (:187,236), cast to int locally; kwargs (:719-723) forwards same ID; no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:187), asserted by shared seed helper; kwargs contains no override |
| `tests/test_orrery/test_live_cycle.py:211` | `resolve_dry_run` | max ID cast to int and compared to story.anchor_chunk_id (:209-210); no | stored anchor clock | seed_live_cycle_story uses seed_played_story (:111,167), real accepted chunks with clocks; no override |
| `tests/test_orrery/test_narration_job_fencing_pg.py:190` | `resolve_dry_run` | _insert_chunk return (:152-163) used at :166; no | stored anchor clock | Helper inserts metadata and explicitly updates 2196-07-06T23:00Z (:154-160); stored clock |
| `tests/test_orrery/test_need_absence_pg.py:132` | `resolve_dry_run` | returning/departing from _chunk (:118,132; helper :43-66); no after successful insert | stored anchor clock | Helper explicitly updates clock to absent_at or absent_at + 1 hour (:55-60); stored clock |
| `tests/test_orrery/test_need_absence_pg.py:118` | `resolve_dry_run` | returning/departing from _chunk (:118,132; helper :43-66); no after successful insert | stored anchor clock | Helper explicitly updates clock to absent_at or absent_at + 1 hour (:55-60); stored clock |
| `tests/test_orrery/test_orbit_distance_live.py:176` | `hydrate_world_state` | explicit None; yes | WORLD_TIME | Explicit WORLD_TIME datetime (:27,180); fixture seeds same clock (:35) |
| `tests/test_orrery/test_orbit_distance_parity.py:81` | `explain_dry_run` | literal 100; no | stored anchor clock | _orbit_session returns FakeSession (:25); default present fixture clock (test_resolver.py:222-226,445-447); no override |
| `tests/test_orrery/test_orbit_distance_parity.py:75` | `resolve_dry_run` | literal 100; no | stored anchor clock | _orbit_session returns FakeSession (:25); default present fixture clock (test_resolver.py:222-226,445-447); no override |
| `tests/test_orrery/test_package_selection.py:284` | `resolve_dry_run` | literal 4242; no | stored anchor clock | FakeSession(max_chunk_id=4242) (:285-295) supplies present default clock (test_resolver.py:222-226,445-447); no override |
| `tests/test_orrery/test_pair_tag_substrate.py:156,184,227,300` | `hydrate_world_state` | explicit None; yes | STORY_WORLD_TIME | STORY_WORLD_TIME datetime (:42), seeded once in pair_tag_slot (:61), supplied explicitly at all four calls |
| `tests/test_orrery/test_polymorphic_patron_live.py:222` | `resolve_dry_run` | db['chunk'] from patron_circle_clone seed_story_clock (:81,115,143); no | stored anchor clock | STORY_WORLD_TIME stored by seed_story_clock (:81), asserted by shared helper; no override |
| `tests/test_orrery/test_recall_disclosure_pg.py:1115` | `resolve_dry_run` | anchor returned by _chunk (:982-987), integer; no | stored anchor clock | _chunk explicitly updates metadata world_time (:173-176) to base + 2 hours, base=2078-02-01T00:00Z (:980); no override |
| `tests/test_orrery/test_recruit_ally_projects.py:977,1023` | `resolve_dry_run` | anchors[0] from sample_anchor_ids (:833), len==35 asserted (:834); no | stored anchor clock | Corpus anchor metadata, no override; min world_time asserted non-NULL (:917-927) does not prove each row. Coverage/shared hydration refuses any missing individual clock |
| `tests/test_orrery/test_resolver.py:2856` | `explain_dry_run` | literal 100; no | override_world_time | Explicit override_world_time datetime (:2824); FakeSession stored anchor_world_time (:2823,2837); parity assertions prove override used |
| `tests/test_orrery/test_resolver.py:2795` | `explain_dry_run` | literal 100; no | stored anchor clock | Existing FakeSession SQL stub supplies default datetime (:222-226,445-447) or an explicit constructor datetime; parity override rows use override_world_time=:2824. No retained caller supplies world_time=None |
| `tests/test_orrery/test_resolver.py:1328,1449,1465,1539,1579,1605,1642,1675,1712,1758` | `hydrate_world_state` | literal 100; no | stored anchor clock | Existing FakeSession SQL stub supplies default datetime (:222-226,445-447) or an explicit constructor datetime; parity override rows use override_world_time=:2824. No retained caller supplies world_time=None |
| `tests/test_orrery/test_resolver.py:2849` | `resolve_dry_run` | literal 100; no | override_world_time | Explicit override_world_time datetime (:2824); FakeSession stored anchor_world_time (:2823,2837); parity assertions prove override used |
| `tests/test_orrery/test_resolver.py:70,96,523,539,553,670,685,707,730,753,774,806,835,862,887,923,966,993,1011,1037,1079,1110,1143,1183,1230,1292,1364,1390,1398,1771,1806,1838,1877,1896,1927,1976,2037,2067,2124,2392,2607,2613,2788,3067,3160,3195,3234,3280,3310,3372,3410,3445,3489,3517` | `resolve_dry_run` | literal 100; no | stored anchor clock | Existing FakeSession SQL stub supplies default datetime (:222-226,445-447) or an explicit constructor datetime; parity override rows use override_world_time=:2824. No retained caller supplies world_time=None |
| `tests/test_orrery/test_retrograde_projects_live.py:1020` | `resolve_dry_run` | advance_chunk from _fabricate_chunk(cur,due_time) (:1017-1019); no | stored anchor clock | _fabricate_chunk inserts metadata then explicitly updates world_time (:1411-1416); due_time comes from seeded project next_eligible_at_world_time; base seeded at :109 |
| `tests/test_orrery/test_routine_clock_required_pg.py:70` | `all three via entry_point` | optional helper anchor: None for empty clone/turn and dev selectors; seeded int after deleted/NULL metadata (:101-136); yes | stored anchor clock | Deliberate missing-clock refusal for all three functions in ENTRY_POINTS (:38); real SQL verifies damage, rollback verifies restoration |
| `tests/test_orrery/test_routine_clock_required_pg.py:173` | `hydrate_world_state` | seed_story_clock return (:148); no | stored anchor clock | Stored STORY_WORLD_TIME is asserted at :174; seed helper verifies exact metadata clock |
| `tests/test_orrery/test_routine_clock_required_pg.py:178` | `hydrate_world_state` | selected_anchor loop in (seeded anchor, None) (:177); yes | end | Explicit end datetime at 17:00 (:176,182); present even when anchor is None |
| `tests/test_orrery/test_stage2a_status_live.py:587` | `hydrate_world_state` | max narrative ID cast to int (:526-528) after stage2a clone seeds clock (:76); no | datetime(2073, 8, 1, tzinfo=timezone.utc) | Explicit datetime(2073,8,1,tzinfo=UTC) (:592), same WORLD_TIME seeded by fixture; override is present |
| `tests/test_orrery/test_weather_live.py:254,260` | `hydrate_world_state` | int(anchor['chunk_id']) from query with cm.world_time IS NOT NULL (:218-232); no on successful row | stored anchor clock | Non-NULL metadata clock selected in SQL (:225); seed clock 2088-06-01T12:00Z (:115,197-202); no override |
| `tests/test_player_identity_consumers_pg.py:537,575` | `resolve_dry_run` | fixture['chunk_id'] from _seed_consumer_save insert RETURNING id (:284-294,353); no | stored anchor clock | Metadata insert supplies _WORLD_TIME (:302-309); stored clock; missing-player test fails later for player identity, not clock |

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

## Pre-existing Diagnostics

Black passes all nine Python files. Flake8 reports the unchanged SQL literal in
resolver.py at branch :1355 versus main :1347 (E501, 133 > 88). Mypy with
`--explicit-package-bases` reports the coordinator-confirmed 26 pre-existing
errors in four files on both branch and main. None is repaired in this order.

| File | Branch Lines | origin/main Lines | Existing Diagnostics |
| --- | --- | --- | --- |
| resolver.py | 2755,2823,2841 | 2747,2815,2833 | 6 optional-value sorting/min/key errors |
| test_pair_tag_substrate.py | 114,283 | 105,271 | 2 optional fetchone tuple indexing errors |
| test_substrate.py | 1116,1117 | 1064,1065 | 2 string-key/Slot dictionary errors |
| test_composition_sources_live.py | 397,398,463,464 | 395,396,460,461 | 16 shared-kwargs argument errors (four existing expected types at each call) |

The composition diagnostics display `datetime` in the branch's inferred kwargs
union because the required explicit override was added; main's union lacks that
member. The diagnostic sites, expected types and error codes are the same,
and the coordinator expressly classified these 26 diagnostics as pre-existing
in the resume instruction. This textual union expansion is visible in the two
unabridged outputs below; the outputs are not claimed byte-identical.
The added PostgreSQL file has no mypy or flake8 diagnostic.

Main sources were extracted with `git show origin/main:<path>` into
`<scratch>/origin-main/<path>` for all eight pre-existing changed Python files.
Flake8 checks those files directly. Mypy's `--shadow-file` reads those exact
main bytes while preserving the same package names/import graph and sanctioned
`--explicit-package-bases` invocation. The new ninth file has no main version
and is checked on the branch. Both complete outputs follow, including tool
exit 1 for pre-existing diagnostics; the comparison gate passes.

## Exact Gate Commands and Verbatim Tails

All commands ran from this worktree with the shared interpreter. The scratch
run_gate.py wrapper runs subprocess.run(..., timeout=590), stores expanded argv
and full logs in this order's scratch directory, and waits for completion.
The PostgreSQL proof, both offline suites, reachability and static comparisons
were rerun after rebasing onto #1063 at the inspected HEAD above. The earlier
resume proof also passed at 711b7690 with 435 passed in 27.36s.
Live LLM opt-in was unset; only TEST is permitted. No gateway was launched here.

### Import Preflight

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/783-routine-clock-required/nexus/__init__.py
```

### PostgreSQL Proof (After Rebase)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/final-postgres-tmp tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
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
435 passed in 29.33s
```

### Offline Other (After Rebase)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/final-offline-other-tmp tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
.................................s..s.............................ssss.. [ 94%]
...............sssss...................................sssss............ [ 96%]
.......sss..............ssss............................................ [ 98%]
.........sssssssssssssssssssssssssss                                     [100%]
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
2732 passed, 474 skipped, 8 warnings in 431.83s (0:07:11)
```

### Offline API and Orrery (After Rebase)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/final-offline-api-tmp tests/test_api tests/test_orrery
```

```text
...............ssssssss................................................. [ 80%]
....................................s.................sssss...s......... [ 83%]
.........................................sssssssssssssssssssssssss...... [ 86%]
..................................................sssssssssssss.s......s [ 88%]
...................s....sssssssssssssssssssss.....ss...............ssss. [ 91%]
.....................................ss....sssssssssss.................. [ 94%]
...................................................................sssss [ 97%]
ssssss........................ssssssssssss.............sssss..........s. [100%]
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
1833 passed, 759 skipped, 7 warnings in 36.38s
```

### Reachability (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/final-reachability-tmp tests/test_reachability.py
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
54 passed, 5 warnings in 10.06s
```

### Black (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
All done! ✨ 🍰 ✨
9 files would be left unchanged.
```

### Flake8 Branch (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
```

```text
nexus/agents/orrery/resolver.py:1355:89: E501 line too long (133 > 88 characters)
```

### Flake8 origin/main (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/nexus/agents/orrery/substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/nexus/agents/orrery/resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_composition_sources_live.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_faction_membership_roles_pg.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_pair_tag_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_evidence.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/nexus/agents/orrery/resolver.py:1347:89: E501 line too long (133 > 88 characters)
```

### Mypy Branch (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
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

### Mypy origin/main (After Rebase)

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --shadow-file nexus/agents/orrery/substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/nexus/agents/orrery/substrate.py --shadow-file nexus/agents/orrery/resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/nexus/agents/orrery/resolver.py --shadow-file tests/test_orrery/test_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_substrate.py --shadow-file tests/test_orrery/test_resolver.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_resolver.py --shadow-file tests/test_orrery/test_composition_sources_live.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_composition_sources_live.py --shadow-file tests/test_orrery/test_faction_membership_roles_pg.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_faction_membership_roles_pg.py --shadow-file tests/test_orrery/test_pair_tag_substrate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_pair_tag_substrate.py --shadow-file tests/test_orrery/test_evidence.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/origin-main/tests/test_orrery/test_evidence.py nexus/agents/orrery/substrate.py nexus/agents/orrery/resolver.py tests/test_orrery/test_substrate.py tests/test_orrery/test_resolver.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_evidence.py
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

## Supplemental Caller-Audit Probe: Coordinator Triage

This is outside the frozen proof set; the probe ran at original HEAD 711b7690.
The fixture file and resolver behavior are unchanged by the rebase. The caller table exposed an existing
fixture with integer IDs but no metadata rows:
`tests/test_lore/test_recent_orrery_rulings_pg.py:44-81` inserts only
narrative_chunks; :234-257 forwards those IDs through _resolve_then_commit
(:117), without an override. The new shared refusal therefore surfaces that
fixture debt. Per the common rules, an unrelated failing file is reported and
not fixed or skipped; it is not classified as a pre-existing static diagnostic
or a successful test. It is not a production story-opening caller and does not
trigger the standing story-opening stop rule.

Exact affected IDs:

- tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_render_real_outcomes_across_sparse_chunk_ids
- tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_respect_configured_cap
- tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_omit_empty_section

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 NEXUS_TEST_PROVIDER_ONLY=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/783-S6/resume-rulings-tmp tests/test_lore/test_recent_orrery_rulings_pg.py
```

```text
                "Cannot hydrate Orrery world state without world_time "
                f"(anchor_chunk_id={anchor_chunk_id!r})"
            )
E           ValueError: Cannot hydrate Orrery world state without world_time (anchor_chunk_id=1451)

nexus/agents/orrery/resolver.py:552: ValueError
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

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: nexus_test_i685_* x3, postgres
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
ERROR tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_render_real_outcomes_across_sparse_chunk_ids
ERROR tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_respect_configured_cap
ERROR tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_omit_empty_section
5 warnings, 3 errors in 1.88s
```

## Landing Notes and Open Questions

Refs #783. Migration numbers: none. Fleet application: none. Product code changes,
so after landing and pulling the code restart the owner gateway by name:
`nexus restart gateway`. No client bundle change or UI rebuild. No prompt, schema,
package, tunable or runtime settings change. Keep issue #783 open.
The coordinator owns the whole-tree PostgreSQL gate at the final landed commit.
Push and open a review-ready PR; do not merge or wait for bots.

Coordinator: assign a separate fixture-clock repair for the three recent-rulings
setup errors before the whole-tree PostgreSQL landing gate. The required proof
set passes; these errors are explicitly reported under the unrelated-file rule.
The prior static-check question is resolved by the common-rules addition.
No production story-opening clock gap remains unreported.

## Stop-Report — 2026-10-01 (Superseded on Resume)

The following is the original stop diagnosis, retained verbatim. Its static
premise is superseded by the common rules' 2026-10-01 03:25 CDT addition and the
coordinator's resume instruction. Original inspected HEAD was c357ef46;
711b7690 committed the complete stop-report, caller inventory and first-run
outputs and is retained without history rewrite. At that stop, no push or PR
had occurred; the caller table's fixture provenance was still incomplete.

### Original Stop Reason

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

The original coordinator question was: “should the baseline mypy/flake8
failures receive an explicit gate exception for this frozen order, or be repaired
by a separate order before 783-S6 resumes?” It is now resolved; no unrelated
static repair was made. The original stop-report is available in full in the
retained 711b7690 commit.

Codex — GPT-6 (exact runtime variant not exposed)

# Card Identity Verification — Work Order 781

Both authorized two-pass turns were accepted as chunk **50** on `qa640_781_card_identity`, with the clone restored from the same original dump between runs. The configured writer and Gaia both used **gpt-5.6-terra**. There were exactly **two writer requests and two Gaia requests**, with provider/structured-output retries disabled. No additional paid seat was permitted.

**Result:** the same 23 proposal identities were produced before and after. Afterward, all 23 have persisted positions and canonical binding names, including recorded places. The first five ranked cards appear in both prompts; four scene-pressure cards and one joint beat also appear. All 11 exposure rows match both actual prompts, and Backstage lists all 23 proposals in the persisted sequence. The audit traces for both joint actors contain both parent exposures, including the deferred parent.

## Scope and Clock Semantics

The implementation stamps the existing effective-priority policy once, descending, with stable composition-order ties. Positions are zero-based. Identity remains `template_id:binding_hash`; adding display-only places does not alter bindings or hashes. Joint beats refer back to those same ranked parent cards. No presence or `co_located` guards were added.

Migration **122** adds an accepted proposal snapshot on `narrative_chunks` and rendered card data on `orrery_prompt_exposures`, and admits the `joint_beat` exposure kind. These are accepted-turn audit records; there is no pending-proposal ledger or rearm machinery. Only the disposable QA clone and test-owned disposable databases were migrated. The coordinator must apply 122 at land time.

Cards show **evaluated_at**, the diegetic evaluation time, not an invented pre-acceptance occurrence time. Both runs evaluated the original anchor at `2189-10-17T22:37:00+00:00` (the same instant as `18:37:00-04:00` in database sessions). `generated_at` remains wall-clock provenance.

Some actors have no stored location. The cards explicitly show `place=unknown` or `target_place=unknown` for those records. They do not infer location from presence or prose. For example, the source has NULL current_location for Tomas Quill, Ora Pell, Kessa Brin, and Ressa Morn. Thus this slice renders all available canonical place names; it cannot supply names absent from the corpus.

## Matched Inputs and Isolation

| Item | Before | After |
|---|---|---|
| Run | `d2e5ad5d-e141-4086-963d-6e49e83bb809` | `9ead86cb-57e4-48ed-9d83-e2c48003b387` |
| Source | Original `save_04` dump | The identical dump restored again |
| Starting rows | 46 narrative chunks; max ID 49; 23 characters | 46 narrative chunks; max ID 49; 23 characters |
| Player input | I remain quiet for a moment, giving Calyx the space I promised. | Identical |
| Accepted chunk | 50 | 50 |
| Proposal identities | 23 | Same set of 23 |
| Logged exposures | 9: five resolutions, four pressures | 11: five resolutions, four pressures, two joint parents |

The inherited pending draft and selected frontier choice were archived and cleared on the clone before each continuation. The original save was read-only. `SELECT current_database()` verified each evidence connection and each paid dispatch; gameplay routing rejected every database except the clone, with maintenance `postgres` read-only. The isolated gateway used **8015**. It is stopped, and the hand-created clone has been dropped. `save_04` still has **46 narrative chunks, max ID 49, and 23 characters**. These counts are the requested safeguard, not a claim of byte-for-byte equality.

## Rendered Cards Side by Side

These are the actual rendered data lines; only hashes are abbreviated below. The writer and Gaia card sections were byte-equal within each run. Full data lines are in [before-cards.txt](before-cards.txt) and [after-cards.txt](after-cards.txt). Complete prompts, system prompts, assembly payloads, approvals, and raw SQL receipts are retained in [evidence.zip](evidence.zip).

### Orrery Imminent Activity

| Before | After |
|---|---|
| - honor_debt:ff450d8c… [Fulfill obligation through a dead-drop]: state_delta={&#x27;character.current_activity&#x27;: &#x27;servicing an old debt&#x27;} | - hide:85dcc9f3… [Go dark and reduce signal exposure]: position=0; actor=Elian Rook; place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; state_delta={&#x27;character.current_activity&#x27;: &#x27;reducing signal exposure&#x27;} |
| - hide:85dcc9f3… [Go dark and reduce signal exposure]: state_delta={&#x27;character.current_activity&#x27;: &#x27;reducing signal exposure&#x27;} | - honor_debt:ff450d8c… [Fulfill obligation through a dead-drop]: position=1; actor=Ivo Senn; place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; state_delta={&#x27;character.current_activity&#x27;: &#x27;servicing an old debt&#x27;} |
| - stroll:a339b89d… [Pace the near ground]: state_delta={&#x27;character.current_activity&#x27;: &#x27;pacing the near ground&#x27;} | - check_on_dependent:b141c5fd… [Reach out through customary channels]: position=2; actor=Elian Rook; place=Lantern Quay Memorial Hall; target=Tam Oris; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; state_delta={&#x27;character.current_activity&#x27;: &#x27;checking in on a dependent&#x27;} |
| - upkeep:f0d332a1… [Tidy what is theirs]: state_delta={&#x27;character.current_activity&#x27;: &#x27;tidying their own space&#x27;} | - check_on_dependent:02e54df4… [Reach out through customary channels]: position=3; actor=Ren Vale; place=Lantern Quay Memorial Hall; target=Dr. Sera Vey; target_place=unknown; evaluated_at=2189-10-17T22:37:00+00:00; state_delta={&#x27;character.current_activity&#x27;: &#x27;checking in on a dependent&#x27;} |
| - drink:850b31cf… [Drink routinely from what is at hand]: state_delta={&#x27;character.current_activity&#x27;: &#x27;drinking routinely&#x27;, &#x27;need.fulfill&#x27;: {&#x27;type&#x27;: &#x27;thirst&#x27;, &#x27;quality&#x27;: &#x27;routine&#x27;, &#x27;discharge_debt&#x27;: 9999}} | - surveil:93626842… [Keep the target in view without contact]: position=4; actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Elian Rook; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; state_delta={&#x27;character.current_activity&#x27;: &#x27;surveilling without contact&#x27;} |

### Orrery Scene Pressure

| Before | After |
|---|---|
| - Follow the public pattern: Ivo Senn may have mapped the public pattern around Mara Vey. Use this only as Storyteller-controlled scene pressure or a future setup. | - Follow the public pattern: actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; Ivo Senn may have mapped the public pattern around Mara Vey. Use this only as Storyteller-controlled scene pressure or a future setup. |
| - Reach out through customary channels: Ivo Senn has sent Kessa Brin a routine welfare-check message. The scene may use this as an unread notification, an answered exchange, or texture for Kessa Brin&#x27;s decisions. | - Reach out through customary channels: actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Kessa Brin; target_place=unknown; evaluated_at=2189-10-17T22:37:00+00:00; Ivo Senn has sent Kessa Brin a routine welfare-check message. The scene may use this as an unread notification, an answered exchange, or texture for Kessa Brin&#x27;s decisions. |
| - Collect a proxy watcher report: Niko Rell has someone off-screen watching for signs around Mara Vey. This can surface as a watcher, rumor, false alarm, or nothing at all. | - Collect a proxy watcher report: actor=Niko Rell; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; Niko Rell has someone off-screen watching for signs around Mara Vey. This can surface as a watcher, rumor, false alarm, or nothing at all. |
| - Collect a proxy watcher report: Tam Oris has someone off-screen watching for signs around Mara Vey. This can surface as a watcher, rumor, false alarm, or nothing at all. | - Collect a proxy watcher report: actor=Tam Oris; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; Tam Oris has someone off-screen watching for signs around Mara Vey. This can surface as a watcher, rumor, false alarm, or nothing at all. |

### Orrery Joint Beats

| Before | After |
|---|---|
| - [crossed] Elian Rook &amp; Tam Oris: check_on_dependent &lt;-&gt; surveil (check_on_dependent:b141c5fd… / surveil:31b0006f…) | - [crossed] Elian Rook &amp; Tam Oris: check_on_dependent &lt;-&gt; surveil (check_on_dependent:b141c5fd… / surveil:31b0006f…); forward: position=2; actor=Elian Rook; place=Lantern Quay Memorial Hall; target=Tam Oris; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00; reverse: position=10; actor=Tam Oris; place=Lantern Quay Memorial Hall; target=Elian Rook; target_place=Lantern Quay Memorial Hall; evaluated_at=2189-10-17T22:37:00+00:00 |

## Exposure Rows Side by Side

Positions for main and joint proposal exposures are the persisted global proposal ranks. `joint_beat_position` separately records the beat’s position in its section. A parent shown in both sections has two exposure kinds; this is not two separate proposals. There are six distinct exposed proposal identities after the change.

| Before | After |
|---|---|
| resolution · position 0 · honor_debt:ff450d8c… · names not recorded | joint_beat · position 2 · check_on_dependent:b141c5fd… · actor=Elian Rook; place=Lantern Quay Memorial Hall; target=Tam Oris; target_place=Lantern Quay Memorial Hall |
| resolution · position 1 · hide:85dcc9f3… · names not recorded | joint_beat · position 10 · surveil:31b0006f… · actor=Tam Oris; place=Lantern Quay Memorial Hall; target=Elian Rook; target_place=Lantern Quay Memorial Hall |
| resolution · position 2 · stroll:a339b89d… · names not recorded | resolution · position 0 · hide:85dcc9f3… · actor=Elian Rook; place=Lantern Quay Memorial Hall |
| resolution · position 3 · upkeep:f0d332a1… · names not recorded | resolution · position 1 · honor_debt:ff450d8c… · actor=Ivo Senn; place=Lantern Quay Memorial Hall |
| resolution · position 4 · drink:850b31cf… · names not recorded | resolution · position 2 · check_on_dependent:b141c5fd… · actor=Elian Rook; place=Lantern Quay Memorial Hall; target=Tam Oris; target_place=Lantern Quay Memorial Hall |
| scene_pressure · position 0 · surveil:5c8f9b44… · names not recorded | resolution · position 3 · check_on_dependent:02e54df4… · actor=Ren Vale; place=Lantern Quay Memorial Hall; target=Dr. Sera Vey; target_place=unknown |
| scene_pressure · position 1 · check_on_dependent:19cf0e8c… · names not recorded | resolution · position 4 · surveil:93626842… · actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Elian Rook; target_place=Lantern Quay Memorial Hall |
| scene_pressure · position 2 · surveil:92cf3d4a… · names not recorded | scene_pressure · position 0 · surveil:5c8f9b44… · actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall |
| scene_pressure · position 3 · surveil:1e994ef5… · names not recorded | scene_pressure · position 1 · check_on_dependent:19cf0e8c… · actor=Ivo Senn; place=Lantern Quay Memorial Hall; target=Kessa Brin; target_place=unknown |
| — | scene_pressure · position 2 · surveil:92cf3d4a… · actor=Niko Rell; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall |
| — | scene_pressure · position 3 · surveil:1e994ef5… · actor=Tam Oris; place=Lantern Quay Memorial Hall; target=Mara Vey; target_place=Lantern Quay Memorial Hall |

Before, the Elian→Tam `check_on_dependent` and Tam→Elian `surveil` IDs were rendered in the joint-beat block, and Gaia explicitly deferred both, but neither had an exposure row. Afterward, the joint records have parent positions **2** and **10**, with the same names and evaluation time as the rendered card. Position 2 is also shown among the five main cards; position 10 is exposed only through the joint beat.

## Gaia Adjudications Side by Side

| Before | After |
|---|---|
| honor_debt:ff450d8c… · defer · The Wickglass obligation has reached its actual choice, but Mara has not signed the dead-book sentence or fulfilled anything; it must not resolve through an off-screen dead-drop. | hide:85dcc9f3… · defer · Elian’s exposure remains real, but she has not chosen a withdrawal move; her present boundary and Tam’s paused process should not be spent off-screen. |
| check_on_dependent:b141c5fd… · defer · Elian&#x27;s choices around Tam&#x27;s safety remain hers; no autonomous check-in is settled while Mara&#x27;s Guild conversation holds the camera. | honor_debt:ff450d8c… · void · Ivo’s debt cannot be serviced by dead-drop: he owes Ressa an in-person, public-to-her accounting before dawn. |
| surveil:31b0006f… · defer · Tam&#x27;s fear does not authorize an off-screen surveillance act; the hall must let Tam define any boundary around Mara directly. | check_on_dependent:b141c5fd… · defer · Elian may choose to offer Tam contact, but Tam’s need for quiet and their suspended shelter decision make an automatic outreach premature. |
| No additional explicit ruling | check_on_dependent:02e54df4… · replace · Ren begins a qualified inquiry into Dr. Sera Vey’s present status, without treating her as a dependent or assuming a location or culpability. |
| No additional explicit ruling | surveil:93626842… · void · Ivo will not convert his remorse or proximity into surveillance of Elian; he remains responsible for his own dawn accounting. |

Before, the debt card was misattributed to Mara’s Wickglass obligation. Afterward, Gaia identified **Ivo’s debt to Ressa** and voided the unsuitable dead-drop proposal. Gaia also replaced Ren’s proposed dependent check with a qualified inquiry about Dr. Sera Vey. It still deferred Elian’s outreach; Tam’s joint-beat surveillance was ratified by omission. These are observations from one matched before/after pair, not evidence of a general acceptance-rate improvement.

## Read-Side and Persistence Proof

- `resolver.py:2740` computes the sole effective-priority sequence; `resolver.py:2772` resolves display names and places without changing identity.
- `logon_utility.py:136` renders stable identity fields; the imminent, pressure, and joint blocks use it at lines 2699, 2722, and 2794. JSONB key order cannot change the rendered name order.
- `events.py:748` and `events.py:1027` persist the accepted snapshot on the sync and async paths. `events.py:1800` logs the same ranked drafts, including each displayed joint parent.
- `audit.py:1688` includes joint exposures and reads snapshotted bindings even if Gaia deferred or voided the proposal and no resolution row exists.
- `backstage.py:582` reads the accepted snapshot without re-ranking. The existing `BackstageDrawer.tsx:238` maps the returned rows in that order. No `ui/` source changed.

The live checks read both complete `cognition_trace` results and `build_backstage_turn` from the accepted after turn under a read-only transaction. Assertions compared every logged card’s formatted identity against **both saved seat prompts**, compared main-card IDs against the first five persisted positions, compared all Backstage IDs/positions against the full snapshot, and confirmed both joint parents in both actors’ audit traces. All passed; [comparison.json](comparison.json) contains the parity receipt and the structured comparison.

```sql
SELECT current_database();
SELECT c.entity_id, c.name, c.current_location, p.name AS place_name
FROM characters c LEFT JOIN places p ON p.id=c.current_location
ORDER BY c.entity_id;

SELECT kind, proposal_id, position, card
FROM orrery_prompt_exposures
WHERE tick_chunk_id = 50
ORDER BY kind, position;

SELECT current_database(),
       (SELECT count(*) FROM narrative_chunks) AS narrative_chunks,
       (SELECT max(id) FROM narrative_chunks) AS max_chunk_id,
       (SELECT count(*) FROM characters) AS characters;
```

## Exact Test Commands and Output

All commands ran from this worktree with the shared interpreter. Import proof printed `/Users/pythagor/nexus/.claude/worktrees/781-card-identity/nexus/__init__.py`. Full final logs are in [test-results.txt](test-results.txt). The targeted PostgreSQL gate actually ran its tests with **no skips**. No #885 exemptions were needed. The offline suite’s 821 skips are its normal PostgreSQL/live-inference gates.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```
```text
2656 passed, 821 skipped, 9 warnings in 101.91s (0:01:41)
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery tests/test_lore -k 'card or exposure or proposal or rank or joint or imminent or pressure'
```
```text
41 passed, 1808 deselected, 7 warnings in 6.82s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_card_identity.py
```
```text
3 passed, 5 warnings in 2.76s
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_backstage_endpoints_pg.py
```
```text
8 passed, 7 warnings in 3.28s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery/test_resolver.py tests/test_orrery/test_catalog.py
```
```text
121 passed in 0.84s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery tests/test_lore -k 'card or exposure or proposal or rank or joint or imminent or pressure'
```
```text
35 passed, 6 skipped, 1808 deselected, 7 warnings in 3.85s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```
```text
37 passed in 6.87s
```

The initial offline run caught the new QA script missing from the reachability operator registry. A later run caught legacy fixture name expectations and the generated catalog needing migration 122 listed. Those were corrected; the full final offline run above has zero failures. The new tests use the real resolver, both PostgreSQL commit paths, prompt formatter, audit, and Backstage; no new mocks or paid test calls were added.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/agents/lore/logon_utility.py nexus/agents/orrery/{audit,backstage,events,history,resolver}.py tests/test_api/test_backstage_endpoints_pg.py tests/test_orrery/{test_ambient,test_card_identity,test_resolver}.py scripts/qa_shift/card_identity_probe.py
```
```text
All done! ✨ 🍰 ✨
11 files would be left unchanged.
```

Both implementation pre-commit hooks passed: `Regenerate Orrery package catalog` and `Validate NEXUS config and model-ID drift`. No frontend build was run because no `ui/` files changed.

## Live Commands

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/card_identity_probe.py clone
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/card_identity_probe.py up
PYTHONPATH=$PWD NEXUS_GATEWAY_PORT=8015 NEXUS_API_URL=http://127.0.0.1:8015 /Users/pythagor/nexus/.venv/bin/python -m nexus.cli continue --slot 4 --user-text 'I remain quiet for a moment, giving Calyx the space I promised.'
PYTHONPATH=$PWD NEXUS_GATEWAY_PORT=8015 NEXUS_API_URL=http://127.0.0.1:8015 /Users/pythagor/nexus/.venv/bin/python -m nexus.cli down
```

The up/continue/down sequence ran once before and once after implementation; the clone was restored between them and migration 122 was applied directly to the restored clone. Each generated draft was accepted through `POST /api/narrative/approve` with logical slot 4, its captured session ID, and `commit=true`. Full CLI text and approval responses are in the archive.

## Limits and Coordinator Questions

- `prompts/*.md` is untouched. The coordinator may want one sentence clarifying that these are off-screen proposals and `evaluated_at` is not a committed occurrence timestamp.
- Who will supply missing canonical locations? This slice displays unknown locations explicitly and does not infer them or repair the corpus.
- The pending-proposal ledger and rearm predicates remain deferred as ordered. Migration 122 still needs coordinator deployment.
- Auxiliary experience-renderer requests were deliberately blocked before payment by the QA authorization guard. This limit does not affect the four completed writer/Gaia requests or the accepted card/exposure evidence, and this run does not validate background experience rendering or incremental embedding.

Authored by Codex (GPT-6 Astra).

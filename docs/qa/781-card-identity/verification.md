# Card Identity Verification — Work Order 781

The second and third coordinator amendments are implemented. The saved real two-pass turn replays through both PostgreSQL commit paths without new provider calls. Eleven exposure rows follow the actual prompt order; both joint actors' audit traces preserve that order. Backstage's primary proposal sequence is **0, 1, 2, 3, 4, 2, 10**; its separate, collapsed inventory is **0–22**.

Ren Vale's saved Gaia replacement now wins over lower-ranked `surveil` and `upkeep` scalar writes. Four PostgreSQL regressions cover both commit paths with ratification and with Gaia's replacement; the full saved-turn replay additionally uses the original structured state updates. The canonical key remains `template_id:binding_hash` everywhere durable.

## Reference Mapping and Card Format

Cards show `<template_id>:<first 8 hash characters>`, deterministically lengthened only for collisions within the rendered selection. Both seats use the same mapping. Runtime staging and both commits normalize rendered handles before canonical validation; canonical IDs remain accepted. Unknown handles, unrendered handles, and duplicate canonical/handle decisions raise errors. Replacement-tag validation sees the same handle-to-binding mapping.

```text
- [0] hide:85dcc9f3 Elian Rook at Lantern Quay Memorial Hall: Go dark and reduce signal exposure
- [3] check_on_dependent:02e54df4 Ren Vale at Lantern Quay Memorial Hall → Dr. Sera Vey: Reach out through customary channels
```

Unknown places are omitted; a target's place appears only when known and different from the actor's. A card evaluated on an earlier turn appends ` · evaluated <clock face>` through `nexus/util/clock_face.py`. Current-turn cards omit the timestamp; durable records keep `evaluated_at` (not an invented occurrence time). Joint parents each use the same card shape and their existing rank.

| #903 Rendered Block Accounting | Original | Amended |
|---|---:|---:|
| Imminent Activity | 657 | 264 |
| Scene Pressure | 431 | 316 |
| Joint Beats | 306 | 148 |
| **Total Per Seat** | **1,394** | **728** |

This is a **666-token reduction per seat (47.8%)**, using `local_text_counter` and `measure_blocks` with the saved model's declared tokenizer. The original formatter at `67bf8527` and current formatter receive the same saved card payload. This measures renderer-owned blocks, including their instructions and separators; it does not claim provider usage or system/schema framing. [Token receipt](live/replay-token-counts.json), [reference mapping and replayed Gaia rulings](live/replay-reference-mapping.json), [writer cards](after-writer-cards.txt), [Gaia cards](after-gaia-cards.txt).

## Persistence, Audit, and Commit Precedence

- `nexus/agents/orrery/cards.py:16` selects the existing ranked cards and joint parents. `turn_cycle.py` freezes the ordered `(kind, proposal_id)` keys before rendering and stages that exact selection. Changed acceptance-time caps cannot change it.
- `events.py` persists the selection inside migration 122's existing proposal JSONB and writes exposures in the selected order. No additional schema column or tunable is required. Migration 122's comment documents the selection.
- `audit.py` joins the saved selection with ordinality, so a repeated joint parent stays at its actual prompt occurrence. Tests compare ordered sequences, not sets.
- `backstage.py` returns the rendered proposal sequence as `rows` and the full ranked inventory separately as `inventory`. The existing drawer uses the primary list and a native disclosure for the secondary list, without a new visible label. Canonical keys and evaluation times remain available on row hover and in the response.
- `events.py:_commit_order` applies descending position (ascending effective rank): lower-priority proposals first, highest-ranked scalar write last. Each replacement executes in its proposal's slot. Unranked historical drafts retain their serialized commit order.

| Replay Evidence | Sync | Async |
|---|---|---|
| Ordered Exposure Rows | [11 rows](live/replay-sync-exposures.json) | [11 rows](live/replay-async-exposures.json) |
| Elian's Audit Response | [actor 4](live/replay-sync-audit-4.json) | [actor 4](live/replay-async-audit-4.json) |
| Tam's Audit Response | [actor 16](live/replay-sync-audit-16.json) | [actor 16](live/replay-async-audit-16.json) |
| Backstage Sequence and Inventory | [response](live/replay-sync-backstage.json) | [response](live/replay-async-backstage.json) |
| Canonical Adjudication Log | [rows](live/replay-sync-adjudications.json) | [rows](live/replay-async-adjudications.json) |
| Ren's Final Activity | [SQL result](live/replay-sync-ren.json) | [SQL result](live/replay-async-ren.json) |

Both Ren receipts read `preparing a qualified status inquiry regarding Dr. Sera Vey`. The saved paid after-turn fixture is [after-draft.json](live/after-draft.json). The old `comparison.json` and original audit responses are historical: their original membership checks did **not** prove the ordered parity now required.

Visual QA renders the actual `BackstageDrawer` with the real replay response, using React server rendering and the built stylesheet. Chromium confirms seven primary rows and 23 rows behind the native disclosure. This is component QA, not a live gameplay UI run. The temporary static server used free lane 8015 and was stopped; no gateway or provider was started during this amendment.

![Rendered Sequence](backstage-rendered.png)
![Expanded Inventory](backstage-inventory.png)

## Isolation Receipts

Every replay target was a disposable `qa640_781_replay_*` clone of `save_04`. Each write path first proved `SELECT current_database()`; test fixtures owned their disposable databases. All replay databases were dropped by their context managers. Source counts were read with `default_transaction_read_only=on` before and after; both show **46 narrative chunks, max ID 49, 23 characters**.

```sql
SELECT current_database(),
       (SELECT count(*) FROM narrative_chunks) AS narrative_chunks,
       (SELECT max(id) FROM narrative_chunks) AS max_chunk_id,
       (SELECT count(*) FROM characters) AS characters;
SELECT entity_id, name, current_activity FROM characters WHERE name='Ren Vale';
```

[Before source receipt](live/replay-source-before.json), [after source receipt](live/replay-source-after.json), [exact SQL and target identities](live/sql.jsonl). The following historical proof records the two paid turns authorized in the original order; the amendment made **zero** new paid calls.

## Original Paid Turns (Historical)

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

## Original Rendered Cards Side by Side

These are the actual rendered data lines; only hashes are abbreviated below. The writer and Gaia card sections were byte-equal within each run. The original complete card blocks are preserved for [before writer](before-skald_writer-original-cards.txt), [before Gaia](before-gaia-original-cards.txt), [after writer](after-skald_writer-original-cards.txt), and [after Gaia](after-gaia-original-cards.txt). These historical prompts precede the amendments. Current replay rendering is [after-cards.txt](after-cards.txt); no new paid adjudication was requested.

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

## Original Exposure Rows Side by Side

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

## Original Gaia Adjudications Side by Side

| Before | After |
|---|---|
| honor_debt:ff450d8c… · defer · The Wickglass obligation has reached its actual choice, but Mara has not signed the dead-book sentence or fulfilled anything; it must not resolve through an off-screen dead-drop. | hide:85dcc9f3… · defer · Elian’s exposure remains real, but she has not chosen a withdrawal move; her present boundary and Tam’s paused process should not be spent off-screen. |
| check_on_dependent:b141c5fd… · defer · Elian&#x27;s choices around Tam&#x27;s safety remain hers; no autonomous check-in is settled while Mara&#x27;s Guild conversation holds the camera. | honor_debt:ff450d8c… · void · Ivo’s debt cannot be serviced by dead-drop: he owes Ressa an in-person, public-to-her accounting before dawn. |
| surveil:31b0006f… · defer · Tam&#x27;s fear does not authorize an off-screen surveillance act; the hall must let Tam define any boundary around Mara directly. | check_on_dependent:b141c5fd… · defer · Elian may choose to offer Tam contact, but Tam’s need for quiet and their suspended shelter decision make an automatic outreach premature. |
| No additional explicit ruling | check_on_dependent:02e54df4… · replace · Ren begins a qualified inquiry into Dr. Sera Vey’s present status, without treating her as a dependent or assuming a location or culpability. |
| No additional explicit ruling | surveil:93626842… · void · Ivo will not convert his remorse or proximity into surveillance of Elian; he remains responsible for his own dawn accounting. |

Before, the debt card was misattributed to Mara’s Wickglass obligation. Afterward, Gaia identified **Ivo’s debt to Ressa** and voided the unsuitable dead-drop proposal. Gaia also replaced Ren’s proposed dependent check with a qualified inquiry about Dr. Sera Vey. It still deferred Elian’s outreach; Tam’s joint-beat surveillance was ratified by omission. These are observations from one matched before/after pair, not evidence of a general acceptance-rate improvement.

## Previous Gate Stop (Resolved by the Fourth Amendment)

Merged `origin/main` at `794e5a85` in `ba7e7b2e`. PostgreSQL, Backstage, Black, replay, TypeScript, and the UI build pass. The offline gate has **one non-exempt failure**, so this branch is **not gate-green and was not pushed**. No merge or paid provider call followed.

`tests/test_lore/test_two_pass_pipeline.py:1073` asserts `len(prompt.split()) < 700`; the merged `prompts/storyteller_gaia.md` has 753 words. Both files are byte-identical to `origin/main`, proved in [main-gate-receipt.txt](main-gate-receipt.txt). Neither the prompt nor the gate was changed by this amendment. The frozen order forbids edits to `prompts/`; weakening the independent concision gate is not an implementation fix. This is outside #885, and no #885 exemption was needed in the passing PostgreSQL selection.

Before the final runs, the first offline attempt caught incomplete legacy card fixtures and the new module missing from the reachability registry; those were corrected. The first post-merge PostgreSQL selection found one more placeholder proposal in the recall fixture; it now uses a real `OrreryTickProposal`. Both hooks passed on the implementation commit after historical model pins were annotated in two pre-existing, ignored `.nexus/` report helpers. All final commands below ran from this worktree with the proven shared interpreter. Offline skips are the normal database/provider gates, not evidence for PostgreSQL.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```
```text
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
1 failed, 2662 passed, 850 skipped, 9 warnings in 103.08s (0:01:43)
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery tests/test_lore -k 'card or exposure or proposal or rank or joint or imminent or pressure'
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
49 passed, 1808 deselected, 7 warnings in 10.97s
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_backstage_endpoints_pg.py
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
8 passed, 7 warnings in 2.66s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
git diff --diff-filter=ACM --name-only -z origin/main -- '*.py' | xargs -0 /Users/pythagor/nexus/.venv/bin/python -m black --check
```
```text
All done! ✨ 🍰 ✨
17 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/card_identity_probe.py replay
```
```text
sync: canonical adjudications accepted; 11 ordered exposures; Backstage [0, 1, 2, 3, 4, 2, 10]; Ren replacement wins
async: canonical adjudications accepted; 11 ordered exposures; Backstage [0, 1, 2, 3, 4, 2, 10]; Ren replacement wins
Card blocks: 1394 -> 728 tokens per seat
save_04 unchanged: 46 chunks, max 49, 23 characters; disposable replay databases dropped; no provider calls
```

```sh
npm --prefix ui run check
```
```text

> nexus-ui@1.0.0 check
> tsc

```

```sh
npm --prefix ui run build
```
```text
✓ built in 2.48s

PWA v1.0.3
mode      generateSW
precache  22 entries (2274.42 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## Fourth Amendment: Final Gates

Merged coordinator fix `879841a3` from `origin/main` in `75d971d5`. The offline gate now has zero failures; the PostgreSQL selection actually ran with no skips and no #885 exemptions. Black passes for all 17 changed Python files. No new provider calls, gateway starts, UI edits, or manual database operations were performed in this amendment. The prompt has no branch diff against main. Prior replay and UI receipts above remain historical evidence; this amendment reran the requested Python gates only.

Import proof (`PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'`) returned `/Users/pythagor/nexus/.claude/worktrees/781-card-identity/nexus/__init__.py`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2663 passed, 850 skipped, 9 warnings in 97.90s (0:01:37)
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery tests/test_lore -k 'card or exposure or proposal or rank or joint or imminent or pressure'
```
```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
49 passed, 1808 deselected, 7 warnings in 9.64s
```

```sh
git diff --diff-filter=ACM --name-only -z origin/main -- '*.py' | xargs -0 /Users/pythagor/nexus/.venv/bin/python -m black --check
```
```text
All done! ✨ 🍰 ✨
17 files would be left unchanged.
```

## Coordinator Questions and Deferred Work

1. The inherited prompt concision failure is resolved by coordinator PR #927; the fourth-amendment gates below pass. No open implementation question remains.
2. Apply migration 122 at landing. No fleet or template migration was performed. Every new column remains commented.
3. Add the planned Gaia explanatory sentence at landing if still wanted; `prompts/` and `nexus.toml` have no branch diff against merged main.

The durable pending-proposal ledger, rearm predicates, corpus location repair, and roster presence are outside this slice. No `co_located` guards were added. The two original paid turns remain the only paid proof; this amendment is deterministic replay, not new inference-quality evidence.

Authored by Codex (GPT-6 Astra).

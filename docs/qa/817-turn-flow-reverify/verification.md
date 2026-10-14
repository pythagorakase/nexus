# 817-S2b: Re-Verify the Turn-Flow Document and AGENTS.md

Work order 817-S2b (issue #817). This branch re-reads every clause of
`docs/turn_flow_sequence.md` against the code, corrects the false ones,
narrows its sources to the files the kept clauses rest on, and moves both
stamps. It changes Markdown only.

## The Merge Base

```
$ git fetch origin
$ git merge-base HEAD origin/main
a01c162f1e4daaf5009a9bba7397ae4065a8614b
```

`M` is `a01c162f1e4daaf5009a9bba7397ae4065a8614b` (PR #1150, the last wave-B
landing). Every `file:line` below refers to the tree at `M`.

## The Range (Item 1)

The last whole-document pass was `be1c299c`. The 30 declared sources are the
front-matter list at `M` (`docs/turn_flow_sequence.md:3-33`).

```
$ SRC=(<the 30 declared sources>)
$ git rev-list --first-parent --count be1c299c..a01c162f
142
$ git log --first-parent --oneline be1c299c..a01c162f -- $SRC | wc -l
47
$ git diff --stat be1c299c a01c162f -- $SRC | tail -1
 24 files changed, 2011 insertions(+), 1579 deletions(-)
```

47 of the 142 first-parent commits in `be1c299c..M` touch at least one
declared source:

```
493902a1 Client Plane Awareness; Retire the No-Op slot/select (824-S1, 824-S5) (#1147)
21cf9353 Typed Settings Response; Fresh Slots Store No Model Pin (809-S3b, 809-S7a) (#1146)
954e8dc3 Trait Derivation on the Wait Screen (776-S6) (#1142)
6853e529 Move Runtime-Imported Setup and Migration Modules Into nexus/ (811-S3a) (#1141)
bab4b68b World-Hour Predicates, Event Times in the Read Model, and a World-Time Horizon (778-S3) (#1134)
75699431 Typed Settings for the Remaining Product Dict Readers (809-S1) (#1130)
f073b371 Merge pull request #1128 from pythagorakase/claude/812-models-plan-fetch
9c8f1050 Merge pull request #1123 from pythagorakase/claude/816-test-provider-database
6f338c55 Merge pull request #1122 from pythagorakase/claude/785-travel-trio
7399bd99 Merge pull request #1120 from pythagorakase/claude/812-one-embedder
91678330 Merge pull request #1117 from pythagorakase/claude/822-story-identity
8f4ad48e Runtime maturation follows the story's genesis strangeness (#838 S1) (#1111)
4f1d1b81 Delete the uncalled MEMNON read-only SQL executor; keep the documented unused labels (#813 S2, S3) (#1108)
c58f86d2 Remove the dead wizard streaming endpoint (#1081) (#1103)
16013454 Live services and local-model captures rotate under the configured policy (#842 S2, S3) (#1065)
63fe4e7f Add keyset reader feed over playable story order (#1092)
5f321ff8 Add per-block removed token accounting (#756 S1) (#1095)
d39d61ba Stamp resolver event occurrence time and backfill legacy NULLs (#1097)
ee60b199 Persist genesis runs and reattach the wizard waiter (#776 S1a) (#1082)
29e79648 Move the deep-query candidate count into nexus.toml (#1089)
edfea333 Move the acquaintance introduction cap into nexus.toml (#1085)
56b7854a Hydrate travel world times and move route speeds into nexus.toml (#785 S2) (#1068)
ffc2d6b8 CLI HTTP handlers classify unusable answers instead of catching broadly (#815 S1) (#1060)
fedebf92 Embedder, reranker and search errors fail the turn; MEMNON loads the reranker (#812 S2) (#1059)
a4c2be8d TEST identity keys on the registry provider; the setup script stops falling back to TEST (#809 S2) (#1057)
41783c1d Migration 138 adopts three unowned indexes and chunk_metadata.scene; the constructor stops creating tables (#810) (#1053)
172bd0e2 Faction membership follows the role (#1033) (#1047)
4c96f8f4 Audit tags in deprecated categories and make the registry the only vocabulary (#811 slice B) (#1030)
07825e12 Share one session waiter and add the player-plane inspect family (#815 slice) (#1024)
696ccf29 Read the alias-backed settings from the typed models behind a parity proof (#809 slice A) (#1021)
588fc543 Retire the async commit twin and fix the playable-boundary lookup (#807 slice A) (#1012)
300a78e3 Build the IDF rebuild a PostgreSQL patch release requires (#1013) (#1014)
c060e93b Make every model loader local-only and commit the artifact lock (#812 slice) (#1010)
9a67e864 Merge pull request #1005: Give the CLI one transport, exit-code, and JSON error contract
84794f2c Merge pull request #1006: Show a deterministic, source-cited return recap above the frontier
276134cb Merge pull request #1004: Add nexus doctor and one registry of role-scoped readiness checks
20894e4f Merge pull request #1002: Send the recollection renderer instructions once and embed rendered recollections from the scheduler
a481b828 Merge pull request #1000: Wire the genesis strangeness selection from the wizard through the transition
9b75167d Merge pull request #1001: Version Pass-2 baselines so a context-window change no longer bricks the next continuation
f6140704 Merge pull request #995: Derive one attempt-keyed turn observation and read it through nexus inspect-turn
cb92207d Merge pull request #996: Resolve the active config and runtime directories through one runtime home
1b250317 Merge pull request #999: Build MEMNON retrieval results through one typed shape and share embedding orchestration across sources
61023ff0 Merge pull request #997: Make the genesis zone radius a validated setting and stop swallowing boundary failures
c1d5416f Merge pull request #991: Make selection, editing, and regeneration deliberate in the reader
ce1d9dea Merge pull request #993: Retire the orphan Storyteller app, its session layer and ChunkWorkflow
664c7f6a Merge pull request #992: Show which API keys the configured model seats require
5b5f9bdd Merge pull request #989: Show truthful genesis stages while the wizard transition runs
```

The diff `git diff be1c299c a01c162f -- $SRC` (5,987 lines) was read file by
file; every clause below was then checked against the tree at `M` directly,
whether or not its file appears in that diff. The order's line numbers came
from `b0da93ea`; each cited location was re-derived at `M` (for example the
state route is now `nexus/api/slot_endpoints.py:43`, not `:58`, and
`resolve_dry_run` is now `nexus/agents/orrery/resolver.py:2503`, not `:2434`).

## Clause Table (Item 2)

**Convention.** "Line" is the line in `docs/turn_flow_sequence.md` at `M`,
before this branch's edits. A `corrected` row adds the line after the edit
("47-49 → 70-72"). This branch grows the front matter by 23 lines and keeps
the body's line count, so an unchanged body line `L` now sits at `L + 23`.
Evidence is `file:line`
at `M`. A clause that names a function, class, type, route, CLI command or
`nexus.toml` key cites its definition; a behavior or order clause cites the
line that performs it, in a declared source where one shows it. A clause
about a step cites the call that performs the step; a clause about how the
callee behaves (a coverage set, a criterion, a failure mode) cites the callee.
UI clauses cite the handler or render condition, never a doc comment.
"Convention" rows are the document's own framing and have no source;
"reference" rows are links to other documents, checked for existence only.

### Introduction

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 39-40 | One turn takes one player action to one pending draft, and the next action accepts that draft into the story. | `nexus/api/narrative_generation.py:383` (`write_to_incubator` stages the one draft); `nexus/api/narrative.py:949` (the next continue accepts the pending draft first) | true |
| 40-42 | Nothing a turn generates becomes part of the story before acceptance: the draft waits in the slot's single-row `incubator` until the player moves on. | `nexus/api/narrative_generation.py:562` (`INSERT INTO incubator (id, ...) VALUES (TRUE, ...)`); `nexus/api/commit_handler_sync.py:512` (the `narrative_chunks` insert happens only in the commit) | true |
| 42-43 | The code paths in the front matter are authoritative; this document is their map. | Convention. | true |

### 1. The Player Acts

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 47 | The IRIS Narrative pane runs on `ui/client/src/hooks/useNarrativeEngine.ts`. | Locator: `ui/client/src/components/nexus/NarrativePane.tsx:89` (the pane's `engine` is a `NarrativeEngine`), `:413`; `ui/client/src/hooks/useNarrativeEngine.ts:70` | true |
| 47-49 → 70-72 | The pane polls `GET /api/slot/{slot}/state`. Now: the pane reads it. | `ui/client/src/hooks/useNarrativeEngine.ts:123-127` (one `useQuery`, no refetch interval); `:133-134` (`invalidateNarrativeQueries` invalidates it, so each invalidation re-reads it: after a submission starts `:455` or fails `:469`, on a terminal transition `:247`, `:280`, when a superseded owner is observed `:224`, and at each boundary `:336-337`, which runs on mount `:379`, after a wake gap `:350`, on a return to the tab `:355-356` and on each socket open or reconnect `:364`) | corrected |
| 48 | The route `GET /api/slot/{slot}/state`. | `nexus/api/slot_endpoints.py:43` (route decorator); `nexus/api/slot_state.py:106` `get_slot_state` | true |
| 48-49 | The state carries the newest passage, which is the pending draft when one exists, and its choices. | `nexus/api/slot_state.py:333-343` (an incubator row is returned with `has_pending=True` and its choices); `:346` (otherwise the committed frontier) | true |
| 49-50 | Selecting a choice, by click or number key, only loads its text into the reader's draft. | `ui/client/src/components/nexus/NarrativePane.tsx:840` (click), `:507-511` (number key), both to `handleSelect` `:435-442`, which calls `draft.select`; `ui/client/src/hooks/useInputDraft.ts:124-126` (`select` writes the draft and never submits) | true |
| 50-51 | The draft remembers the choice while the player edits the text and forgets it once the text is cleared. | `ui/client/src/hooks/useInputDraft.ts:116-121` (`update` keeps `choice` only while `text.trim()` is non-empty) | true |
| 51-52 | Enter or the send glyph commits. | `ui/client/src/components/nexus/NarrativePane.tsx:473-482` (Enter), `:872` (send glyph), both to `handleSend` `:456-471` | true |
| 52-55 | `continueNarrative` (`narrative-api.ts`) posts `slot`, the draft as `choice` plus `user_text` (one edited-choice payload) or as freeform `user_text` alone, and any pending draft's `session_id` to `POST /api/narrative/continue`. | `ui/client/src/components/nexus/NarrativePane.tsx:462-466` (choice plus text, or text alone); `ui/client/src/hooks/useNarrativeEngine.ts:491-497` (adds the pending `session_id`); `ui/client/src/lib/narrative-api.ts:208-223` (the POST); route `nexus/api/narrative.py:851-852` | true |
| 55-56 | The `nexus continue` CLI command uses the same endpoint. | `nexus/cli.py:5631` (`add_parser("continue")`); `:3047-3058` (posts to `/api/narrative/continue`) | true |
| 56-57 | `--choice K --text "..."` sends an edited choice. | `nexus/cli.py:5635-5648` (`--choice` and `--text` arguments); `:3048-3053` (both sent in one payload) | true |
| 57 | The wizard refuses that combination. | `nexus/cli.py:2769-2776` | true |
| 59-60 | While a generation runs, the pane follows phase events on `/ws/narrative?slot=N`. | `ui/client/src/hooks/useNarrativeEngine.ts:361-372` (socket; each message triggers a durable read); route `nexus/api/narrative.py:1623` | true |
| 60-61 | The pane reconciles with the durable session through `GET /api/narrative/active` and `GET /api/narrative/status/{session_id}`. | `ui/client/src/hooks/useNarrativeEngine.ts:217`, `:222`, `:234`; routes `nexus/api/narrative.py:1171`, `:1186` | true |
| 61-62 | A reader who disconnects still finds the finished draft. | `ui/client/src/hooks/useNarrativeEngine.ts:337` and `:354-356` (reconnect and visibility boundaries re-read); the draft is durable at `nexus/api/narrative_generation.py:562` | true |
| 62-63 | The OFFLINE status reflects gateway reachability alone. | `ui/client/src/hooks/useNarrativeEngine.ts:516-517` (OFFLINE only from `backendReachable`), set by the `/health` probe `:404-414` and transport errors `:323-327` | true |

### 2. The Gateway Claims the Slot

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 67 | `continue_narrative` in `nexus/api/narrative.py`. | `nexus/api/narrative.py:861` | true |
| 69 | Step 1 rejects locked slots. | `nexus/api/narrative.py:874` (`require_writable_slot`) | true |
| 69 | Step 1 rejects a request carrying both `choice` and `accept_fate`. | `nexus/api/narrative.py:875-879` | true |
| 70 | Step 1 rejects a model override missing from the registry. | `nexus/api/narrative.py:884-886`; `nexus/config/story_model.py:197-202` (unregistered model raises) | true |
| 70-71 | Step 1 rejects slots still in the new-story wizard. | `nexus/api/narrative.py:900-904` | true |
| 72-73 | Step 2 returns 409 when a supplied `session_id` no longer matches the pending draft, before any session or lease exists. | `nexus/api/narrative.py:906-914`, before the mint at `:916` and the lease at `:917` | true |
| 74-75 | Step 3 mints a session UUID and acquires the slot's durable generation lease (`narrative_lease.py`). | `nexus/api/narrative.py:916-921`; `nexus/api/narrative_lease.py:158` `acquire_generation_lease` | true |
| 75-76 | The lease is the singleton `narrative_generation_lease` row plus a `narrative_generation_sessions` record. | `nexus/api/narrative_lease.py:231` (session insert), `:253` (lease insert with `id = TRUE`) | true |
| 76-77 | A live owner returns 409 with its session id. | `nexus/api/narrative_lease.py:202-206`; `nexus/api/narrative.py:644-651` | true |
| 77-79 | An owner past `[api.narrative_generation] stale_lease_timeout_seconds` is recorded as `GenerationLeaseExpired` and replaced. | `nexus.toml:244`, `:250`; `nexus/api/narrative_lease.py:208-222` (delete and terminal update), `:52` (`GenerationLeaseExpired`) | true |
| 80-81 | Step 4, with a draft pending, records the player's response on it and accepts it through `commit_incubator_to_database_sync`. | `nexus/api/narrative.py:949-958`, `:752-761` (response on the incubator row), `:763-776` (commit) | true |
| 81-82 | Acceptance binds the new session to the accepted chunk in the same transaction. | `nexus/api/commit_handler_sync.py:540-544` (`associate_accepted_parent` inside the commit transaction) | true |
| 82-83 | Without a pending draft, the response is recorded on the committed frontier chunk. | `nexus/api/narrative.py:974-982` | true |
| 83-86 | A numbered `choice`, or `accept_fate` (the first presented choice), resolves to that choice's full text, which the chunk records and generation receives. | `nexus/api/choice_handling.py:262-279` (choice), `:280-286` (`accept_fate` takes choice 1); `nexus/api/narrative.py:589-597` (persisted), `:1036-1040` (passed to generation) | true |
| 86-89 | A `choice` sent with different `user_text` records and generates from that edited text, and its `choice_object` keeps the number with `"edited": true`. | `nexus/api/choice_handling.py:264-273` | true |
| 89 | Unchanged text resolves as the bare choice. | `nexus/api/choice_handling.py:274-278` | true |
| 89-90 | Freeform `user_text` is recorded as written. | `nexus/api/choice_handling.py:288-299` (the trimmed text becomes `choice_text`) | true |
| 91-92 | Step 5 binds the session to its parent chunk and claims the parent's embedding trigger. | `nexus/api/narrative.py:1011-1016`, `:654-677`; `nexus/api/narrative_lease.py:357` `claim_parent_embedding` | true |
| 92-93 | The claim enqueues every playable chunk older than the parent that lacks embeddings (`embeddings.py`). | `nexus/api/narrative_lease.py:399`; `nexus/jobs/embeddings.py:50-59` (`nc.id < parent`, `embedding_generated_at IS NULL`, playable predicate) | true |
| 93-94 | Embedding therefore trails acceptance by one turn. | Follows from the predicate at `nexus/jobs/embeddings.py:55` (the parent itself waits for the next turn's claim) | true |
| 95-96 | Step 6 schedules `generate_narrative_async` (`narrative_generation.py`) as a background task and returns the session id. | `nexus/api/narrative.py:1036-1060`; `nexus/api/narrative_generation.py:148` | true |
| 96-97 | A failure before scheduling releases the lease and records the error on the session. | `nexus/api/narrative.py:1069-1077`, `:702-730`; `nexus/api/narrative_lease.py:559` `abandon_generation` | true |
| 99 | The background task renews the lease every third of the stale timeout. | `nexus/api/narrative_generation.py:205-221` (sleeps `timeout / 3`, then `heartbeat_generation`) | true |
| 100-101 | It records the durable phase: `retrieval`, `assembly`, `writer`, `gaia`, `staging`, then `complete`. | `nexus/api/narrative_generation.py:228`; `nexus/agents/lore/lore.py:375`, `:400`; `nexus/agents/lore/logon_utility.py:1882`; `nexus/api/narrative_generation.py:375`; `nexus/api/narrative_lease.py:515` (`complete`) | true |

The phase list (lines 100-101) is complete and in order: `lore.py:375`
(retrieval) runs before `:400` (assembly), the seats report `writer` then
`gaia` (`logon_utility.py:1882`, called per seat in `_generate_narrative_two_pass`
`:1485-1590`), and `narrative_generation.py:375` (staging) precedes the
terminal update.

### 3. LORE Assembles Context

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 105-106 | Each turn builds a fresh `LORE` (`lore.py`) and closes it afterward. | `nexus/api/narrative_generation.py:292` (built per turn), `:370` (`lore.close()` in `finally`) | true |
| 106-107 | `process_turn` restores the Pass-2 baseline staged when the parent was accepted (`lore_pass_baselines`). | `nexus/agents/lore/lore.py:329`, `:373`; `nexus/memory/manager.py:619-650` | true |
| 107 | It fails loudly if the baseline is missing. | `nexus/memory/manager.py:663` (`MissingPass2BaselineError`) | true |
| 107-108 | It then runs the phases in `turn_cycle.py`. | `nexus/agents/lore/lore.py:378-411`; `nexus/agents/lore/utils/turn_cycle.py:219` | true |
| 108-109 | No language model runs before the storyteller seats. | `nexus/agents/lore/lore.py:378-403` (input, warm slice, entities, deep queries, Orrery dry run, intertitle, assembly) precede `:407` (`call_apex_ai`) | true |
| 109 | Retrieval embeds and reranks raw text. | `nexus/agents/lore/utils/turn_cycle.py:259-270` (raw parent text plus input), `:709`; `nexus/memory/manager.py:1042` (raw input) | true |
| 113-114 | LOGON resolves the storyteller route (model, wire class, provider), which fixes the effective context window and the token budget. | `nexus/agents/lore/utils/turn_cycle.py:315` (`resolve_storyteller_route`), `:320-327` (window and budget); `nexus/agents/lore/logon_utility.py:669` | true |
| 114-115 | `handle_user_input` in `nexus/memory/manager.py` then runs Pass 2. | `nexus/agents/lore/utils/turn_cycle.py:340`; `nexus/memory/manager.py:956` | true |
| 115-117 | Deterministic entity detection reports every known character, place, and faction named in the input as a divergence gap. | `nexus/memory/manager.py:972-978`; `nexus/memory/entity_detector.py:97-158` (loads every character with aliases, place and faction), `:244-269` (each match becomes a gap) | true |
| 117-118 | Pass 2 is skipped for a bare choice number or letter (`[memory] skip_simple_choices`). | `nexus.toml:1170`; `nexus/memory/manager.py:869`, `:1002` | true |
| 118 | Pass 2 is skipped when no budget remains. | `nexus/memory/manager.py:1021` | true |
| 118-120 → 141-143 | Otherwise a raw vector search over the input keeps the results that fit the Pass-2 budget (`[memory] phase2_fraction` of the context window). Now: a raw hybrid search over the input (MEMNON's `query_memory`). | `nexus/memory/manager.py:1042-1046`, `:1077-1090` (keep while within budget), `:498` (`int(window * phase2_fraction)`); `nexus.toml:1168`; `nexus/memory/incremental.py:145` (`query_memory(query=query, k=k, use_hybrid=True)`); `nexus/agents/memnon/memnon.py:1506` (the hybrid strategy runs when `use_hybrid` and hybrid search are both on), `:1620` (rerank); `nexus.toml:1074` (`[memnon.retrieval.hybrid_search] enabled = true`) | corrected |
| 120-121 | An embedder, reranker or search error in that query fails the turn; it is never logged and skipped. | `nexus/memory/manager.py:1042` (no handler); `nexus/memory/incremental.py:145` (`query_memory` with no handler); `nexus/agents/lore/lore.py:421-428` and `nexus/api/narrative_generation.py:330-337` (the phase error fails the turn) | true |
| 125-126 | MEMNON loads a window of up to `[lore.chunk_parameters] warm_slice_initial` playable chunks ending at the parent. | `nexus.toml:314-315`; `nexus/agents/lore/utils/turn_cycle.py:391-393`; `nexus/agents/memnon/memnon.py:1308`, `:1337-1338` (playable predicate, `id <= parent`) | true |
| 126 | Pass-2 additions join as recalled chunks. | `nexus/agents/lore/utils/turn_cycle.py:418`; `nexus/memory/manager.py:1220` (`is_recalled: True`) | true |
| 127 | An empty warm slice is fatal. | `nexus/agents/lore/utils/turn_cycle.py:422-427` | true |
| 131 | Baseline rows cover every character, place, and faction. | `nexus/agents/lore/utils/turn_cycle.py:511`, `:562`, `:582`; `nexus/agents/lore/utils/entity_queries.py:103-114` (all characters), `:242-251` (all places), `:340-347` (all factions) | true |
| 131-132 | Entities referenced in the warm slice are featured with full detail. | `nexus/agents/lore/utils/turn_cycle.py:487-489` (warm-slice chunk ids); `nexus/agents/lore/utils/entity_queries.py:82`, `:220`, `:323` (featured rows with details) | true |
| 132-133 | Featured characters' current locations are featured too. | `nexus/agents/lore/utils/turn_cycle.py:531-558`, `:562-567` | true |
| 133 | The relationships among featured characters are included. | `nexus/agents/lore/utils/turn_cycle.py:593-601` | true |
| 133-134 | All within the limits of `[lore.entity_inclusion]` and its provider overrides. | `nexus.toml:317`, `:328`; `nexus/agents/lore/utils/turn_cycle.py:475-479`; `nexus/agents/lore/utils/entity_inclusion.py:15`, `:48-50` (override by provider name) | true |
| 138-139 | The query is the full parent chunk followed by the current input, never an LLM rewrite. | `nexus/agents/lore/utils/turn_cycle.py:259-270`, `:659-666` | true |
| 139 | `docs/retrieval_query_bakeoff_2026_05_18.md` | Reference; the file exists at `M`. | true |
| 139-140 | MEMNON's `query_memory` (`memnon.py`) classifies the query type. | `nexus/agents/memnon/memnon.py:1438`, `:1484` | true |
| 140-141 | It runs hybrid vector and full-text search (`[memnon.retrieval.hybrid_search]`). | `nexus.toml:1072`; `nexus/agents/memnon/memnon.py:1543`; `nexus/agents/memnon/utils/search.py:73`, `:242`; `nexus/agents/memnon/utils/db_access.py:434` (vector and text scores in one query) | true |
| 142-143 | It reranks with the cross-encoder (`[memnon.retrieval.cross_encoder_reranking]`). | `nexus.toml:1127`; `nexus/agents/memnon/memnon.py:1620` | true |
| 143-144 | MEMNON loads the reranker when LORE builds it. | `nexus/agents/lore/lore.py:256`; `nexus/agents/memnon/memnon.py:229` (`get_or_create_reranker` at construction) | true |
| 144-145 | A missing or broken reranker folder fails the turn at that point, before any query runs. | `nexus/agents/memnon/utils/cross_encoder.py:69-78` (missing or non-directory folder), `:163-167` (load failure); LORE is built inside the failing generation at `nexus/api/narrative_generation.py:292` | true |
| 145-146 | An embedder, reranker or search error in any query fails the turn; no layer returns the unreranked or empty results instead. | `nexus/agents/lore/utils/turn_cycle.py:709` (no handler); `nexus/agents/memnon/memnon.py:1538-1560` (strategy loop) and `:1620` (rerank), no handler; `nexus/agents/memnon/utils/search.py:73-258` (no handler on the hybrid path); `nexus/agents/memnon/utils/db_access.py:503`, `:1086` (`try`/`finally` only); `nexus/agents/memnon/utils/cross_encoder.py:691` (no handler); `nexus/agents/memnon/utils/embedding_manager.py:256`, `:278-283` (encode errors re-raise) | true |
| 150 | With `[orrery] enabled`, behavior packages resolve; otherwise the phase is skipped. | `nexus.toml:346-347`; `nexus/agents/lore/utils/turn_cycle.py:756-763` | true |
| 150-151 | `resolve_dry_run` resolves behavior packages at the parent chunk without canonical writes. | `nexus/agents/orrery/resolver.py:2503` (definition; "without database writes"); `nexus/agents/lore/utils/turn_cycle.py:782` (anchored at the parent through `_orrery_anchor_chunk_id`, `:889`) | true |
| 151-153 | The proposal carries draft resolutions, scene pressures, ambient seeds, joint beats, and scene conditions. | `nexus/agents/orrery/resolver.py:241-259` (`OrreryTickProposal` fields) | true |
| 153-154 | The intertitle (season, episode, scene, world layer, world clock, and the protagonist's location) loads on every turn, independent of Orrery. | `nexus/agents/lore/lore.py:398` (unconditional); `nexus/agents/lore/utils/turn_cycle.py:924-939`, `:856-862` (the selected fields) | true |
| 158-159 | Assembly adds the Orrery bleed menu (earlier off-screen outcomes offered for uptake). | `nexus/agents/lore/utils/turn_cycle.py:950`, `:1054-1057`; candidates are resolutions (`nexus/api/narrative_generation.py:355`); uptake recorded at `nexus/api/commit_handler_sync.py:761` | true |
| 159-160 | Assembly adds the knowledge digest for entities present in the scene when `[orrery.knowledge]` is enabled. | `nexus.toml:500-502`; `nexus/agents/lore/utils/turn_cycle.py:1387`, `:1416` (present roster), `:1059` | true |
| 160 | Assembly adds recent Orrery rulings. | `nexus/agents/lore/utils/turn_cycle.py:953`, `:1065`; `nexus/agents/lore/logon_utility.py:2499` | true |
| 160-161 | Assembly adds the rendered Orrery cards. | `nexus/agents/lore/utils/turn_cycle.py:1012-1025` | true |
| 161-162 | Assembly adds the private writer–Gaia correspondence (`correspondence.py`). | `nexus/agents/lore/utils/turn_cycle.py:1000`; `nexus/memory/manager.py:563-570`; `nexus/memory/correspondence.py:221` | true |
| 162-163 | Warm and retrieved memories are deduplicated against each other and capped by `[lore.render_limits]`. | `nexus.toml:267`; `nexus/agents/lore/utils/turn_cycle.py:1126-1130`; `nexus/agents/lore/utils/scene_order.py:19-51` (one winner per identity across both lanes, retrieved capped) | true |
| 163-164 | LOGON then renders and measures the real request for each seat. | `nexus/agents/lore/utils/turn_cycle.py:1165`; `nexus/agents/lore/logon_utility.py:1769` | true |
| 164-166 | While any seat exceeds its target, the oldest warm chunks are dropped first (never the parent). | `nexus/agents/lore/utils/turn_cycle.py:1173-1174` (any seat over target), `:1203-1210` (oldest first), `:184-195` (the parent is protected) | true |
| 166 | Then the lowest-ranked retrieved passages are dropped. | `nexus/agents/lore/utils/turn_cycle.py:1213-1214` (`pop()` from the score-sorted list, `:133-149`) | true |
| 166-167 | Each dropped chunk is released from Pass-2 state. | `nexus/agents/lore/utils/turn_cycle.py:1244`; `nexus/memory/manager.py:1161` | true |
| 167-168 | A core that cannot fit fails at the final prompt-window guard. | `nexus/agents/lore/logon_utility.py:2159-2173` | true |

The trimming order (lines 164-167) matches the code: the warm loop
(`turn_cycle.py:1203`) runs to exhaustion before the retrieved loop (`:1213`).

### 4. LOGON Runs the Storyteller Seats

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 172-173 | `LogonUtility` composes each seat's prompt from the block manifest in `seat_blocks.py`. | `nexus/agents/lore/logon_utility.py:387`, `:2603` (`SEAT_BLOCKS[manifest_seat]`); `nexus/agents/lore/seat_blocks.py:69` | true |
| 173-175 | Every seat opens with the same scene blocks, from the intertitle through recent narrative. | `nexus/agents/lore/seat_blocks.py:34-42` (`_SHARED_START`), `:69-89` (every seat starts with it) | true |
| 175 | `[apex] turn_pipeline` selects the pipeline. | `nexus.toml:1209`; `nexus/agents/lore/logon_utility.py:452-455`, `:922` | true |
| 177 | `two_pass` is the default. | `nexus.toml:1209` (`turn_pipeline = "two_pass"`) | true |
| 177-179 | The writer seat returns `SkaldWriterWire`: prose, two to four choices, scene and presence deltas, runtime operations, and a private letter to Gaia. | `nexus/agents/logon/skald_wire.py:358-386`; `nexus/agents/lore/logon_utility.py:1523-1527` | true |
| 179-181 | The Gaia seat reads its own rendering of the turn context plus the writer's finished output and letter. | `nexus/agents/lore/logon_utility.py:923-928` (Gaia rendering), `:1531` (`_format_gaia_user_prompt(gaia_turn_prompt, writer)`), `:1415` | true |
| 181-183 | Gaia returns `SkaldGaiaWire`: durable state updates, rulings on the Orrery proposal, new-entity declarations, and a reply letter. | `nexus/agents/logon/skald_wire.py:399-421` | true |
| 183-184 | Gaia uses the story's pinned Gaia model or follows the writer's (`resolve_seat` in `story_model.py`). | `nexus/agents/lore/logon_utility.py:1234`; `nexus/config/story_model.py:143`, `:174-180` | true |
| 185 | `combine_two_pass` merges both halves. | `nexus/agents/logon/skald_wire.py:486`; `nexus/agents/lore/logon_utility.py:1586` | true |
| 186 | `single_pass`: one call returns `SkaldTurnWire`, carrying both halves. | `nexus/agents/logon/skald_wire.py:434`; `nexus/agents/lore/logon_utility.py:945-950` | true |
| 188 | The type `StoryTurnResponse`. | `nexus/agents/logon/apex_schema.py:870` | true |
| 188-189 | The merged wire is hydrated into a `StoryTurnResponse` against the scene's presence baseline and character roster. | `nexus/agents/lore/logon_utility.py:2264-2287` (`reconcile_prose_mentions` with the roster, then `hydrate_skald_turn` with the baseline); `nexus/agents/logon/skald_wire.py:734` | true |
| 189-190 | Validation failures are retried up to `[apex] structured_output_retries` times. | `nexus.toml:1217`; `nexus/agents/lore/logon_utility.py:720`, `:757`, `:771` (budget handed to the provider); `scripts/api_openai.py:561`, `:634`; `scripts/api_anthropic.py:698`, `:754` (the retry loops) | true |
| 190-191 | An exhausted budget or a provider error fails the turn. | `scripts/api_openai.py:634-645`; `scripts/api_anthropic.py:754`; `nexus/agents/lore/lore.py:426-427` (the generation phase re-raises) | true |

### 5. The Draft Is Staged

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 195-198 | `response_to_incubator` (`lore_adapter.py`) maps the response to an incubator row: prose and choices; metadata, entity, and reference updates; the Orrery proposal and bleed offers; Gaia's adjudications and declarations; both letters; the Pass-1 baseline for the next turn; and the generating model. | `nexus/api/lore_adapter.py:134`, `:176-199` | true |
| 199 | `write_to_incubator` (`narrative_generation.py`) then runs four steps. | `nexus/api/narrative_generation.py:472` | true |
| 201-203 | Step 1 dry-runs acceptance validation (`validate_commit_draft_sync` in `draft_validation.py`) inside a savepoint that is always rolled back. | `nexus/api/narrative_generation.py:488-494`; `nexus/api/draft_validation.py:32` | true |
| 204 | Step 2 confirms the session still holds the lease for this parent. | `nexus/api/narrative_generation.py:524-541` | true |
| 205 | Step 3 writes the singleton `incubator` row. | `nexus/api/narrative_generation.py:562` | true |
| 205-206 | A regeneration replaces only the draft it expects and marks that session superseded. | `nexus/api/narrative_generation.py:576-628` (conditional update; `terminal_outcome = 'superseded'` at `:623`) | true |
| 207-208 | Step 4 marks the session complete and releases the lease in the same transaction. | `nexus/api/narrative_generation.py:633`; `nexus/api/narrative_lease.py:452-460`, `:512-528`, `:547` (one commit) | true |
| 208 | That wakes the deferred-work scheduler. | `nexus/api/narrative_lease.py:548-551`; `nexus/jobs/scheduler.py:27-31` | true |
| 210-211 | A failure at any point marks the session `error` with its error class, releases the lease, and emits an `error` event. | `nexus/api/narrative_generation.py:406-432` | true |

The four steps of `write_to_incubator` (lines 201-208) match the code order:
validation `:488`, lease check `:524`, row write `:562`, completion `:633`.

### 6. Review

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 215 | The pending draft appears in the Narrative pane. | `ui/client/src/components/nexus/NarrativePane.tsx:690-700` (pending block); `nexus/api/slot_state.py:333-343` | true |
| 217-218 | Accept: the next `POST /api/narrative/continue` accepts the draft before generating (step 2). | `nexus/api/narrative.py:935-958` (acceptance precedes scheduling at `:1036`) | true |
| 218-219 | `POST /api/narrative/approve` commits it without continuing. | `nexus/api/narrative.py:1333`, `:1418-1427` | true |
| 220-222 | Regenerate: `POST /api/narrative/regenerate` reruns generation from the same parent and player text, with an optional author's note, under a new session. | `nexus/api/narrative.py:1203-1213`, `:1229-1250` (parent and `user_text` from the incubator), `:1257` (new session), `:1274` (note) | true |
| 222-223 | The new session records the draft it set out to replace in `supersedes_session_id` when it acquires the slot. | `nexus/api/narrative.py:1258-1263`; `nexus/api/narrative_lease.py:231-250` | true |
| 223-224 | The pane offers regenerate as a glyph on the pending block while nothing generates. | `ui/client/src/components/nexus/NarrativePane.tsx:395-400` (`canRegenerate` requires `!isGenerating` and a pending session), `:702-736` (glyph inside the pending block) | true |
| 224-225 | The current draft stays until its replacement is staged. | `nexus/api/narrative.py:1305` (`expected_incubator_session`); `nexus/api/narrative_generation.py:576-610` (replaced only on success) | true |
| 225-227 | When the re-roll fails the draft remains, and the failed session's `supersedes_session_id` naming that draft lets the pane report the failure. | `ui/client/src/components/nexus/NarrativePane.tsx:263-268` (`regenerationFailure`), `:793-794` (failure line) | true |
| 228-229 | Discard: `DELETE /api/narrative/incubator` removes the draft and marks its session discarded. | `nexus/api/narrative.py:1659-1680`; `nexus/api/narrative_lease.py:657-661` (`terminal_outcome = 'discarded'`) | true |
| 230-232 | Retry: after a failed generation, `POST /api/narrative/retry` with the failed session id replays the recorded player action, provided that failure is still the latest session and nothing is pending. | `nexus/api/narrative.py:1080`, `:1093-1099`, `:1140`; `nexus/api/narrative_lease.py:99-157` (latest-session, no-incubator and recorded-action fences) | true |

### 7. Acceptance Commits the Turn

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 236-237 | `commit_incubator_to_database_sync` (`commit_handler_sync.py`) runs one transaction. | `nexus/api/commit_handler_sync.py:324`, `:352` (`with conn:` wraps steps 1-12) | true |
| 239-240 → 262-263 | Step 1 locks the incubator row, reruns draft validation, and binds staged name-reveal identities. Now: locks the row, binds the identities, and reruns validation. | `nexus/api/commit_handler_sync.py:367-369` (`FOR UPDATE`), `:387` (bind), `:392` (validation, after the bind) | corrected |
| 241-242 | Step 2 derives chronology from the parent's `chunk_metadata`: the scene number advances, and an episode or season transition plans summary jobs. | `nexus/api/commit_handler_sync.py:415-424` (parent metadata), `:453-457` (`plan_summary_tasks`), `:460` (scene + 1) | true |
| 243 | Step 3 checks declared characters against the identity index. | `nexus/api/commit_handler_sync.py:481-493` | true |
| 244-246 | Step 4 inserts the `narrative_chunks` row (prose plus the enacted choice), marks the session accepted, persists the Pass-1 baseline to `lore_pass_baselines`, and stores both private letters. | `nexus/api/commit_handler_sync.py:512`, `:534`, `:551`, `:564` | true |
| 247-248 | Step 5 inserts `chunk_metadata` with its `SxxEyy_zzz` slug and reads back the accepting chunk's world clock. | `nexus/api/commit_handler_sync.py:574-591`, `:593` | true |
| 249 | Step 6 applies name reveals. | `nexus/api/commit_handler_sync.py:600` | true |
| 249-250 | New-entity declarations create stubs and enqueue Retrograde maturation jobs. | `nexus/api/commit_handler_sync.py:610`; `nexus/agents/orrery/retrograde_maturation.py:197` (stub), `:248` (job) | true |
| 251-252 | Step 7 resolves character, place, and faction references, reconciles roster mentions, and writes the scene's presence roster. | `nexus/api/commit_handler_sync.py:635`, `:683-684` (references), `:642`, `:664` (reconciliation), `:692-714` (roster written) | true |
| 253 | Step 8 applies Gaia's state updates at the accepting chunk's clock. | `nexus/api/commit_handler_sync.py:718-722` (`anchor_world_time=accepting_world_time`) | true |
| 254-257 | Step 9 commits the Orrery tick (`commit_orrery_tick_sync` in `events.py`): the previewed proposal is materialized with Gaia's adjudications applied, then bleed offers and uptake are recorded. | `nexus/api/commit_handler_sync.py:734-740`, `:756`, `:761`; `nexus/agents/orrery/events.py:684`, `:731`, `:810` | true |
| 258-259 | Step 10 seeds character experiences, enqueues experience rendering at scene boundaries, and captures interval state checkpoints. | `nexus/api/commit_handler_sync.py:808`, `:820-821`, `:847` | true |
| 260-261 | Step 11 enqueues correspondence compaction, binds attempt-manifest exposures, and enqueues planned summaries (`summary_triggers.py`). | `nexus/api/commit_handler_sync.py:864`, `:873`, `:876`; `nexus/jobs/compaction.py:19`; `nexus/api/summary_triggers.py:56` | true |
| 262 | Step 12 deletes the incubator row. | `nexus/api/commit_handler_sync.py:883` | true |
| 264-265 | After the commit, the optional presence audit runs and the gateway wakes the scheduler. | `nexus/api/commit_handler_sync.py:903-904` (after the transaction); `nexus/api/narrative.py:787`, `:1452` | true |

The twelve steps match the code order (`:367` through `:883`); the only
inversion was inside step 1, corrected above.

### 8. Deferred Work

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 269-270 | Before starting its scheduler, the gateway checks the production model artifact lock by file list, size and revision. | `nexus/api/narrative.py:129` (before `:135-136`); `nexus/agents/memnon/utils/artifact_manifest.py:731-733` (`hash_files=False`) | true |
| 270 | It refuses startup on drift. | `nexus/agents/memnon/utils/artifact_manifest.py:734-743` (`ArtifactLockError`) | true |
| 270-271 | A process marked `NEXUS_TEST_PROVIDER_ONLY=1` skips this boot check. | `nexus/api/narrative.py:123-127` | true |
| 271-272 | Full sha256 checks run through `nexus models verify`. | `nexus/cli.py:5727` (`add_parser("models")`), `:5737` (the verb `add_parser`, which receives `verify` from the tuple at `:5733`); `nexus/agents/memnon/utils/artifact_manifest.py:971` (`hash_files=True` for verify), `:570` (sha256 compare) | true |
| 272 | Full sha256 checks run through the doctor's `models.artifacts` check. | `nexus/runtime/readiness.py:1452` (registration), `:1100` (`hash_files=True`) | true |
| 274-275 | A gateway started with `NEXUS_SLOT` runs one `SlotScheduler` (`scheduler.py`) for that slot. | `nexus/api/narrative.py:132-136`; `nexus/jobs/scheduler.py:59` | true |
| 275-276 | It holds the durable `deferred_work_scheduler` lease. | `nexus/jobs/scheduler.py:152-185` | true |
| 276 | It observes locked slots without draining them. | `nexus/jobs/scheduler.py:111-150`, `:154` (a locked slot is never acquired) | true |
| 277-278 | Before every job and provider call it waits until no generation lease is live. | `nexus/jobs/scheduler.py:294-341` (`checkpoint`), `:497-499` (installed as the provider gate); `nexus/jobs/gate.py:43-47` (`before_provider_call`) | true |
| 278 | So background inference never competes with a turn. | `nexus/jobs/scheduler.py:294-341` (`checkpoint` waits while a generation lease is live), `:497-499` (installed as the provider gate); `nexus/jobs/gate.py:43-47` (`before_provider_call`) | true |
| 278-279 | Each pass drains, in order, the seven lanes below. | `nexus/jobs/scheduler.py:480-626` | true |
| 281-283 | 1. Orrery promotion (`promote_pending_resolutions_sync` in `worker.py`), by the deterministic thresholds in `[orrery.promote]`. | `nexus/jobs/scheduler.py:502`; `nexus/agents/orrery/worker.py:178`, `:223`, `:795`; `nexus.toml:696` | true |
| 284-285 | 2. The narration outbox records deterministic perceptual descriptors without a provider call. | `nexus/jobs/scheduler.py:510`; `nexus/agents/orrery/worker.py:236`, `:348` | true |
| 285 | `docs/offscreen_narration_retirement.md` | Reference; the file exists at `M`. | true |
| 286 | 3. Character experience rendering and Retrograde maturation. | `nexus/jobs/scheduler.py:517`, `:524` | true |
| 287 | 4. Relationship milestone recovery and correspondence compaction. | `nexus/jobs/scheduler.py:554`, `:555-566`, `:632` | true |
| 288-289 | 5. Episode and season summaries (`summaries.py`), on the model resolved when each job was enqueued. | `nexus/jobs/scheduler.py:579`; `nexus/jobs/summaries.py:16`, `:24` (`persisted_job_model`); `nexus/api/summary_triggers.py:62-76` (model resolved at enqueue) | true |
| 290-291 | 6. Chunk embeddings (`embeddings.py`) with the active MEMNON embedding model, which stamp `embedding_generated_at`. | `nexus/jobs/scheduler.py:590`; `nexus/jobs/embeddings.py:62`, `:76`, `:100-103`; `nexus.toml:950-951` (the one active model) | true |
| 292-293 | 7. Rendered character experience embeddings (`experience_embedding.py`). | `nexus/jobs/scheduler.py:616-626`; `nexus/agents/orrery/experience_embedding.py:82` | true |
| 293-294 | Oldest first and one recollection per checkpoint. | `nexus/agents/orrery/experience_embedding.py:62` (`ORDER BY id`); `nexus/jobs/scheduler.py:617-620` (one checkpoint, `limit=1`) | true |
| 294-295 | Up to `[orrery.experiences].max_embeddings_per_drain` per pass. | `nexus.toml:430`, `:448`; `nexus/jobs/scheduler.py:34-57`, `:616` | true |
| 295-296 | Each stamps `embedding_generated_at` only after every active model's vector lands. | `nexus/agents/orrery/experience_embedding.py:112`; `nexus/agents/memnon/utils/source_embeddings.py:338-345` (all vectors generated, then upserted and stamped together) | true |
| 296-297 | A failure leaves it unstamped for the next pass. | `nexus/agents/memnon/utils/source_embeddings.py:338-345` (generation precedes the write transaction) | true |
| 297-298 | `nexus jobs` reports the backlog as `unembedded_rendered_experiences`. | `nexus/cli.py:5504-5507` (`add_parser("jobs")`), `:5201-5209`; `nexus/agents/orrery/job_queues.py:116` (the backlog count), `:135` (returned under the `unembedded_rendered_experiences` key); `nexus/agents/orrery/experience_embedding.py:70` | true |
| 298-301 | An operator pass (`SlotScheduler.run_pass`) lowers that bound with `experience_embedding_limit`, and `0` skips the lane without loading a model. | `nexus/jobs/scheduler.py:433-440`, `:51-56` (`0` returns before the table is read) | true |
| 301 | As the Orrery queue limits cap their own lanes. | `nexus/jobs/scheduler.py:536-541` (`min(maximum, requested)`) | true |
| 303-304 → 326-327 | The scheduler lease and the compaction, summary, and embedding queues are configured in `[runtime.scheduler]`. Now: the scheduler lease, the promotion limit, and the compaction, summary, and embedding queues. | `nexus.toml:1400-1426`; `nexus/jobs/scheduler.py:76`, `:506` (`self.cfg.promotion_limit`, `nexus.toml:1409`), `:555`, `:601`; `nexus/jobs/narrative_jobs.py:37`, `:59`, `:78` (attempts and lease from the same tables) | corrected |
| 304-305 | The Orrery queues take their limits from their own `[orrery]` tables. | `nexus/jobs/scheduler.py:511`, `:518-523`, `:525-529`, `:55`; `nexus.toml:430`, `:669`, `:809` | true |
| 305-306 → 329 | `python -m nexus.agents.orrery.worker` runs one pass under the same ownership. | `nexus/agents/orrery/worker.py:1002`, `:985`, `:129-135` (`SlotScheduler.run_pass`) | true |

The drain order (lines 281-301) matches `_drain`: promotion `:502`, narration
`:510`, experiences `:517`, maturation `:524`, milestones `:554`, compaction
`:555`, summaries `:579`, chunk embeddings `:590`, experience embeddings
`:616`. The order asked whether the claim scan at `scheduler.py:567-576`
(`SELECT ... FROM narrative_parent_embedding_claims ... LIMIT 1`, then
`enqueue_locked_embeddings`) is a separate drained step or part of item 6. It
is neither: it drains no queue. It enqueues, from the newest parent claim,
every older playable chunk still lacking embeddings (the predicate of section
2 step 5) into the queue that item 6 drains, and it runs between item 4 and
item 5. Item 6 drains that queue at its listed position, so the enumeration of
drains leaves out no drain and puts none out of order. No clause was added.

### Bootstrap Turns

| Line | Clause | Evidence at M | Verdict |
|---|---|---|---|
| 310 | A story's first turn has parent chunk 0. | `nexus/api/narrative.py:1009-1010` (`parent_chunk_id == 0` is bootstrap) | true |
| 310-311 | The new-story wizard posts to the same endpoint. | `ui/client/src/components/NewStoryWizard/InteractiveWizard.tsx:536-543` (`chunk_id: 0` to `/api/narrative/continue`) | true |
| 311 | `generate_bootstrap_narrative` replaces LORE. | `nexus/api/narrative_generation.py:262-280` (bootstrap branch never builds LORE), `:641` | true |
| 311-312 | It reads the setting from `global_variables` and the canonical player character. | `nexus/api/narrative_generation.py:672`, `:681` | true |
| 312-313 | It calls LOGON with the bootstrap schema. | `nexus/api/narrative_generation.py:812-819` (`bootstrap_mode=True`); `nexus/agents/lore/logon_utility.py:2176-2181` (`StorytellerResponseBootstrap`) | true |
| 313 | It stages the result like any other draft. | `nexus/api/narrative_generation.py:844`, `:383` (the same `write_to_incubator`) | true |
| 314 | Acceptance starts at season 1, episode 1, scene 1. | `nexus/api/commit_handler_sync.py:402-413`, `:460` | true |
| 314-315 | No embedding is claimed. | `nexus/api/narrative.py:1015` (`claim_embedding=not is_bootstrap`) | true |

### Verdict Counts

171 rows: 167 `true` (4 of them convention, locator or reference rows), 4
`corrected` (four corrections, one row each), 0 `cut`.

## Corrections (Item 3)

1. **Section 1, lines 47-49 (now 70-72).** Before: "The IRIS Narrative pane
   (`ui/client/src/hooks/useNarrativeEngine.ts`) polls `GET
   /api/slot/{slot}/state` for the newest passage, ...". After: "... reads
   `GET /api/slot/{slot}/state` for the newest passage, ...". Only the verb
   changes. The pane does not poll that route: it is one `useQuery` with no
   refetch interval (`useNarrativeEngine.ts:123-127`; the application client
   disables interval refetch, `ui/client/src/lib/queryClient.ts:48`). It is
   re-read whenever the narrative queries are invalidated (`:133-134`): after
   a submission starts (`:455`) or fails (`:469`), on a terminal transition
   (`:247`, `:280`), when a superseded owner is observed (`:224`), and at each
   boundary (`:336-337`), which runs on mount (`:379`), after a wake gap
   (`:350`), on a return to the tab (`:355-356`) and on each socket open or
   reconnect (`:364`). The corrected clause names none of these occasions, so
   it cannot list some and leave out others. What the pane polls on an
   interval is `/api/narrative/active` and
   `/api/narrative/status/{session_id}` (line 61, true). The corrected clause
   claims no interval, so `queryClient.ts` is not evidence for it and is not a
   source.
2. **Section 7, step 1, lines 239-240 (now 262-263).** Before: "Locks the
   incubator row, reruns draft validation, and binds staged name-reveal
   identities." After: "Locks the incubator row, binds staged name-reveal
   identities, and reruns draft validation." The bind runs at
   `commit_handler_sync.py:387`, before validation at `:392`, so the
   validation sees the bound identities.
3. **Section 8, lines 303-305 (now 326-328).** Before: "The scheduler lease
   and the compaction, summary, and embedding queues are configured in
   `[runtime.scheduler]`; the Orrery queues take their limits from their own
   `[orrery]` tables." After: "The scheduler lease, the promotion limit, and
   the compaction, summary, and embedding queues are configured in
   `[runtime.scheduler]`; the Orrery queues take their limits from their own
   `[orrery]` tables." Only the first clause changes. The Orrery promotion
   lane takes its per-pass limit from `[runtime.scheduler] promotion_limit`
   (`nexus.toml:1409`, `scheduler.py:506`); only its thresholds live in
   `[orrery.promote]`. The second clause keeps its words (row 304-305, true):
   it does not group promotion with the Orrery queues, whose limits come from
   `[orrery]` tables and cap their own lanes (line 301), while the operator's
   promotion limit replaces the configured value instead. The trailing
   sentence was rewrapped onto its own line; its words are unchanged.
4. **Section 3, User Input and Pass 2, lines 118-120 (now 141-143).** Before:
   "... a raw vector search over the input keeps the results that fit the
   Pass-2 budget ...". After: "... a raw hybrid search over the input
   (MEMNON's `query_memory`) keeps the results that fit the Pass-2 budget
   ...". The Pass-2 query is not a vector search alone: it calls
   `query_memory(query=query, k=k, use_hybrid=True)`
   (`nexus/memory/incremental.py:145`), which runs the hybrid vector and
   full-text strategy (`nexus/agents/memnon/memnon.py:1506`, enabled at
   `nexus.toml:1074`) and the cross-encoder rerank (`memnon.py:1620`) that the
   Deep Retrieval section describes. The paragraph's last five lines were
   rewrapped; the body keeps its line count.

No clause was cut and none was added. Every heading and `status: canonical`
are unchanged.

## Sources (Item 4)

No declared source was removed: each of the 30 is cited by a kept row
(`nexus/jobs/gate.py` by line 277-278, `nexus/jobs/narrative_jobs.py` by line
303-304, `nexus/memory/correspondence.py` by line 161-162,
`nexus/api/draft_validation.py` by line 201-203). 23 paths were appended in
the order the body first cites them:

| Added path | Rows that cite it (line at M) |
|---|---|
| `ui/client/src/components/nexus/NarrativePane.tsx` | 47, 49-50, 51-52, 52-55, 215, 223-224, 225-227 |
| `nexus/api/slot_endpoints.py` | 48 |
| `ui/client/src/hooks/useInputDraft.ts` | 49-50, 50-51 |
| `nexus/cli.py` | 55-56, 56-57, 57, 271-272, 297-298 |
| `nexus/memory/entity_detector.py` | 115-117 |
| `nexus/memory/incremental.py` | 118-120, 120-121 |
| `nexus/agents/lore/utils/entity_queries.py` | 131, 131-132 |
| `nexus/agents/lore/utils/entity_inclusion.py` | 133-134 |
| `nexus/agents/memnon/utils/search.py` | 140-141, 145-146 |
| `nexus/agents/memnon/utils/db_access.py` | 140-141, 145-146 |
| `nexus/agents/memnon/utils/cross_encoder.py` | 144-145, 145-146 |
| `nexus/agents/memnon/utils/embedding_manager.py` | 145-146 |
| `nexus/agents/orrery/resolver.py` | 150-151, 151-153 |
| `nexus/agents/lore/utils/scene_order.py` | 162-163 |
| `nexus/agents/logon/apex_schema.py` | 188 |
| `scripts/api_openai.py` | 189-190, 190-191 |
| `scripts/api_anthropic.py` | 189-190, 190-191 |
| `nexus/agents/orrery/retrograde_maturation.py` | 249-250 |
| `nexus/agents/memnon/utils/artifact_manifest.py` | 269-270, 270, 271-272 |
| `nexus/runtime/readiness.py` | 272 |
| `nexus/agents/memnon/utils/source_embeddings.py` | 295-296, 296-297 |
| `nexus/agents/orrery/job_queues.py` | 297-298 |
| `ui/client/src/components/NewStoryWizard/InteractiveWizard.tsx` | 310-311 |

The order predicted six of these (`slot_endpoints.py`, `NarrativePane.tsx`,
`useInputDraft.ts`, `cli.py`, `resolver.py`, `apex_schema.py`). The other 17
come from clauses that state how a callee outside the declared set behaves
(the coverage of the entity baseline and of entity detection, the
no-swallowing chain through the retrieval layers, the retry loop, the
artifact boot check, all-or-nothing embedding stamps, the `nexus jobs`
backlog key) and from the
boot-check paragraph and the bootstrap clause, whose performing lines no
declared source holds.

**In-flight orders.** `grep -l <path> /Users/pythagor/nexus/temp/orders_2026_10_07/*.md`
for the 17 unpredicted paths names these orders: 817-S3 (`entity_queries.py`,
`retrograde_maturation.py`; ledger rows only, landed); 812-S3 (`cross_encoder.py`,
`embedding_manager.py`, `artifact_manifest.py`, `readiness.py`; landed, and
it re-verifies this document); 812-S4a (`cross_encoder.py`, `db_access.py`,
`embedding_manager.py`, `artifact_manifest.py`, `source_embeddings.py`; its
item 8 re-verifies this document); 820-S2 (`cross_encoder.py`,
`embedding_manager.py`, `artifact_manifest.py`; in the header's list for
`nexus/cli.py`; landed as #1125); 803-S1, 803-S6, 811-S3a
and 822-S1 (`readiness.py`; all landed, 822-S1 re-verifies); 809-S1, 838-S1,
840-S2, 783-S1a (`retrograde_maturation.py`; all landed); 802-S1b and 811-S3a
(`api_anthropic.py`, `api_openai.py`; landed, and 811-S3a names the provider
shims out of scope); 776-S1b and 776-S6 (`InteractiveWizard.tsx`; landed).
`search.py` appears only in `812-S4a.md:86`, as out-of-scope work deferred to
812-S4b, an order not yet drafted. `entity_detector.py`, `incremental.py`,
`entity_inclusion.py`, `scene_order.py` and `job_queues.py` appear in no
order. Every order that edits an added path
without re-verifying this document has landed: 820-S2 (#1125), 806-S1
(#1118) and 815-S2 (#1127) are ancestors of M, as are 815-S3 (#1132), 815-S5
(#1133), 803-S6 (#1131), 776-S1b (#1137) and 776-S3 (#1139). No open order is
bound.
`gh pr list --state open` was empty when this was written.

**Landing note: the future 812-S4b.** `812-S4a.md:86` defers to 812-S4b
edits to `search.py`, `db_access.py` and `source_embeddings.py`, and to
`embedding_manager.py` beyond 812-S4a's one docstring. All four are now
declared turn-flow sources, so the 812-S4b draft must carry the duty to
re-verify this document and then `AGENTS.md`.

## Stamps (Item 5)

`docs/turn_flow_sequence.md` `verified_commit`:
`f073b3711a3bd0273943c9defad85913452fd00b` →
`a01c162f1e4daaf5009a9bba7397ae4065a8614b`.

## The Red Run

With items 2 to 5 committed (`aa29e2e0`) and `AGENTS.md` not yet re-stamped,
the freshness test fails exactly as the order predicts:

```
$ PYTHONPATH=$PWD $PY -m pytest -vv tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit - AssertionError: assert ['AGENTS.md: docs/turn_flow_sequence.md changed since the merge base a01c162f1e4d without a re-stamped verified_commit'] == []

  Left contains one more item: 'AGENTS.md: docs/turn_flow_sequence.md changed since the merge base a01c162f1e4d without a re-stamped verified_commit'

  Full diff:
  - []
  + [
  +     'AGENTS.md: docs/turn_flow_sequence.md changed since the merge base '
  +     'a01c162f1e4d without a re-stamped verified_commit',
  + ]
======================== 1 failed, 5 warnings in 2.20s =========================
```

After item 6 the same test passes (see the gate tails below).

## AGENTS.md Clauses Re-Checked (Item 6)

`AGENTS.md` was last re-verified whole at `41783c1d` (817-S2a) and later
re-stamped by single-change passes, most recently to `f073b371`. The order
names `364fef4b` as the base of this check:

```
$ AS=(<the 34 AGENTS.md sources>)
$ git log --first-parent --oneline 364fef4b..a01c162f -- $AS
493902a1 Client Plane Awareness; Retire the No-Op slot/select (824-S1, 824-S5) (#1147)
21cf9353 Typed Settings Response; Fresh Slots Store No Model Pin (809-S3b, 809-S7a) (#1146)
954e8dc3 Trait Derivation on the Wait Screen (776-S6) (#1142)
6853e529 Move Runtime-Imported Setup and Migration Modules Into nexus/ (811-S3a) (#1141)
fa1d20e1 Refuse Place Stubs Without a Point; Producers Author the Point (840-S2) (#1138)
bab4b68b World-Hour Predicates, Event Times in the Read Model, and a World-Time Horizon (778-S3) (#1134)
75699431 Typed Settings for the Remaining Product Dict Readers (809-S1) (#1130)
f073b371 Merge pull request #1128 from pythagorakase/claude/812-models-plan-fetch
be9ce348 Merge pull request #1124 from pythagorakase/claude/836-unified-references
9c8f1050 Merge pull request #1123 from pythagorakase/claude/816-test-provider-database
6f338c55 Merge pull request #1122 from pythagorakase/claude/785-travel-trio
7399bd99 Merge pull request #1120 from pythagorakase/claude/812-one-embedder
d476db91 Merge pull request #1118 from pythagorakase/claude/806-receipt-store
dbc1f392 Merge pull request #1116 from pythagorakase/claude/840-natural-earth
91678330 Merge pull request #1117 from pythagorakase/claude/822-story-identity
fc6f7b45 Refuse a NULL story-clock base and fix base_timestamp at genesis (778-S1b, migration 144) (#1114)
8f4ad48e Runtime maturation follows the story's genesis strangeness (#838 S1) (#1111)
4f1d1b81 Delete the uncalled MEMNON read-only SQL executor; keep the documented unused labels (#813 S2, S3) (#1108)
2e8b415c Data clones migrate before they pin (#1083) (#1105)
c58f86d2 Remove the dead wizard streaming endpoint (#1081) (#1103)
```

20 commits. The `AGENTS.md` sources each one changed (`git diff --name-only
<c>^1 <c> -- $AS`):

| Commit | Changed `AGENTS.md` sources |
|---|---|
| `493902a1` | `nexus/api/narrative.py` |
| `21cf9353` | `nexus.toml` |
| `954e8dc3` | `docs/turn_flow_sequence.md` (stamp only) |
| `6853e529` | `CLAUDE.md` |
| `fa1d20e1` | `nexus/agents/logon/apex_schema.py` |
| `bab4b68b` | `nexus/agents/lore/utils/turn_cycle.py` |
| `75699431` | `nexus/agents/orrery/worker.py`, `nexus/jobs/scheduler.py`, `tests/pg_fixtures.py` |
| `f073b371` | `docs/turn_flow_sequence.md`, `nexus/api/narrative.py` |
| `be9ce348` | `docs/turn_flow_sequence.md` (stamp only) |
| `9c8f1050` | `docs/agent_workflow.md`, `docs/turn_flow_sequence.md`, `nexus.toml`, `tests/conftest.py`, `tests/pg_fixtures.py` |
| `6f338c55` | `docs/turn_flow_sequence.md`, `nexus.toml` |
| `7399bd99` | `docs/turn_flow_sequence.md`, `nexus.toml`, `nexus/agents/memnon/memnon.py` |
| `d476db91` | `tests/conftest.py` |
| `dbc1f392` | `CLAUDE.md` |
| `91678330` | `docs/turn_flow_sequence.md`, `tests/pg_fixtures.py` |
| `fc6f7b45` | `tests/pg_fixtures.py`, `tests/test_lore/conftest.py` |
| `8f4ad48e` | `nexus.toml` |
| `4f1d1b81` | `CLAUDE.md`, `nexus/agents/memnon/memnon.py` |
| `2e8b415c` | `tests/pg_fixtures.py` |
| `c58f86d2` | `docs/turn_flow_sequence.md`, `nexus.toml` |

The diffs of every listed commit against these sources were read, including
the three the order names (`2e8b415c`, `4f1d1b81`, `8f4ad48e`). The `CLAUDE.md`
changes rename the Python-migration allowlist location, add
`natural_earth_features` to the template seed list, and rewrite the
`get_schema_summary` note; `docs/agent_workflow.md` adds the legacy `mock`
target to the dbname audit; `tests/conftest.py` adds receipt isolation and
the unrouted TEST provider database; `tests/test_lore/conftest.py` seeds a
story base. None of these touches what an `AGENTS.md` clause says. Each
`AGENTS.md` clause that a changed source backs (per the "AGENTS.md, Sentence by
Sentence" table of `docs/qa/817-freshness-gate/verification.md`), checked at
`M`:

| AGENTS.md line | Clause | Changed source | Evidence at M | Verdict |
|---|---|---|---|---|
| 44 | `lore` orchestrates each turn (`lore.py`, `utils/turn_cycle.py`). | `turn_cycle.py` | `nexus/agents/lore/lore.py:198`, `:329`; `nexus/agents/lore/utils/turn_cycle.py:219`, `:284`, `:351`, `:441`, `:639`, `:749` | true |
| 44 | `logon` holds the storyteller wire schemas and validators. | `apex_schema.py` | `nexus/agents/logon/apex_schema.py:1-3` (structured output schema), `:870`; `nexus/agents/logon/skald_wire.py:358` | true |
| 44 | `memnon` handles retrieval. | `memnon.py` | `nexus/agents/memnon/memnon.py:1-8`, `:1438` `query_memory` | true |
| 44 | `orrery` is the deterministic off-screen world engine. | `worker.py` | `nexus/agents/orrery/worker.py:1-5` ("deterministic off-screen record worker"), `:178`, `:236` | true |
| 44 | The FastAPI gateway and its turn routes live in `nexus/api/` (`narrative.py`). | `narrative.py` | `nexus/api/narrative.py:146` (`app = FastAPI(...)`), `:851-852` (`/api/narrative/continue`), `:1080` (`/api/narrative/retry`) | true |
| 44 | Deferred work runs under `nexus/jobs/`. | `scheduler.py` | `nexus/jobs/scheduler.py:1` ("One durable, preemptible recovery owner for each slot database"), `:59` `SlotScheduler` | true |
| 44 | `docs/turn_flow_sequence.md` traces the turn cycle through the code. | `docs/turn_flow_sequence.md` | Re-read against the corrected document: `docs/turn_flow_sequence.md:60` "# The Turn Cycle", its 53 file-level sources, and the clause table above (every clause true or corrected at `M`) | true |
| 44 | Runtime settings live in `nexus.toml`. | `nexus.toml`, `CLAUDE.md` | `CLAUDE.md:18`; `nexus.toml` exists | true |
| 47 | `CLAUDE.md` is the canonical command reference, including the PostgreSQL test gate, migrations and pre-commit hooks. | `CLAUDE.md` | `CLAUDE.md:9` (full gate), `:20-34` (pre-commit hooks), `:64-90` (migrations) | true |
| 47 | Run the suite with `poetry run pytest`; format, type-check and lint with Black, mypy and flake8. | `CLAUDE.md` | `CLAUDE.md:8`, `:12-14` | true |
| 50 | Adopt Black (88 columns), group and alphabetize imports, PascalCase classes and snake_case elsewhere, docstrings and type hints. | `CLAUDE.md` | `CLAUDE.md:38-41`, `:44` | true |
| 50 | Load configurable values from `nexus.toml` instead of literals. | `nexus.toml`, `CLAUDE.md` | `CLAUDE.md:18`; `nexus.toml` | true |
| 50 | Follow the structured-output practices in `CLAUDE.md` and prefer Pydantic models. | `CLAUDE.md` | `CLAUDE.md:42`, `:240-242` | true |
| 53 | Reuse fixtures from `tests/test_lore/conftest.py`, and `tests/pg_fixtures.py` for PostgreSQL. | `tests/test_lore/conftest.py`, `tests/pg_fixtures.py` | `tests/test_lore/conftest.py:28-29`, `:37-38`, `:54`; `tests/pg_fixtures.py:1` ("Shared PostgreSQL helpers for disposable integration-test databases") | true |
| 53 | Tests that need PostgreSQL carry the `requires_postgres` marker and run only with `NEXUS_RUN_POSTGRES=1`. | `tests/conftest.py` | `pytest.ini:6`; `tests/conftest.py:334-338` (skip unless set), `:129-139` (an unmarked connection fails) | true |
| 53 | Prefer real code paths and real API calls over mocks. | `CLAUDE.md` | `CLAUDE.md:189` | true |
| 56 | Follow the autonomous branch/PR/review workflow in `docs/agent_workflow.md`. | `docs/agent_workflow.md` | `docs/agent_workflow.md:1-8` | true |
| 56 | PRs note any updates to `nexus.toml` or database schema. | `nexus.toml` | Convention. | true |
| 59 | `NEXUS_template` is the canonical schema reference, and the old `NEXUS` database is deprecated. | `CLAUDE.md` | `CLAUDE.md:58` | true |
| 59 | Align local LLM endpoints with the models referenced in `nexus.toml`. | `nexus.toml` | `nexus.toml:56-60` (`[global.model.api_models.local]` and its models) | true |

Every clause is true at `M`. `AGENTS.md`'s `verified_commit` moves from
`f073b3711a3bd0273943c9defad85913452fd00b` to
`a01c162f1e4daaf5009a9bba7397ae4065a8614b`; no other line of `AGENTS.md`
changes.

## Second Range (Item 7)

Before pushing, `git fetch origin` left `origin/main` at `a01c162f`, the
merge base already used above, so there was no second range, no merge and no
conflicted clause.

## Gate Tails

All at `40e7ed6f` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`
unset; every command prefixed `nice -n 15`. The one-minute load read 4.5 before
the PostgreSQL run.

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 5.79s

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
147 passed in 8.71s

$ PYTHONPATH=$PWD $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3196 passed, 678 skipped, 8 warnings in 622.11s (0:10:22)

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 45.88s

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
54 passed, 5 warnings in 10.94s

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.

$ git diff --name-only origin/main...HEAD
AGENTS.md
docs/qa/817-turn-flow-reverify/verification.md
docs/turn_flow_sequence.md
```

The offline pieces skip their PostgreSQL tests by design (no
`NEXUS_RUN_POSTGRES`). Black, flake8 and mypy were not run: this branch
changes no Python file.

## Review-Fix Tails

The review round (`e436d121`) changed only `docs/turn_flow_sequence.md` (one
added source, `job_queues.py`; the `NarrativePane.tsx` and `slot_endpoints.py`
sources swapped into first-citation order; section 1's verb-only correction)
and this file. `tests/test_doc_front_matter.py` is the only test that reads
either file, so these runs cover the round; the offline-suite tails above
stand. All at `e436d121` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset; every pytest command prefixed `nice -n 15`. The one-minute
load read 12.55 before the PostgreSQL run.

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 5.62s

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
147 passed in 8.41s

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.

$ git diff --name-only origin/main...HEAD
AGENTS.md
docs/qa/817-turn-flow-reverify/verification.md
docs/turn_flow_sequence.md
```

`git fetch origin` left `origin/main` at `a01c162f`, so both stamps stay at
the merge base and there is still no second range.

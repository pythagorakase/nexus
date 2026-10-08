---
status: canonical
sources:
  - ui/client/src/hooks/useNarrativeEngine.ts
  - ui/client/src/lib/narrative-api.ts
  - nexus/api/slot_state.py
  - nexus/api/narrative.py
  - nexus/api/choice_handling.py
  - nexus/api/narrative_lease.py
  - nexus/api/narrative_generation.py
  - nexus/agents/lore/lore.py
  - nexus/agents/lore/utils/turn_cycle.py
  - nexus/memory/manager.py
  - nexus/memory/correspondence.py
  - nexus/agents/memnon/memnon.py
  - nexus/agents/lore/logon_utility.py
  - nexus/agents/lore/seat_blocks.py
  - nexus/agents/logon/skald_wire.py
  - nexus/config/story_model.py
  - nexus/api/lore_adapter.py
  - nexus/api/draft_validation.py
  - nexus/api/commit_handler_sync.py
  - nexus/agents/orrery/events.py
  - nexus/api/summary_triggers.py
  - nexus/jobs/scheduler.py
  - nexus/jobs/gate.py
  - nexus/jobs/compaction.py
  - nexus/jobs/summaries.py
  - nexus/jobs/embeddings.py
  - nexus/jobs/narrative_jobs.py
  - nexus/agents/orrery/worker.py
  - nexus/agents/orrery/experience_embedding.py
  - nexus.toml
verified_commit: "afd034f360e625f8bc4ffa8a717dda28422b19c7"
---

# The Turn Cycle

One turn takes one player action to one pending draft, and the next action
accepts that draft into the story. Nothing a turn generates becomes part of the
story before acceptance: the draft waits in the slot's single-row `incubator`
until the player moves on. The code paths in the front matter are
authoritative; this document is their map.

## 1. The Player Acts

The IRIS Narrative pane (`ui/client/src/hooks/useNarrativeEngine.ts`) polls
`GET /api/slot/{slot}/state` for the newest passage, which is the pending draft
when one exists, and its choices. Selecting a choice, by click or number key,
only loads its text into the reader's draft, which remembers the choice while
the player edits the text and forgets it once the text is cleared. Enter or the
send glyph commits: `continueNarrative` (`ui/client/src/lib/narrative-api.ts`)
posts `slot`, the draft as `choice` plus `user_text` (one edited-choice
payload) or as freeform `user_text` alone, and any pending draft's `session_id`
to `POST /api/narrative/continue`. The `nexus continue` CLI command uses the
same endpoint; `--choice K --text "..."` sends an edited choice (the wizard
refuses that combination).

While a generation runs, the pane follows phase events on
`/ws/narrative?slot=N` and reconciles with the durable session through
`GET /api/narrative/active` and `GET /api/narrative/status/{session_id}`, so a
reader who disconnects still finds the finished draft. The OFFLINE status
reflects gateway reachability alone.

## 2. The Gateway Claims the Slot

`continue_narrative` in `nexus/api/narrative.py`:

1. Rejects locked slots, a request carrying both `choice` and `accept_fate`,
   a model override missing from the registry, and slots still in the
   new-story wizard.
2. Returns 409 when a supplied `session_id` no longer matches the pending
   draft, before any session or lease exists.
3. Mints a session UUID and acquires the slot's durable generation lease
   (`nexus/api/narrative_lease.py`): the singleton `narrative_generation_lease`
   row plus a `narrative_generation_sessions` record. A live owner returns 409
   with its session id; an owner past `[api.narrative_generation]
   stale_lease_timeout_seconds` is recorded as `GenerationLeaseExpired` and
   replaced.
4. With a draft pending, records the player's response on it and accepts it
   through `commit_incubator_to_database_sync` (step 7), binding the new
   session to the accepted chunk in the same transaction. Without a pending
   draft, the response is recorded on the committed frontier chunk. A
   numbered `choice`, or `accept_fate` (which takes the first presented
   choice), resolves to that choice's full text, which the chunk records and
   generation receives as the player's input. A `choice` sent with different
   `user_text` (`nexus/api/choice_handling.py`) records and generates from that
   edited text instead, and its `choice_object` keeps the number with
   `"edited": true`; unchanged text resolves as the bare choice. Freeform
   `user_text` is recorded as written.
5. Binds the session to its parent chunk and claims the parent's embedding
   trigger, which enqueues every playable chunk older than the parent that
   lacks embeddings (`nexus/jobs/embeddings.py`). Embedding therefore trails
   acceptance by one turn.
6. Schedules `generate_narrative_async` (`nexus/api/narrative_generation.py`)
   as a background task and returns the session id. A failure before
   scheduling releases the lease and records the error on the session.

The background task renews the lease every third of the stale timeout and
records the durable phase: `retrieval`, `assembly`, `writer`, `gaia`,
`staging`, then `complete`.

## 3. LORE Assembles Context

Each turn builds a fresh `LORE` (`nexus/agents/lore/lore.py`) and closes it
afterward. `process_turn` restores the Pass-2 baseline staged when the parent
was accepted (`lore_pass_baselines`), failing loudly if it is missing, then
runs the phases in `nexus/agents/lore/utils/turn_cycle.py`. No language model
runs before the storyteller seats; retrieval embeds and reranks raw text.

### User Input and Pass 2

LOGON resolves the storyteller route (model, wire class, provider), which fixes
the effective context window and the token budget. `handle_user_input` in
`nexus/memory/manager.py` then runs Pass 2: deterministic entity detection
reports every known character, place, and faction named in the input as a
divergence gap. Unless the input is a bare choice number or letter
(`[memory] skip_simple_choices`) or no budget remains, a raw vector search over
the input keeps the results that fit the Pass-2 budget (`[memory]
phase2_fraction` of the context window). An embedder, reranker or search error
in that query fails the turn; it is never logged and skipped.

### Warm Slice

MEMNON loads a window of up to `[lore.chunk_parameters] warm_slice_initial`
playable chunks ending at the parent. Pass-2 additions join as recalled chunks.
An empty warm slice is fatal.

### Entity Dossiers

Baseline rows cover every character, place, and faction. Entities referenced
in the warm slice are featured with full detail, together with featured
characters' current locations and the relationships among them, within the
limits of `[lore.entity_inclusion]` and its provider overrides.

### Deep Retrieval

The query is the full parent chunk followed by the current input, never an
LLM rewrite (`docs/retrieval_query_bakeoff_2026_05_18.md`). MEMNON's
`query_memory` (`nexus/agents/memnon/memnon.py`) classifies the query type,
runs hybrid vector and full-text search (`[memnon.retrieval.hybrid_search]`),
and reranks with the cross-encoder
(`[memnon.retrieval.cross_encoder_reranking]`). MEMNON loads the reranker when
LORE builds it, so a missing or broken reranker folder fails the turn at that
point, before any query runs. An embedder, reranker or search error in any
query fails the turn; no layer returns the unreranked or empty results instead.

### Orrery Preview and Intertitle

With `[orrery] enabled`, `resolve_dry_run` resolves behavior packages at the
parent chunk without canonical writes. The resulting proposal carries draft
resolutions, scene pressures, ambient seeds, joint beats, and scene
conditions. The intertitle (season, episode, scene, world layer, world clock,
and the protagonist's location) loads on every turn, independent of Orrery.

### Payload Assembly and Trimming

Assembly adds the Orrery bleed menu (earlier off-screen outcomes offered for
uptake), the knowledge digest for entities present in the scene when
`[orrery.knowledge]` is enabled, recent Orrery rulings, the rendered Orrery
cards, and the private writer–Gaia correspondence
(`nexus/memory/correspondence.py`). Warm and retrieved memories are
deduplicated against each other and capped by `[lore.render_limits]`. LOGON
then renders and measures the real request for each seat. While any seat
exceeds its target, the oldest warm chunks are dropped first (never the
parent), then the lowest-ranked retrieved passages, and each dropped chunk is
released from Pass-2 state. A core that cannot fit fails at the final
prompt-window guard.

## 4. LOGON Runs the Storyteller Seats

`LogonUtility` (`nexus/agents/lore/logon_utility.py`) composes each seat's
prompt from the block manifest in `nexus/agents/lore/seat_blocks.py`; every
seat opens with the same scene blocks, from the intertitle through recent
narrative. `[apex] turn_pipeline` selects the pipeline:

- **`two_pass`** (default). The writer seat returns `SkaldWriterWire`
  (`nexus/agents/logon/skald_wire.py`): prose, two to four choices, scene and
  presence deltas, runtime operations, and a private letter to Gaia. The Gaia
  seat then reads its own rendering of the turn context plus the writer's
  finished output and letter, and returns `SkaldGaiaWire`: durable state
  updates, rulings on the Orrery proposal, new-entity declarations, and a
  reply letter. Gaia uses the story's pinned Gaia model or follows the
  writer's (`resolve_seat` in `nexus/config/story_model.py`).
  `combine_two_pass` merges both halves.
- **`single_pass`**. One call returns `SkaldTurnWire`, carrying both halves.

The merged wire is hydrated into a `StoryTurnResponse` against the scene's
presence baseline and character roster. Validation failures are retried up to
`[apex] structured_output_retries` times; an exhausted budget or a provider
error fails the turn.

## 5. The Draft Is Staged

`response_to_incubator` (`nexus/api/lore_adapter.py`) maps the response to an
incubator row: prose and choices; metadata, entity, and reference updates; the
Orrery proposal and bleed offers; Gaia's adjudications and declarations; both
letters; the Pass-1 baseline for the next turn; and the generating model.
`write_to_incubator` (`nexus/api/narrative_generation.py`) then:

1. Dry-runs acceptance validation (`validate_commit_draft_sync` in
   `nexus/api/draft_validation.py`) inside a savepoint that is always rolled
   back.
2. Confirms the session still holds the lease for this parent.
3. Writes the singleton `incubator` row. A regeneration replaces only the draft
   it expects and marks that session superseded.
4. Marks the session complete and releases the lease in the same transaction,
   which wakes the deferred-work scheduler.

A failure at any point marks the session `error` with its error class,
releases the lease, and emits an `error` event.

## 6. Review

The pending draft appears in the Narrative pane. From there:

- **Accept.** The next `POST /api/narrative/continue` accepts the draft before
  generating (step 2). `POST /api/narrative/approve` commits it without
  continuing.
- **Regenerate.** `POST /api/narrative/regenerate` reruns generation from the
  same parent and player text, with an optional author's note, under a new
  session, which records the draft it set out to replace in
  `supersedes_session_id` when it acquires the slot. The pane offers it as a
  glyph on the pending block while nothing generates. The current draft stays
  until its replacement is staged; when the re-roll fails the draft remains,
  and the failed session's `supersedes_session_id` naming that draft lets the
  pane report the failure.
- **Discard.** `DELETE /api/narrative/incubator` removes the draft and marks
  its session discarded.
- **Retry.** After a failed generation, `POST /api/narrative/retry` with the
  failed session id replays the recorded player action, provided that failure
  is still the latest session and nothing is pending.

## 7. Acceptance Commits the Turn

`commit_incubator_to_database_sync` (`nexus/api/commit_handler_sync.py`) runs
one transaction:

1. Locks the incubator row, reruns draft validation, and binds staged
   name-reveal identities.
2. Derives chronology from the parent's `chunk_metadata`: the scene number
   advances, and an episode or season transition plans summary jobs.
3. Checks declared characters against the identity index.
4. Inserts the `narrative_chunks` row (prose plus the enacted choice), marks
   the session accepted, persists the Pass-1 baseline to `lore_pass_baselines`,
   and stores both private letters.
5. Inserts `chunk_metadata` with its `SxxEyy_zzz` slug and reads back the
   accepting chunk's world clock.
6. Applies name reveals. New-entity declarations create stubs and enqueue
   Retrograde maturation jobs.
7. Resolves character, place, and faction references, reconciles roster
   mentions, and writes the scene's presence roster.
8. Applies Gaia's state updates at the accepting chunk's clock.
9. Commits the Orrery tick (`commit_orrery_tick_sync` in
   `nexus/agents/orrery/events.py`): the previewed proposal is materialized
   with Gaia's adjudications applied, then bleed offers and uptake are
   recorded.
10. Seeds character experiences, enqueues experience rendering at scene
    boundaries, and captures interval state checkpoints.
11. Enqueues correspondence compaction, binds attempt-manifest exposures, and
    enqueues planned summaries (`nexus/api/summary_triggers.py`).
12. Deletes the incubator row.

After the commit, the optional presence audit runs and the gateway wakes the
scheduler.

## 8. Deferred Work

A gateway started with `NEXUS_SLOT` runs one `SlotScheduler`
(`nexus/jobs/scheduler.py`) for that slot. It holds the durable
`deferred_work_scheduler` lease, observes locked slots without draining them,
and before every job and provider call waits until no generation lease is
live, so background inference never competes with a turn. Each pass drains, in
order:

1. Orrery promotion (`promote_pending_resolutions_sync` in
   `nexus/agents/orrery/worker.py`), by the deterministic thresholds in
   `[orrery.promote]`.
2. The narration outbox, which records deterministic perceptual descriptors
   without a provider call (`docs/offscreen_narration_retirement.md`).
3. Character experience rendering and Retrograde maturation.
4. Relationship milestone recovery and correspondence compaction.
5. Episode and season summaries (`nexus/jobs/summaries.py`), on the model
   resolved when each job was enqueued.
6. Chunk embeddings (`nexus/jobs/embeddings.py`) with the active MEMNON
   embedding model, which stamp `embedding_generated_at`.
7. Rendered character experience embeddings
   (`nexus/agents/orrery/experience_embedding.py`), oldest first and one
   recollection per checkpoint, up to
   `[orrery.experiences].max_embeddings_per_drain` per pass. Each stamps
   `embedding_generated_at` only after every active model's vector lands; a
   failure leaves it unstamped for the next pass. `nexus jobs` reports the
   backlog as `unembedded_rendered_experiences`. An operator pass
   (`SlotScheduler.run_pass`) lowers that bound with
   `experience_embedding_limit`, and `0` skips the lane without loading a
   model, as the Orrery queue limits cap their own lanes.

The scheduler lease and the compaction, summary, and embedding queues are
configured in `[runtime.scheduler]`; the Orrery queues take their limits from
their own `[orrery]` tables. `python -m nexus.agents.orrery.worker` runs one
pass under the same ownership.

## Bootstrap Turns

A story's first turn has parent chunk 0. The new-story wizard posts to the
same endpoint, but `generate_bootstrap_narrative` replaces LORE: it reads the
setting from `global_variables` and the canonical player character, calls
LOGON with the bootstrap schema, and stages the result like any other draft.
Acceptance starts at season 1, episode 1, scene 1, and no embedding is
claimed.

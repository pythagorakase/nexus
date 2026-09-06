# 01 User Input
1. Simple chat-like interface within Terminal-based UI displays recent narrative in markdown format. (See `gui_mockup.rtf`)
2. User inputs next passage.

# 02 Warm Context
1. `LORE` retrieves recent narrative chunks (warm slice) from the database.
2. If a parent/target chunk is known, it is anchored first and marked as the
   target for raw-text retrieval.
3. Phase metadata records chunk ids; no local LLM analysis runs here.

# 03 World State Report - Programmatic Entity Queries
1. `LORE` queries character, location, and faction baselines and featured dossiers
   using `[lore.entity_inclusion]` in `nexus.toml`.
2. Warm-slice references select featured characters; the canonical player is
   always featured.
3. Relationships between featured characters are included when configured.
4. Featured-character locations receive their location dossiers.
5. Limits include `warm_slice_lookback_chunks`, `max_characters_from_warm_slice`,
   and `max_locations_from_warm_slice`; `include_all_relationships` controls the
   relationship query. Provider overrides retain the existing budget behavior.
6. The nonexistent legacy `events` and `threats` tables are no longer queried.
   Canonical Orrery `world_events` remain on their existing dedicated paths.

# 04 Deep Queries
1. The full target/latest chunk text is used as the first retrieval query when available.
2. MEMNON's QueryAnalyzer classifies the raw chunk query for optimal search strategy.
3. Queries are sent to `MEMNON` for retrieval. If no raw text is available, the
   phase skips instead of summoning a local LLM fallback.

# 05 Cold Distillation
1. For each query, `MEMNON` performs hybrid search combining vector similarity and text search.
2. Results are reranked using cross-encoder models to narrow candidate pool.
3. Top results suitable for context payload are selected.

# 06 Payload Assembly
1. `LORE` calculates the API payload budget from the current Apex AI model's TPM limit, and subtracting variables it cannot control and must include regardless:
	- user input
	- system prompt
2. `LORE` dynamically determines percentage allotment for each component of API call within parameters. These parameters may be adjusted frequently during unit testing. Example limits:
	- structured/summarized/hidden information: 10-25%
	- contextual augmentation passages: 25-40%
	- warm slice: 40-70%
3. For contextual augmentation passages, `LORE` converts token budget into an overall character budget then makes final selections with the following logic:
	1. orders chunks from most relevant to least relevant
	2. removes the least relevant chunk and continues until the remainder is less than the character budget
	3. finally, reorders the final chunk selections chronologically (i.e., sort by chunk ID, "S03E07_003"), ensuring that all quoted passages are arranged in chronological order: historical context passages --> recent narrative --> last user input
4. For warm slice, `LORE` starts with user input and most recent chunk, then goes backwards until this character budget is filled.

# 07 Apex AI Generation
1. `LOGON` receives API payload from `LORE` and attempts to establish connection with Apex AI.
2. Checkpoint = Connectivity: If Apex API cannot be reached or fails to return valid response after a fixed amount of time, system enters offline mode. In this state, the narrative is frozen, but existing narrative history and character profiles may be browsed. `LOGON` continues to check for connectivity and retry API calls until a valid response is received.
3. Apex AI returns a structured response (`StoryTurnResponse`) with the following components:
	- narrative: new narrative passage
	- metadata: chronology updates, arc position, narrative vector updates
	- referenced_entities: entities present or mentioned in the narrative
	- state_updates: character state updates and relationship changes
	- operations: requests for summaries, regeneration, or side tasks
	- reasoning: AI's reasoning about narrative choices (for debugging)
4. Checkpoint = Quality Control: Present user with new narrative passage and prompt user to (A) accept or (B) reject new content.
	- If user rejects new content, provide option to (A) resend same API payload for regeneration, or (B) revise last user input and roll back to phase 02.
	- If user accepts new content, proceed to next phase
5. If user accepts new content, provide option to accept or reject new episode division.

# 08 Narrative Integration
1. `GAIA` processes any explicit changes to database information directed by Apex AI.
	   - "Change `location_status` of `Sullivan` from 'hiding under bed' to 'sleeping in laundry hamper'"
	   - "Change `internal_state` of `Pete` from 'resents being overlooked/underutilized' to 'determined to demonstrate he is invaluable and irreplaceable to team'"
	   - "Change `status` of `Pete_Silo` from 'abandoned' to 'occupied by squatters'"
2. `LORE` interprets new narrative for factual/event-based changes to databases.
3. `GAIA` interprets new narrative for character/relationship changes.
4. New chunk is embedded and enriched with metadata.
5. New chunk is added to user-viewable markdown-format chat interface. 

# 09 Idle State
1. System notifies user that integration processing is complete.
2. System awaits next user input.

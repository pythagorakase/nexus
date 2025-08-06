# 01 User Input
1. Simple chat-like interface within Terminal-based UI displays recent narrative in markdown format. (See `gui_mockup.rtf`)
2. User inputs next passage.

# 02 Warm Analysis
1. `LORE` cross-references "warm slice" against high-level summary information from SQLite database along two axes:
	   - characters
	   - events
2. For characters and events, `LORE` determines if they are known (i.e., if they already have database entries) or novel entities.
3. For relationships, `LORE` identifies
	   - which characters are directly interacting with each other
	   - any relationships that are off-screen but being referred to in dialog, etc.
4. Salience is determined along three axes, flagging entities for additional retrieval of structured information:
	   - characters: `PSYCHE` 
	   - relationships: `PSYCHE`
	   - events: `LORE`

# 03 World State Report
1. `LORE` sends queries to `GAIA` for more detailed information:
	   - characters: detailed stored profiles for salient characters
	   - relationships: status and dynamics of salient relationships
	   - events: historical summary of already-known plot elements
2. `GAIA` answers queries, but also always appends a certain level of unsolicited information about "hidden"/off-screen variables, since this type of information is otherwise prone to being ignored or "forgotten" by LLMs.
	   - last known location & activity of off-screen characters
	   - last known status of significant locations
	   - last known status & activity of factions

# 04 Deep Queries
1. Characters: `PSYCHE` selects one character for whom additional context/history would most benefit the Apex AI and formulates a query.
	   - "What is Alex's leadership style like?"
	   - "How has Emilia acted in similar situations before?"
2. Relationships: `PSYCHE` formulates a query for the most contextually important relationship.
	   - "How has Alex and Emilia's communication style changed over time?"
	   - "When did Alex and Emilia's relationship become romantic?"
	   - "How did Alina and Lansky interact during their first encounter?"
3. Events: `LORE`
	   - "When was the first time Alex entered The Bridge?"
	   - "What occurred immediately after the sabotage mission at the Dynacorp facility in season 1?"
4. Queries are sent to `MEMNON`

# 05 Cold Distillation
1. For each query, `MEMNON` returns a broad pool of candidate chunks with permissive matching for keywords, semantic embedding, and deep metadata
2. Cross-encoder reranking rapidly narrows the candidate chunk pool for each query to a "short list" suitable for inclusion in the context

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
3. Apex AI returns a JSON object with the following components:
	- new narrative passage
	- how far to advance the in-game clock
	- whether to propose a new episode/season division if appropriate (primary considerations: narrative rhythm, current episode/season length)
	- updates to hidden/off-screen information
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
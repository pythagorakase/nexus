# Episode Summary Request

I need a structured summary of Season {{SEASON}}, Episode {{EPISODE}} of the narrative. Analyze all the provided chunks and write the episode summary in the format specified.

{{CONTEXT_TEXT}}## The Narrative Chunks:

{{CHUNKS_TEXT}}

## Important Requirements:

1. The whole summary is at most 1,500 words. Stop before the limit rather than run past it.

2. Your summary must include ALL five sections exactly as follows:

   - OVERVIEW: One paragraph, at most 120 words.
   
   - TIMELINE: The longest section. One line per significant beat, each starting with "THEN:", in chronological order. At most 30 lines, at most 30 words each.
   
   - CHARACTERS: One line per character who acted, mapping the name to their current state. At most 12 lines.
   
   - PLOT_THREADS: Active, resolved, and introduced storylines, one line each. At most 10 lines.
   
   - CONTINUITY_ELEMENTS: Important objects, locations, and knowledge, one line each. At most 10 lines.

3. Be objective, factual, and focus on concrete details - your summary will be used by another AI to maintain narrative continuity.

4. Format matters! Your response must follow the exact structure required for machine processing.

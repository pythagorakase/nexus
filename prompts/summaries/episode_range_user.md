# Narrative Summary Request

I need a comprehensive, structured summary of the provided narrative chunks (IDs {{START_ID}}-{{END_ID}}), treating them as a complete episode. Please analyze all chunks to create a structured episode summary following the format specified.

## The Narrative Chunks:

{{CHUNKS_TEXT}}

## Important Requirements:

1. Your summary must include ALL five sections exactly as follows:

   - OVERVIEW: A brief factual summary of what happened in this episode.
   
   - TIMELINE: A list of chronological events, each starting with "THEN:"
   
   - CHARACTERS: A dictionary mapping character names to their current states.
   
   - PLOT_THREADS: A dictionary of active, resolved, and introduced storylines.
   
   - CONTINUITY_ELEMENTS: A dictionary of important objects, locations, and knowledge.

2. Be objective, factual, and focus on concrete details - your summary will be used by another AI to maintain narrative continuity.
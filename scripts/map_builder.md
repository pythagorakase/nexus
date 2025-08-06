# ClaudeCode Prompt: Create a New `map_builder.py`

## Project Overview
Unfortunately, our `map_builder.py` has become a buggy mess. I have renamed it `map_builder_fail.py`.

We will try again with a fresh start, and name this new script `map_builder.py`.

This script will analyze one chunk at a time, record relationships to known locations, and help identify new locations. It will use an interactive workflow very similar to that found in `map_builder_legacy.py`, with exceptions as detailed below.

## Key Requirements

### Database Integration
- Use the existing `place_chunk_references` table that has already been created. Query it directly to understand its structure.

- Connect to existing database to query:
  - `narrative_chunks` - Raw text content
  - `chunk_metadata` - Season, episode, scene info
  - `places` - Known locations
  - `zones` - Location categories
  - `place_chunk_references` - Existing references

### Processing Approach
- Process one chunk at a time: `chunk n`
- Include exactly one previous chunk as context: `chunk n-1`
- Show `chunk n-1` place references for continuity
- Do not show `chunk n-1` mention or transit references, as this may confuse the AI
- Do not send any following chunks
- System prompt will encourage AI to default to last-used place/setting if no transit/transition is suggested in text

### Command Line Interface
- Support arguments:
  - `--test`: Test mode to show what prompt would be used. IMPORTANT:
    - This mode should *not* use a separate pathway or dummy data.
    - When `--test` is used the script should function the same way prior to API call stage
    - Right after full API payload is built and before making API call, check `test` status
    - IF `test = True`: print full contents of API payload to terminal, then exit
    - ELSE: make API call
  - `--chunk`: Process specific chunks (ID, comma-separated list, or range with hyphen)
  - `--all`: Process all chunks needing location data
  - `--episode`: Process all chunks from a specific episode (e.g., s01e05)
  - `--overwrite`: Process chunks that already have location references
  - `--model`: Select alternate OpenAI endpoint (default `gpt-4.1`)

### User Interaction
- Auto-accept references to known places
- For new place suggestions, prompt for confirmation with options:
- `0`: Reject suggestion
- `1`: Accept, but always prompt user to confirm (enter to accept as-is), edit, or input details
	- `reference_type`: prompt user to accept or correct
	- `zones.id` inherit last-used but allow user to edit
	- `places.id` prompt user to enter manually
	- `places.name` allow user to edit AI-suggested name
	- `places.summary` allow user to edit AI-suggested summary
- `2`: Link to existing place instead
	- query and reprint known locations list
	- user will input `places.id` value only
- `9`: Quit


### Output Schema with Pydantic
- Adapt Pydantic models from `map_builder_fail.py` with minor adjustments as needed.
  - Do not request `zones.id` input from AI (default-to-last with user override option will handle this)
- Use OpenAI's `client.responses.parse()` with the Pydantic model for structured output

### Known Location Display Format
- Display places grouped by zone with clear formatting
- Do not display `zones.id` to AI, as this tends to confuse it into thinking `zones` are `places`

Mockup:
```
Night City - Center
├─111: Skyline Lounge - bar and corporate meeting place
├─112: Corporate District Streets - streets outside Skyline Lounge
├─113: Dead Circuit - computer equipment store
├─114: District 06 Hacker Den - hacker den hidden under noodle bar
├─115: Derelict Parking Structure - A rundown, abandoned parking structure overlooking a luxury capsule hotel, used as a vantage point for surveillance.
└─116: Luxury Capsule Hotel - A high-end, high-security capsule hotel in Night City, currently the site of a major corporate response and the protagonist's digital decoy.

Night City - Industrial Zone
├─121: District 07 Shipping Yard - dangerous gang-controlled neighborhood
├─122: Sable Rats Warehouse - gang headquarters and server area
├─123: Alex's Night City Safehouse - Alex's safehouse in abandoned transit hub
└─124: Low Tide - tech apparel store in industrial district
```

## Implementation Details

### Workflow
1. Parse command line arguments to determine chunks to process
2. Load known places and zones from database
3. For each chunk:
   - Get previous chunk and its place references for context
   - Build prompt with this context
   - Call OpenAI API with structured output schema
   - Process results:
     - Auto-record references to known places
     - Prompt for each new place suggestion
   - Update database with confirmed references

### Error Handling
- Check if tables exist before proceeding
- Validate API responses
- Handle database connection errors
- Provide helpful error messages

### Prompt Structure
- The system prompt will be loaded from a separate file: `prompts/map_builder.json`
- The externally-stored system prompt is hierarchically-stored; examine it yourself to understand its structure
- For simplicity of implementation, import the entire contents of the JSON system prompt without trying to reformat it.
	- include newlines and whitespace
	- do not flatten
	- further post-processing is not necessary
- The script should not contain ANY hardcoded prompts; these will be managed externally by the user.

#### Sequence

1. system prompt
2. known locations
3. `chunk n-1`
4. `chunk n`

We don't need to repeat the prompt & locations because this is not a long-context workflow.

## Additional Notes
- This is a rewrite of an existing script (`map_builder_legacy.py`), focus on reliability
- For best practices with OpenAI structured output, refer to patterns from `map_builder_fail.py`
- The script will import from `api_openai.py`
- Place IDs and zone IDs should both be shown to the user (for their reference)
- AI should only be shown place IDs

Please create a complete, well-commented implementation of this script.
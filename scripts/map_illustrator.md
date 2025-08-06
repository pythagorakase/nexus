# Map Illustrator Implementation Guide

## Overview
Create a Python script (`map_illustrator.py`) that expands location data in two distinct modes:
1. Fact mode: Extract only explicit location information from narrative chunks
2. Creative mode: Use factual base to create rich, detailed expansions

## Arguments Structure
```
# Extract factual information from direct chunk references
python map_illustrator.py --place 42 --fact --chunk

# Extract factual information from all chunks in relevant episodes
python map_illustrator.py --place 42 --fact --episode

# Create creative expansion using direct chunk references
python map_illustrator.py --place 42 --creative --chunk

# Debug mode shows output without updating database
python map_illustrator.py --place 42 --fact --chunk --debug
```

### `--test` Mode
    - Show what prompt *would* be used.
    - This mode should *not* use a separate pathway or dummy data.
    - When `--test` is used the script should function the same way prior to API call stage
    - Right after full API payload is built and before making API call, check `test` status
    - IF `test = True`: print full contents of API payload to terminal, then exit
    - ELSE: make API call

## Core Components

## Dual Modes
### `--fact` Mode
Tells the AI to write only what the text supports, in just one unstructured string, which will be stored in `places.summary`.

## `--creative` Mode
Sends the all the same amount of information that `--fact` mode does, plus the factual text block from `places.summary`, and generates content for the following columns from the `places` table:
inhabitants _text
history text
current_status varchar(500)
secrets text
extra_data jsonb

### Prompt Management
- The system prompt will be loaded from a separate file: `prompts/map_illustrator.json`
- The externally-stored system prompt is hierarchically-stored; examine it yourself to understand its structure
- At the root level, this file contains two objects, representing a complete and distinct system prompt for each of the two modes: `fact_mode` and `creative_mode`
- For simplicity of implementation, fetch one object or the other, and import that object into the appropriate location of the API package with no additional formatting.
	- include newlines and whitespace
	- do not flatten
	- further post-processing is not necessary
- The script should not contain ANY hardcoded prompts; these will be managed externally by the user.

### Automated Content-Place Matching
This takes advantage of all the trouble we went to in gathering the place<-->chunk data. No need to manually enter chunk/episode values, lists, or ranges.

#### `--chunk` 
References `places.id` against a many-to-many relational table, `place_chunk_references`, to build a list of all chunks where the place was a setting, was mentioned, or was traveled through. Not interested in making the distinction in this workflow. Grab them all!

#### `--episode`
Similar to the automatic chunk fetch, but expands this by fetching every chunk in the `episodes.chunk_span` of every episode that contains at least one chunk that matches the relational table.

## Tagging
Because any given chunk may have multiple types of `place` data, each chunk should present this data in a clear, structured fashion. Mockup:

   ```
   Night City - Center
   └─111: Skyline Lounge (setting)
   └─112: Night City Streets (transit)
   
   Night City - Industrial Zone
   └─124: Low Tide (setting)
   
   Antarctic
   └─651: Antarctic Military Research Station (mentioned)
   
   vehicles
   └─001: The Ghost (setting)
   ```

### **OpenAI API Notes**:
   - Where possible, import from our library, `scripts/api_openai.py`
   - Use OpenAI's Structured Output mode for guaranteed schema adherence
   - Requirements for Structured Output mode are strict, and detailed in `CLAUDE.md`
   - Define structure with Pydantic and `client.responses.parse()`
   - Use `o3` as default model
   - Do not send a temperature parameter unless given as an argument

### **Error Handling**:
   - Use sparingly!
   - The user hates error handling because it often conceals problems.
   - The user prefers that errors raise exceptions and alert us to problems we need to solve.
   - Few to no fallbacks should be required.
   - Example: If script cannot find or load system prompt from `prompts/map_illustrator.json`, it should error and quit.

### **Debugging and Feedback**:
   - In debug mode, show formatted outputs without database updates
   - Provide clear logging about what's happening in each step

## `places.extra_data` Schema
Convert this to Pydantic.

```
{
  "areas": {
    "area_name_1": {
      "description": "",
      "purpose": "",
      "notable_features": []
    },
    "area_name_2": {
      "description": "",
      "purpose": "",
      "notable_features": []
    }
  },
  "physical_attributes": {
    "appearance": "",
    "atmosphere": "",
    "notable_features": [],
    "sensory_details": {
      "sights": [],
      "sounds": [],
      "smells": [],
      "textures": []
    }
  },
  "surroundings": {
    "environment": "",
    "approach": "",
    "nearby_features": [],
    "weather_patterns": "",
    "accessibility": ""
  },
  "technology": {
    "systems": [],
    "capabilities": [],
    "limitations": [],
    "unique_aspects": ""
  },
  "social_aspects": {
    "customs": [],
    "power_structure": "",
    "common_activities": [],
    "reputation": ""
  },
  "secrets": {
    "mysteries": [],
    "tensions": [],
    "narrative_hooks": [],
    "hidden_elements": []
  }
}
```

## Pseudocode Outline

```python
# 1. Command-line interface
def parse_arguments():
    # Parse arguments with argparse
    # Required: --place ID
    # Mode (mutually exclusive): --fact or --creative
    # Source (mutually exclusive): --chunk or --episode
    # Optional: --debug
    return args

# 2. Data retrieval functions
def get_place_by_id(conn, place_id):
    # Query places table
    # Include zone information via parent_id lookup
    # Return structured place data
    
def get_chunks_for_place(conn, place_id):
    # Query place_chunk_references for all reference types
    # Get corresponding chunks
    # For each chunk, get all places referenced in it
    # Get zone information for places
    # Return structured chunk data
    
def get_episodes_containing_place(conn, place_id):
    # Find episodes that contain chunks referencing this place
    # Return episode data including chunk_span
    
def get_chunks_for_episodes(conn, episodes):
    # Get all unique chunks from episode chunk_spans
    # For each chunk, get place references
    # Get zone information for places
    # Return structured chunk data

# 3. Content organization
def format_chunks_with_tags(chunks, target_place_id):
    # Organize chunks by zones and places
    # Group by parent location (zone)
    # Special handling for vehicles
    # Format as hierarchical text display
    # Ensure target place is highlighted
    return formatted_text

# 4. Prompt preparation
def load_system_prompt():
    # Load from map_illustrator_system.json
    # Return both fact_mode and creative_mode objects
    
def load_schema():
    # Load from schema_map_illustrator.json
    # Return schema object
    
def prepare_fact_prompt(place, chunks):
    # Format location information
    # Include tagged chunk context
    # Format chunk contents
    # Return complete prompt for fact extraction
    
def prepare_creative_prompt(place, chunks, schema):
    # Format location information
    # Include factual summary as canonical foundation
    # Include tagged chunk context
    # Include schema structure
    # Format chunk contents
    # Return complete prompt for creative expansion

# 5. API interactions
def extract_facts_with_openai(place, chunks):
    # Use OpenAI API with fact mode system prompt
    # Set temperature low (0.1-0.3)
    # Return factual summary text
    
def expand_creatively_with_openai(place, chunks, schema):
    # Use OpenAI API with creative mode system prompt
    # Require structured JSON output
    # Set temperature higher (0.7-0.8)
    # Parse response to extract JSON
    # Return structured expansion data

# 6. Database updates
def update_place_summary(conn, place_id, summary):
    # Update only places.summary field
    # Return success status
    
def update_place_creative(conn, place_id, expansion_data):
    # Update all fields: summary, inhabitants, etc.
    # Structure extra_data as JSONB
    # Return success status

# 7. Process functions
def process_place_fact_mode(conn, place_id, use_chunks, use_episodes, debug):
    # Get place data
    # Get appropriate chunks based on flags
    # Extract factual information
    # Update database unless debug mode
    # Return success status
    
def process_place_creative_mode(conn, place_id, use_chunks, use_episodes, debug):
    # Get place data
    # Verify factual summary exists
    # Get appropriate chunks based on flags
    # Create creative expansion
    # Update database unless debug mode
    # Return success status

# 8. Main function
def main():
    # Parse arguments
    # Connect to database
    # Process based on arguments
    # Close database connection
```


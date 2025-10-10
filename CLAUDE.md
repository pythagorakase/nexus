# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands
- Install dependencies: `poetry install`
- Run tests: `poetry run pytest`
- Run specific test: `poetry run pytest tests/path/to/test.py::test_name`
- Format code: `poetry run black .`
- Typecheck: `poetry run mypy .`
- Lint: `poetry run flake8`

## Code Style Guidelines
- Use Black for formatting with default line length (88 chars)
- Imports: standard library, third-party, local (alphabetized within groups)
- Use type annotations for all function parameters and return values
- Classes: PascalCase, functions/variables: snake_case
- Use Pydantic for data validation and serialization
- Error handling: use specific exceptions with descriptive messages
- Documentation: docstrings for all public functions and classes
- Prefer composition over inheritance where possible
- Use SQLAlchemy for database interactions
- When working with agents, follow NEXUS runtime conventions

## Database Connection
- Database Name: NEXUS
- Host: localhost
- User: pythagor
- Password: None (uses system authentication)
- Port: 5432 (default PostgreSQL port)
- Connection string: `postgresql://pythagor@localhost:5432/NEXUS`
- Main tables:
  - `narrative_chunks`: Contains the raw text content (fields: id, raw_text, created_at)
  - `chunk_metadata`: Contains metadata for each chunk (fields: id, chunk_id, world_layer, etc.)
  - `chunk_embeddings`: Contains vector embeddings for search (fields: chunk_id, model, embedding)

## API Key Management

**IMPORTANT: All API keys are securely stored in 1Password. Never store API keys in environment variables, config files, or source code.**

### 1Password Setup
The codebase uses 1Password CLI for secure API key retrieval:

#### OpenAI API Key
- **Vault**: API
- **Item ID**: tyrupcepa4wluec7sou4e7mkza
- **Access Method**: `op item get tyrupcepa4wluec7sou4e7mkza --fields "api key" --reveal`
- **Plugin Setup**: 1Password OpenAI shell plugin is configured
  - Source the plugin: `source /Users/pythagor/.config/op/plugins.sh`
  - This enables the `openai` CLI command with automatic authentication
  - Configuration verified with: `op plugin inspect openai`

#### Anthropic API Key
- **Vault**: API
- **Reference**: `op://API/Anthropic/api key`
- **Access Method**: `op read "op://API/Anthropic/api key"`

### Implementation Details
- `scripts/api_openai.py`: Uses subprocess to call 1Password CLI for OpenAI keys
- `scripts/api_anthropic.py`: Uses subprocess to call 1Password CLI for Anthropic keys
- Both scripts will fail with clear error messages if:
  - 1Password CLI is not installed
  - User is not signed into 1Password
  - API keys are not found in the expected vaults

### Security Notes
- Never fallback to environment variables or config files
- All API key access requires biometric authentication through 1Password
- Error messages do not expose sensitive information
- Keys are only retrieved when needed and not cached in memory

## User Directives
- Do not hardcode any settings the user may conceivably want to adjust during development; instead, add the settings to `settings.json`, following the established format there, and write your code to pull configurable values from that file.
- Do not build graceful fallbacks into your code unless the user requests it or explicitly gives permission. While in development, I prefer that errors surface visibly and unmistakebly. If that means a screeching traceback, so be it!

## OpenAI API Best Practices

### Using Structured Outputs (responses.parse vs responses.create)

When implementing OpenAI API calls requiring structured responses, there are two main approaches: `responses.parse()` (preferred) or `responses.create()` with a JSON schema. We strongly recommend using the `responses.parse()` method with a Pydantic model for most use cases.

#### Preferred Approach: `responses.parse()` with Pydantic

This approach offers the simplest implementation and best reliability:

```python
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List

# Define Pydantic models for your structured output
class CharacterSummary(BaseModel):
    character_id: int = Field(description="ID of the character")
    summary: str = Field(description="Character summary text")

class CharacterSummaries(BaseModel):
    characters: List[CharacterSummary] = Field(description="List of character summaries")
    
    class Config:
        extra = "forbid"  # Equivalent to additionalProperties: false

# Use responses.parse with the Pydantic model
client = OpenAI()
response = client.responses.parse(
    model="gpt-4.1",  # Use appropriate model
    input=[
        {"role": "system", "content": "You are a character summarizer."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.2,
    text_format=CharacterSummaries  # Pass the Pydantic model directly
)

# Access the parsed data directly as a Pydantic object
result = response.output_parsed
for character in result.characters:
    print(f"Character {character.character_id}: {character.summary}")
```

The `responses.parse()` method automatically:
- Converts your Pydantic model to a proper JSON schema
- Adds `additionalProperties: false` at every object level
- Sets required fields based on your model
- Returns a fully-validated Pydantic object

#### Alternative: `responses.create()` with Direct Schema

For cases where you need more control over the schema:

```python
response = client.responses.create(
    model="gpt-4o",
    input=messages,
    text={
        "format": {
            "type": "json_schema",
            "name": "character_summary",
            "schema": {
                "type": "object",
                "properties": {
                    "character_id": {
                        "type": "integer",
                        "description": "ID of the character"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Character summary"
                    }
                },
                "required": ["character_id", "summary"],
                "additionalProperties": false
            },
            "strict": true
        }
    }
)

# Parse the response manually
result = json.loads(response.output_text)
```

### Hard-Won Lessons for Structured Outputs

From extensive testing, we've learned these critical guidelines:

1. **Handling Collections of Items:**
   - Use an array-based approach for multiple items rather than dynamic keys
   - Example for multiple characters:
   ```python
   class CharacterSummaries(BaseModel):
       characters: List[CharacterSummary]
   ```
   - Avoid dictionary types with dynamic keys like `Dict[str, str]` as these are harder to validate

2. **Schema Requirements:**
   - ALWAYS include `additionalProperties: false` at EVERY object level 
   - ALWAYS explicitly list ALL properties in the `required` array, even optional ones
   - For optional fields, use a union type with `null` in the type definition:
     ```json
     "unit": {
         "type": ["string", "null"],
         "description": "Optional unit (F or C)",
         "enum": ["F", "C"]
     }
     ```
   - These requirements apply to every nested object in your schema

3. **Hierarchy and Nesting:**
   - Keep schemas as flat as possible
   - For unavoidable nesting, use arrays of objects with well-defined structures
   - Use `$ref` for recursive structures, for example:
   ```json
   {
     "$defs": {
       "node": {
         "type": "object",
         "properties": {
           "value": { "type": "string" },
           "next": { "$ref": "#/$defs/node" }
         },
         "additionalProperties": false,
         "required": ["value"]
       }
     },
     "$ref": "#/$defs/node"
   }
   ```

4. **Troubleshooting Schema Issues:**
   - Error `Unknown parameter: 'text.type'` often means your schema format is incorrect
   - For schema validation errors, try simplifying until it works, then add complexity
   - When using `responses.create()`, verify every nesting level has:
     - `additionalProperties: false`
     - `required` listing all non-optional properties
     - Correct types and descriptions

### Implementation Recommendations

- When possible, use `responses.parse(text_format=MyPydanticModel)` instead of building JSON schemas manually
- For multiple items, use an array-based approach rather than dynamic dictionary keys
- Start with small, working examples and gradually add complexity
- Include a `--test` mode in scripts to inspect what's being sent to the API
- For collections, consider applying a reasonable limit (e.g., 5-10 items per API call)

Following these guidelines will save significant development time and API costs while ensuring reliable structured outputs.
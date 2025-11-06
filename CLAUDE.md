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

For detailed key management workflows, see the `update-1password-keys` skill in `.claude/skills/`.

## User Directives
- Do not hardcode any settings the user may conceivably want to adjust during development; instead, add the settings to `settings.json`, following the established format there, and write your code to pull configurable values from that file.
- Do not build graceful fallbacks into your code unless the user requests it or explicitly gives permission. While in development, I prefer that errors surface visibly and unmistakebly. If that means a screeching traceback, so be it!

## Task-Specific Workflows (Claude Code Skills)

For detailed, task-specific workflows and guides, see the Claude Code skills in `.claude/skills/`. These skills are automatically invoked when relevant:

- **git-feature-workflow**: Complete feature development workflow including branch creation, PR submission, GPT-5-Codex review handling, merging, and cleanup
- **test-lore-agent**: Run LORE agent tests with context saving, divergence detection testing, and jq query helpers
- **audit-settings**: Validate `settings.json` for configuration errors, constraint violations, and cross-agent consistency
- **inspect-chunk-context**: Query NEXUS database for chunk details, metadata, entity references, and temporal relationships
- **update-1password-keys**: Manage API key retrieval from 1Password, verify CLI configuration, and rotate credentials
- **openai-structured-output**: Implement OpenAI structured outputs with Pydantic models or JSON schemas
- **analyze-divergence**: Debug divergence detection behavior, understand the LLM-based architecture, and tune thresholds

These skills contain detailed commands, workflows, troubleshooting guides, and best practices extracted from development experience.

## LLM-Based Divergence Detection

The LORE agent uses intelligent LLM-based divergence detection to identify when users reference entities, events, or context not present in the recent narrative (warm slice).

For architecture details, testing procedures, and troubleshooting, see the `analyze-divergence` skill in `.claude/skills/`.

## OpenAI API Best Practices

For implementing structured outputs with `responses.parse()` or `responses.create()`, including Pydantic patterns, schema requirements, and troubleshooting, see the `openai-structured-output` skill in `.claude/skills/`.
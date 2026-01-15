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

## Database Connection (Save Slots)

NEXUS uses a multi-slot save system. Each save slot has its own database:
- **Slot 1**: `save_01`
- **Slot 2**: `save_02`
- **Slot 3**: `save_03`
- **Slot 4**: `save_04`
- **Slot 5**: `save_05`

**IMPORTANT**: The `NEXUS` database is deprecated. Use `NEXUS_template` as the canonical schema reference.

### Schema Management Workflow

`NEXUS_template` is the single source of truth for database schema. There are two mechanisms for schema changes:

#### 1. Incremental Migrations (for existing databases with data)

Use `scripts/migrate.py` to apply SQL migrations to all databases without data loss:

```bash
# Check migration status across all databases
python scripts/migrate.py --status

# Apply pending migrations to all unlocked databases
python scripts/migrate.py --all

# Dry-run to see what would be applied
python scripts/migrate.py --all --dry-run

# Apply to specific slot or template only
python scripts/migrate.py --slot 5
python scripts/migrate.py --template
```

Migration files live in `migrations/` (e.g., `009_remove_assets_save_slots.sql`). The runner tracks applied migrations in a per-database `schema_migrations` table.

**Locked slots are skipped** - unlock first if needed, then re-lock after migration.

#### 2. Slot Initialization (for new/empty slots)

Use `scripts/new_story_setup.py` to create fresh slots from template (DESTRUCTIVE - drops all data):

```bash
# Reset a slot to fresh schema (schema-only, no data)
python scripts/new_story_setup.py --slot 5 --force

# Clone with data from another slot
python scripts/new_story_setup.py --slot 5 --mode clone --source save_01 --force
```

The setup script uses `pg_dump -s` to extract schema from `NEXUS_template`.

**When to use each:**
- **Migrations** → Schema changes to existing slots with data (non-destructive)
- **Slot initialization** → Creating fresh slots or resetting test slots (destructive)

#### Refreshing the Template

To update `NEXUS_template` from a known-good slot:
```bash
dropdb NEXUS_template && createdb NEXUS_template && pg_dump -s -d save_01 | psql -d NEXUS_template
```

### Active Slot Configuration
Set the active slot via the `NEXUS_SLOT` environment variable (1-5):
```bash
export NEXUS_SLOT=1  # Use save_01 database
```

### Slot Utilities
Use functions from `nexus/api/slot_utils.py`:
- `require_slot_dbname(dbname=None, slot=None)` - Get validated database name
- `get_slot_db_url(dbname=None, slot=None)` - Get full PostgreSQL URL
- `get_active_slot()` - Get active slot from NEXUS_SLOT env var
- `slot_dbname(slot)` - Convert slot number (1-5) to database name

### Connection Details
- Host: localhost
- User: pythagor
- Password: None (uses system authentication)
- Port: 5432 (default PostgreSQL port)
- Example connection string: `postgresql://pythagor@localhost:5432/save_01`

### Main Tables (per slot)
- `narrative_chunks`: Contains the raw text content (fields: id, raw_text, created_at)
- `chunk_metadata`: Contains metadata for each chunk (fields: id, chunk_id, world_layer, etc.)
- `chunk_embeddings`: Contains vector embeddings for search (fields: chunk_id, model, embedding)

## API Key Management

**IMPORTANT: All API keys are securely stored in 1Password. Never store API keys in environment variables, config files, or source code.**

For detailed key management workflows, see the `update-1password-keys` skill in `.claude/skills/`.

## User Directives
- Do not hardcode any settings the user may conceivably want to adjust during development; instead, add the settings to `nexus.toml`, following the established format there, and write your code to pull configurable values from that file.
- Do not build graceful fallbacks into your code unless the user requests it or explicitly gives permission. While in development, I prefer that errors surface visibly and unmistakebly. If that means a screeching traceback, so be it!

## Testing with NEXUS CLI

When developing features that affect the narrative/wizard flow:

1. **Always test using the NEXUS CLI** before reporting back to the user (unless it's a UI-only feature)
2. **Roleplay as a human user** - use simple, direct commands:
   ```bash
   nexus continue --slot 5 --choice 1
   nexus load --slot 5
   ```
   Not Rube Goldberg constructions with bash/echo/cat/piping.
3. **Expand the CLI** if it doesn't have syntax for your new feature yet - add the necessary commands to support testing

For CLI command reference, see the `nexus-cli` skill in `.claude/skills/`.

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
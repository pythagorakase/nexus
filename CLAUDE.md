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

### Schema Reference

The NEXUS database schema is self-describing via Postgres table and column comments. **Do not duplicate schema details in this file** — they drift. Use the live schema instead:

- **Interactive inspection**: `psql -d save_NN -c '\d+ <table>'` (`\dt` to list all tables). The `\d+` form shows column comments in the Description column plus foreign-key references — effectively a free, always-current ER diagram in text.
- **Programmatic access**: `MEMNON.get_schema_summary(tables=[...])` in `nexus/agents/memnon/memnon.py` returns a structured summary (the same path LORE uses to build retrieval context).
- **Convention**: when adding a column, include `COMMENT ON COLUMN <table>.<col> IS '...'` in the same migration. The comment IS the documentation.

## API Key Management

**Runtime API key storage is macOS Keychain.** 1Password remains the canonical source of truth used for rotation and audit; `scripts/sync_secrets.py` copies keys from 1Password into Keychain on bootstrap or rotation, and that script is the only place in the codebase that touches `op`.

All runtime code retrieves keys via `nexus.util.secret_manager.get_secret(<provider>)`. The helper subprocesses to the system `security` CLI (Apple-signed, silent) rather than invoking 1Password — so agentic / unattended workflows are not interrupted by biometric or session-expiry prompts.

**Storage rules:**
- Never commit keys to source.
- Never export keys in long-lived shell rc files.
- `NEXUS_KEYRING_DISABLE=1` is the supported CI/debug escape hatch — when set, `get_secret` reads from `<PROVIDER>_API_KEY` env vars instead of Keychain.
- Keys live in Keychain under service `nexus-api`, account `<provider>` (e.g., `openai`, `anthropic`, `openrouter`). Inspect with `security find-generic-password -s nexus-api -a <provider> -w`.

For detailed key management workflows including rotation, see the `manage-api-keys` skill in `.claude/skills/`.

## User Directives
- **Formatting**: The user has a strong preference for Chicago title case in headings.
- Do not hardcode any settings the user may conceivably want to adjust during development; instead, add the settings to `nexus.toml`, following the established format there, and write your code to pull configurable values from that file.
- Do not build graceful fallbacks into your code unless the user requests it or explicitly gives permission. While in development, I prefer that errors surface visibly and unmistakebly. If that means a screeching traceback, so be it!
- **Testing Defaults**: When writing live tests or setting model defaults in *runtime* code, do not hardcode model IDs. Reference the `[global.model.api_models]` registry in `nexus.toml` via `@<provider>.<role>` syntax (e.g., `@openai.default`, `@anthropic.fast`); the Pydantic loader resolves these to concrete IDs at config load. Tests that intentionally pin a specific model for behavioral regression coverage may keep literal IDs and should add a `# pin: <reason>` comment so the drift checker (`scripts/check_model_drift.py`) ignores them.
- **Testing Philosophy**: The user **HATES** mock tests. If the current feature involves remote inference, for example, that means testing will be meaningless to the user unless it makes real API calls.

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
- **manage-api-keys**: Manage NEXUS API keys via macOS Keychain (runtime) and 1Password (canonical source), bootstrap fresh checkouts, rotate keys, and troubleshoot silent retrieval
- **openai-structured-output**: Implement OpenAI structured outputs with Pydantic models or JSON schemas
- **analyze-divergence**: Debug divergence detection behavior, understand the LLM-based architecture, and tune thresholds

These skills contain detailed commands, workflows, troubleshooting guides, and best practices extracted from development experience.

## LLM-Based Divergence Detection

The LORE agent uses intelligent LLM-based divergence detection to identify when users reference entities, events, or context not present in the recent narrative (warm slice).

For architecture details, testing procedures, and troubleshooting, see the `analyze-divergence` skill in `.claude/skills/`.

## OpenAI API Best Practices

For implementing structured outputs with `responses.parse()` or `responses.create()`, including Pydantic patterns, schema requirements, and troubleshooting, see the `openai-structured-output` skill in `.claude/skills/`.
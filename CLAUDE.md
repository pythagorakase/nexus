# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands
- Install dependencies: `poetry install`
- Register pre-commit hooks (once per checkout): `poetry run pre-commit install`
- Run tests: `poetry run pytest`
- Run specific test: `poetry run pytest tests/path/to/test.py::test_name`
- Format code: `poetry run black .`
- Typecheck: `poetry run mypy .`
- Lint: `poetry run flake8`

## Configuration

`nexus.toml` is the sole runtime configuration file, validated by the Pydantic models in `nexus/config/settings_models.py`. The legacy top-level `settings.json` was retired in June 2026 after every runtime reader (loader fallback chain, LORE, MEMNON, memory manager) had migrated to nexus.toml; its overlapping keys (embedding model registry with `is_active` flags, `memory.divergence_threshold`, retired GAIA/NEMESIS/PSYCHE agent settings) were already dead copies. Explicitly passed `.json` paths to `load_settings()` remain supported only for legacy ir_eval V1 tooling.

## Pre-commit hooks

Config in `.pre-commit-config.yaml`. Hooks fire on `git commit`. Currently:

- **regenerate-orrery-catalog** — always runs and regenerates `docs/orrery_packages.md` so the human-readable catalog stays in lockstep with the canonical Python source. The hook modifies the file; if it does, pre-commit aborts the commit and prompts you to re-stage the regenerated doc + commit again.
- **validate-config** — fires when `nexus.toml` or any `.py` file is staged; makes model-roster edits safe to commit. Loads `nexus.toml` through the Pydantic models (a removed model id with a dangling `@provider.role` reference aborts the commit here, not at the next boot), enforces the dev-dashboard ship-off invariant (`[orrery.dashboard] enabled` must be committed `false`; use `NEXUS_DEV_DASHBOARD=1` for local dashboard work), and runs `scripts/check_model_drift.py` for stale literal model ids lacking a `# pin: <reason>` comment.

Bypass (use sparingly): `git commit --no-verify`. CI staleness tests still gate merges.

## Shared Agent Workflow

Follow `docs/agent_workflow.md` for the repository's autonomous branch, PR,
review-orchestration, heartbeat, merge, and cleanup workflow.

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

The template is the canonical fresh-slot image: latest schema **plus**
seed/vocab rows (`tags`, `event_types`, `pair_tags`, `tag_category_registry`,
`assets.traits`) **plus** a fully stamped `schema_migrations` table. Slot
initialization copies all three; a template without migration stamps is
rejected loudly (the runner would otherwise replay already-applied
migrations against the post-migration schema and fail).

To update `NEXUS_template` from a known-good slot:
```bash
dropdb NEXUS_template && createdb NEXUS_template && pg_dump -s -d save_01 | psql -d NEXUS_template
pg_dump --data-only -d save_01 -t schema_migrations -t tags -t event_types \
  -t pair_tags -t tag_category_registry -t assets.traits | psql -d NEXUS_template
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

**The platform secret store is canonical.** NEXUS uses macOS Keychain on Darwin and the Python `keyring` backend elsewhere. Set and rotate credentials through the settings pane's API KEYS card; the card reads only masked status from `GET /api/secrets/status`, writes through `PUT /api/secrets/{provider}`, and verifies with a real provider call through `POST /api/secrets/{provider}/verify`.

All runtime reads go through `nexus.util.secret_manager.get_secret(<account>)`, and all writes go through `set_secret(<account>, <key>)`. On macOS the helpers subprocess to Apple's signed `security` CLI for silent unattended access; other platforms use `keyring`. Native providers use their provider name as the account. Visible non-native registry providers participate only when `[global.model.api_models.<provider>].api_key_secret` declares their account; keyless and UI-hidden providers never appear in the card.

**Storage Rules:**
- Never commit keys to source.
- Never export keys in long-lived shell rc files.
- `NEXUS_KEYRING_DISABLE=1` is the supported CI/debug escape hatch — when set, `get_secret` reads from `<ACCOUNT>_API_KEY` env vars instead of the platform store.
- Stored keys use service `nexus-api`; inspect status through the API KEYS card rather than printing credential values.
- 1Password is not a NEXUS dependency or source of truth. `scripts/sync_secrets.py` is a deprecated personal migration shim for legacy entries only.

For detailed set, rotation, verification, and migration workflows, see the `manage-api-keys` skill in `.claude/skills/`.

## User Directives
- **Formatting**: The user has a strong preference for Chicago title case in headings.
- Do not hardcode any settings the user may conceivably want to adjust during development; instead, add the settings to `nexus.toml`, following the established format there, and write your code to pull configurable values from that file.
- Do not build graceful fallbacks into your code unless the user requests it or explicitly gives permission. While in development, I prefer that errors surface visibly and unmistakebly. If that means a screeching traceback, so be it!
- **Testing Defaults**: When writing live tests or setting model defaults in *runtime* code, do not hardcode model IDs. Reference the `[global.model.api_models]` registry in `nexus.toml` via `@<provider>.<role>` syntax (e.g., `@openai.default`, `@anthropic.fast`); the Pydantic loader resolves these to concrete IDs at config load. Tests that intentionally pin a specific model for behavioral regression coverage may keep literal IDs and should add a `# pin: <reason>` comment so the drift checker (`scripts/check_model_drift.py`) ignores them.
- **Testing Philosophy**: The user **HATES** mock tests. If the current feature involves remote inference, for example, that means testing will be meaningless to the user unless it makes real API calls.

## UI Design: Visual Minimalism

Scope: all visual UI surfaces (the IRIS web client under `ui/`). CLI output follows its own conventions.

The standing antipattern to avoid is **visual verbosity**: cluttering the UI with excessive or redundant textual labels. The reference example is the light/dark toggle on darioamodei.com — a small unlabeled icon button that swaps theme on a single click; its function is ~90% guessable on sight and 100% confirmed by one click. NEXUS UI should strive for that kind of clean minimalism.

- Every verbal label must earn its place, and the threshold is high. UI elements should be visually self-evident or easily discoverable through interaction.
- Err on the side of too little labeling. When confusion seems possible, first redesign the element to communicate intent visually — an icon, placement, theme-token color or weight, state styling (dimmed, glowing, dashed), or a hover-revealed affordance — and add text only as a last resort.
- Never restate information already visible elsewhere on screen (duplicate slugs, repeated cast lists, a wordmark re-spelled in a footer bar).
- No explanatory paragraphs in persistent chrome (the recurring shell: nav rails, headers, sidebars, settings panes). Rationale and "how this works" prose belong in release communications or docs — never in the UI.
- One label per section, maximum, matching its navigation name. No eyebrow-plus-title-plus-subtitle stacks.
- Internal module names (LORE, LOGON, MEMNON, and the like) never appear in UI copy. Users see plain functional names: "MODEL", "CONTEXT LENGTH".
- Don't uppercase content. Character names and prose render in natural case; uppercase belongs only to chrome element labels where the vendored theme CSS (`ui/client/src/`) styles them that way.
- Transient status (telemetry, progress) is visible only while the underlying activity is live, and vanishes when idle.
- Friction is earned the same way labels are: destructive actions (wiping an occupied save slot) warrant explicit confirmation; everything else should act on a single interaction.

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
- **audit-settings**: Validate agent configuration (`nexus.toml`) for errors, constraint violations, and cross-agent consistency
- **inspect-chunk-context**: Query NEXUS database for chunk details, metadata, entity references, and temporal relationships
- **manage-api-keys**: Set, rotate, inspect, and verify NEXUS API keys through the canonical platform secret store and API KEYS card
- **openai-structured-output**: Implement OpenAI structured outputs with Pydantic models or JSON schemas

These skills contain detailed commands, workflows, troubleshooting guides, and best practices extracted from development experience.

## Entity-Based Divergence Detection

The LORE turn loop (`nexus/memory/manager.py`) runs deterministic entity-based divergence detection (`nexus/memory/divergence.py`, `nexus/memory/entity_detector.py`) to identify when user input references known entities absent from the warm slice. Configuration: `divergence_threshold` in nexus.toml's `[memory]` section (default `0.7`). Tests at `tests/test_lore/test_memory_manager.py` and `tests/test_lore/test_pass2_chunk1369.py`.

This is the **deterministic** entity-based variant. An earlier *LLM-based* divergence detection path was retired per the bake-off in `docs/retrieval_query_bakeoff_2026_05_18.md`; the `analyze-divergence` skill that documented the LLM-based path was removed alongside.

## OpenAI API Best Practices

For implementing structured outputs with `responses.parse()` or `responses.create()`, including Pydantic patterns, schema requirements, and troubleshooting, see the `openai-structured-output` skill in `.claude/skills/`.

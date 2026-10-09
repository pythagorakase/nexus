---
status: canonical
sources:
  - CLAUDE.md
  - nexus/agents/lore/lore.py
  - nexus/agents/lore/utils/turn_cycle.py
  - nexus/agents/lore/logon_utility.py
  - nexus/agents/lore/seat_blocks.py
  - nexus/agents/logon/apex_enums.py
  - nexus/agents/logon/apex_schema.py
  - nexus/agents/logon/gaia_registry_schema.py
  - nexus/agents/logon/orrery_tag_validation.py
  - nexus/agents/logon/place_reference_validation.py
  - nexus/agents/logon/skald_wire.py
  - nexus/agents/memnon/memnon.py
  - nexus/agents/orrery/worker.py
  - docs/blueprint_gaia.md
  - docs/blueprint_nemesis.md
  - docs/blueprint_psyche.md
  - nexus/memory/manager.py
  - nexus/memory/context_state.py
  - nexus/memory/divergence.py
  - nexus/memory/entity_detector.py
  - nexus/api/narrative.py
  - nexus/jobs/scheduler.py
  - nexus/prompts/registry.py
  - docs/turn_flow_sequence.md
  - tests/conftest.py
  - tests/pg_fixtures.py
  - tests/test_lore/conftest.py
  - tests/test_lore/test_memory_manager.py
  - pytest.ini
  - nexus.toml
  - docs/agent_workflow.md
  - nexus/util/secret_manager.py
  - scripts/sync_secrets.py
  - nexus/api/slot_utils.py
verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"
---

# Repository Guidelines

## Project Structure & Module Organization
Core package lives in `nexus/`. Agents in `nexus/agents/`: `lore` orchestrates each turn (`lore.py`, `utils/turn_cycle.py`) and hosts LOGON (`logon_utility.py`), the provider client for the Skald writer and Gaia seats; `logon` holds the storyteller wire schemas and validators; `memnon` handles retrieval; and `orrery` is the deterministic off-screen world engine. GAIA, PSYCHE, and NEMESIS modules were never built: their `docs/blueprint_*.md` files are historical, and Gaia now names the second storyteller seat. Pass 1/Pass 2 memory lives in `nexus/memory/` (`manager.py`, `context_state.py`, `divergence.py`, `entity_detector.py`). The FastAPI gateway and its turn routes live in `nexus/api/` (`narrative.py`), and deferred work runs under `nexus/jobs/`. Model prompts are Markdown files under `prompts/`, loaded only through the catalog in `nexus/prompts/registry.py`. The IRIS client lives in `ui/`, tooling scripts in `scripts/`, SQL migrations in `migrations/`, and reference material in `docs/`; `docs/turn_flow_sequence.md` traces the turn cycle through the code. Tests live under `tests/`, grouped by subsystem (`tests/test_lore/`, `tests/test_api/`, `tests/test_orrery/`, and others). Runtime settings live in `nexus.toml`.

## Build, Test, and Development Commands
`CLAUDE.md` is the canonical command reference, including the PostgreSQL test gate, migrations, and pre-commit hooks. Bootstrap with `poetry install`. Run the suite with `poetry run pytest`; narrow scope with `poetry run pytest tests/test_lore/test_memory_manager.py::test_explicit_base_budget_mode_configures_phase2`. Format via `poetry run black .`; type-check `poetry run mypy .`; lint `poetry run flake8`.

## Coding Style & Naming Conventions
Adopt Black (88 columns) and flake8. Group imports stdlib/third-party/local and alphabetize. Use PascalCase for classes and snake_case elsewhere. Public functions and classes need docstrings and explicit type hints. Load configurable values from `nexus.toml` instead of literals. When shaping LLM responses, follow the structured-output practices in `CLAUDE.md` and prefer Pydantic models. Fail fast; do not add quiet fallbacks.

## Testing Guidelines
Pytest drives coverage; mirror test filenames to their targets (e.g., `test_chunk_operations.py`). Reuse fixtures from `tests/test_lore/conftest.py`, and `tests/pg_fixtures.py` for PostgreSQL. Cover Pass 1 baseline assembly and Pass 2 divergence detection in `tests/test_lore/test_memory_manager.py`; mark async turn checks with `pytest.mark.asyncio`. Tests that need PostgreSQL carry the `requires_postgres` marker and run only with `NEXUS_RUN_POSTGRES=1`; document the tables they depend on and keep mutations reversible. Prefer real code paths and real API calls over mocks.

## Commit & Pull Request Guidelines
Write concise, imperative commits (`Add divergence guard`). Stage and commit your work proactively; don't leave useful changes sitting unstaged when you pause or hand off. Pair code with its tests. Follow the autonomous branch/PR/review workflow in `docs/agent_workflow.md`. PRs should summarize impact, call out touched agents or memory modules, list manual verification commands, and note any updates to `nexus.toml` or database schema. Screenshots are only needed when changing rendered output.

## Security & Configuration Tips
Fetch API credentials via `nexus.util.secret_manager.get_secret(<account>)`; write them only through `set_secret`. The platform secret store is canonical (macOS Keychain service `nexus-api`, or `keyring` elsewhere), and the settings-pane API KEYS card is the supported write and rotation path. 1Password is not a runtime dependency; `scripts/sync_secrets.py` is only a deprecated personal migration shim. Each save slot is its own PostgreSQL database (`save_01` through `save_05`, selected by `NEXUS_SLOT`) with pgvector and PostGIS; `NEXUS_template` is the canonical schema reference, and the old `NEXUS` database is deprecated. Align local LLM endpoints with the models referenced in `nexus.toml`.

## Authorization & Access Requests
When work needs extra permissions (network, filesystem, etc.), try the action so the approval prompt can surface or spell out exactly what the user must enable—don't declare a hard "can't" if capability exists behind a permission gate.

# Repository Guidelines

## Project Structure & Module Organization
Core package lives in `nexus/`. Agents in `nexus/agents`: `lore` orchestrates the turn cycle, `memnon` handles retrieval, `gaia` tracks world state, and `psyche` analyzes characters. Custom two-pass memory lives in `nexus/memory/` (`manager.py`, `context_state.py`, `divergence.py`). Shared models sit in `nexus/models`. Tooling scripts stay under `scripts/`; reference material under `docs/`. Tests currently target LORE in `tests/test_lore/`. Runtime settings, including memory budgets and model defaults, live in top-level `settings.json`.

## Build, Test, and Development Commands
Bootstrap with `poetry install`. Run the suite using `poetry run pytest`; narrow scope with `poetry run pytest tests/test_lore/test_context_validation.py::test_sql_restoration`. Format via `poetry run black .`; type-check `poetry run mypy .`; lint `poetry run flake8`. Exercise MEMNON alone through `poetry run python run_memnon.py`.

## Coding Style & Naming Conventions
Adopt Black (88 columns) and flake8. Group imports stdlib/third-party/local and alphabetize. Use PascalCase for classes and snake_case elsewhere. Public functions and classes need docstrings and explicit type hints. Load configurable values from `settings.json` instead of literals. When shaping LLM responses, follow the structured-output practices in `CLAUDE.md` and prefer Pydantic models. Fail fast; do not add quiet fallbacks.

## Testing Guidelines
Pytest drives coverage; mirror test filenames to their targets (e.g., `test_chunk_operations.py`). Reuse fixtures from `tests/test_lore/conftest.py`. Add unit tests for Pass 1 baseline assembly and Pass 2 divergence detection outlined in `nexus/agents/lore/prompt.md`; mark async turn checks with `pytest.mark.asyncio`. Document required PostgreSQL tables (`narrative_chunks`, `chunk_metadata`, embeddings) when a test depends on live data, and keep mutations reversible.

## Commit & Pull Request Guidelines
Write concise, imperative commits (`Add divergence guard`). Pair code with its tests. PRs should summarize impact, call out touched agents or memory modules, list manual verification commands, and note any updates to `settings.json` or database schema. Screenshots are only needed when changing rendered output.

## Security & Configuration Tips
Fetch API credentials via the 1Password CLI helpers in `scripts/api_openai.py` and `scripts/api_anthropic.py`; never introduce environment variable fallbacks. Ensure `op` authentication and the `NEXUS` PostgreSQL instance with vector extensions are ready before runs. Align local LLM endpoints with the models referenced in `settings.json`.

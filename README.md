# NEXUS: Narrative Intelligence System

NEXUS is a turn-based interactive storytelling system that pairs a frontier
LLM storyteller with a deterministic memory and world-state engine. Apex-tier
models write excellent prose but cannot hold a long narrative in context or
attend to what happens off screen. NEXUS compensates on both fronts: a
PostgreSQL-backed retrieval stack reassembles the relevant past for every
turn, and an off-screen world engine keeps characters, factions, and places
evolving while the player is elsewhere.

The project is intentionally turn-based and quality-first. There are no skill
checks, no combat system, and no real-time constraints — latency is accepted
in exchange for richness of plot, depth of character, and high-quality prose.

## Architecture

Everything below exists and runs today; blueprints for unbuilt modules live
in `docs/blueprint_*.md`.

### Turn-Cycle Orchestration

Each turn is orchestrated deterministically (`nexus/agents/lore`,
`nexus/memory`): budget the context window, assemble the warm slice (recent
chunks plus user input), run retrieval, build the payload, integrate the
response. A two-pass memory system provides the baseline context for
generation (Pass 1) and then catches novel entity references in user input
via deterministic entity-based divergence detection (Pass 2,
`nexus/memory/divergence.py`).

There is no local-LLM intelligence in the loop. That layer was retired after
the May 2026 retrieval bake-off
(`docs/retrieval_query_bakeoff_2026_05_18.md`) showed that feeding raw chunk
text to the IR engine outperforms LLM-rewritten queries.

### MEMNON Retrieval

`nexus/agents/memnon` is the headless information-retrieval engine over the
narrative corpus. Production embeddings use Octen-Embedding-4B (2560d, the
issue #175 bake-off winner) stored in pgvector tables, combined with
IDF-weighted full-text search through configurable hybrid scoring, then
refined by cross-encoder reranking. See `docs/hybrid_search.md` and
`docs/vector_embeddings.md`.

### Skald via LOGON

Skald is the frontier storyteller (Claude or GPT family, configured in
`nexus.toml`). `nexus/agents/logon` owns the API traffic: structured-output
schemas (`nexus/agents/logon/apex_schema.py`), retry handling, and response
validation. Skald receives the assembled context payload and returns new
narrative plus authorial retrieval directives.

### Orrery World Engine

`nexus/agents/orrery` resolves off-screen behavior and is on by default
(`[orrery]` in `nexus.toml`). A deterministic package substrate ticks
characters, factions, and places through condition-gated templates; salient
resolutions are promoted by a post-commit worker
(`python -m nexus.agents.orrery.worker`) and narrated asynchronously into
`offscreen_narrations` — canonical prose the player never sees directly but
future scenes can draw on. Packages are self-aware in three stages
(entry-gating, branch-selection, outcome), so what an actor notices and
pursues depends on its tags and the target's fame. See
`docs/orrery_design_plan.md` and the generated catalog
`docs/orrery_packages.md`.

### Retrograde Deep History

Retrograde cures the cold-start problem by running Orrery backward: at
new-story setup it generates shallow-but-connected backstory as
pre-game-stamped `world_events`, retrievable by MEMNON exactly like
play-generated history. It fires automatically inside the new-story wizard
and continues at runtime by maturing entity stubs as they surface. See
`docs/orrery_retrograde_spec.md`.

### Save-Slot Fleet

Each save slot is its own PostgreSQL database (`save_01` through `save_05`),
selected via the `NEXUS_SLOT` environment variable. `NEXUS_template` is the
canonical fresh-slot image (schema, seed vocabulary, migration stamps).
Incremental schema changes go through `scripts/migrate.py`; fresh slots are
created with `scripts/new_story_setup.py`. Chunks become immutable once
accepted: accepting chunk N finalizes it and triggers embedding of N-1, so
embedded history is ironman.

### IRIS UI and the Gateway

`ui/` holds the React/TypeScript client (Vite, shadcn/ui) with Narrative,
Map, Characters, and Settings panes, a status bar, theming, and the
conversational new-story wizard (setting, character traits, story seed).

One origin serves everything: the FastAPI gateway
(`nexus.api.narrative:app`, port 8002) owns every API route, the
`/ws/narrative` websocket, and static serving of the built PWA
(`ui/dist/public`) plus runtime image uploads. Node is build-time only —
there is no Express layer. For development with HMR, the Vite dev server
(`npm --prefix ui run dev`, port 5001) serves the client and proxies
`/api`, `/ws`, and upload routes to the gateway.

## Quickstart

Requirements: Python 3.11, Poetry, PostgreSQL with pgvector and PostGIS,
Node.js for the UI, and local model weights for the embedder and reranker
(paths in `nexus.toml`). API keys live in the macOS Keychain; see
`CLAUDE.md` for key management.

```bash
poetry install
poetry run pre-commit install

# Database status and migrations
python scripts/migrate.py --status
python scripts/migrate.py --all

# Single-origin gateway (port 8002): APIs, websocket, and the built PWA
./iris

# UI development with HMR: Vite dev server (port 5001) proxying to the gateway
npm --prefix ui run dev

# Or drive a story from the command line
nexus load --slot 5
nexus continue --slot 5 --choice 1
```

CLI reference: `docs/cli.md`.

## Configuration

`nexus.toml` is the sole runtime configuration file, validated by Pydantic
models in `nexus/config/settings_models.py`. Model choices use
`@provider.role` references resolved against the `[global.model.api_models]`
registry at load time. The legacy `settings.json` is retired.

## Testing

```bash
poetry run pytest                          # offline tier (default)
NEXUS_RUN_POSTGRES=1 poetry run pytest     # + PostgreSQL integration tests
NEXUS_RUN_LIVE_LLM=1 poetry run pytest     # + live model endpoints
```

Tests marked `requires_postgres`, `live`, and `live_llm` skip unless their
flag is set, so the default sweep runs fast with no services required.
Formatting and linting: `poetry run black .`, `poetry run flake8`,
`poetry run mypy .`.

## Documentation

- `docs/turn_flow_sequence.md` — the turn cycle end to end
- `docs/orrery_design_plan.md` — world engine stages, schema, and workers
- `docs/orrery_retrograde_spec.md` — deep-history generation
- `docs/hybrid_search.md`, `docs/vector_embeddings.md` — retrieval stack
- `docs/agent_workflow.md` — branch, PR, and review workflow for agents
- `CLAUDE.md`, `AGENTS.md` — repository conventions for coding agents

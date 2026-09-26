# NEXUS CLI

A command-line interface for managing stories in NEXUS. All commands are slot-centric—just specify which save slot (1-5) you want to work with.

## Quick Start

```bash
# Start the API server (required)
poetry run python -m nexus.api.narrative

# In another terminal, check a slot's state
poetry run nexus load --slot 5

# Advance the story
poetry run nexus continue --slot 5
```

## Remote Runtimes

Story commands use `[runtime.remote].base_url` when `[runtime].profile` is
`"remote"`. `NEXUS_API_URL` remains an explicit override. If Cloudflare
Access protects the origin, configure secret-store account names—not token
values—in `nexus.toml`:

```toml
[runtime]
profile = "remote"

[runtime.remote]
base_url = "https://nexus.example.com"

[runtime.remote.cloudflare_access]
client_id_secret = "cloudflare_access_client_id"
client_secret_secret = "cloudflare_access_client_secret"
```

Store both values through `nexus.util.secret_manager.set_secret()`. On macOS
they live in Keychain service `nexus-api`. The CLI adds the two `CF-Access-*`
headers only for the configured origin and does not follow redirects while
carrying them.

To select an alternate config for story commands without editing the checkout:

```bash
NEXUS_RUNTIME_CONFIG=/path/to/remote.toml poetry run nexus load --slot 5
```

An explicit `NEXUS_API_URL` can select the same configured origin directly;
the Access headers are omitted if its origin differs from
`[runtime.remote].base_url`.

## Commands

### `usage` — View Exact API Token Usage

Reads the append-only provider telemetry for a UTC quota day. This command is
slotless and does not require a running gateway. Its totals are API-reported
usage, not NEXUS prompt-budget estimates.

```bash
# Current UTC day
poetry run nexus usage

# Specific UTC day, as machine-readable JSON
poetry run nexus usage --json --day 2026-07-29

# Restrict the event list and totals to one correlated run
poetry run nexus usage --json --run ab12cd34ef56
```

Human output lists totals by provider and logical seat, unknown-usage response
counts, the OpenAI-only UTC-day total, and configured readout-only allowances.
The JSON payload places `day`, `events`, `providers`, `seats`,
`openai_day_total`, and `allowance` under the `usage` key.

### `window-replay` — Replay Prompt Windows

Recomputes each recorded attempt's seat ceiling for one run under candidate
settings, keeping the recorded token counts. This command is slotless, makes
no provider calls, and reports tokens only.

```bash
# Current UTC day, under a candidate copy of nexus.toml
poetry run nexus window-replay --run ab12cd34ef56 --config candidate.toml

# Another model and prompt spend, as machine-readable JSON
poetry run nexus window-replay --json --run ab12cd34ef56 --day 2026-09-26 \
  --model MODEL_ID --window 90000
```

Each attempt keeps its recorded spend unless `--window` replaces it; a
candidate whose configured window differs from the runtime config's is refused.
Human output lists, per seat and attempt, the recorded input and ceiling, the
candidate ceiling, whether the model cap bounded the recorded spend, the
ceiling delta, overflow, trimmable memory tokens, feasibility, and freed
tokens. The JSON payload places `run`, `day`, `config`, and `rows` under the
`window_replay` key. See `docs/settings_scopes.md` for the field semantics.

### `load` — View Current State

Shows the current state of a slot: wizard phase, narrative text, or empty status.

```bash
poetry run nexus load --slot 5
```

### `continue` — Advance the Story

The main command for progressing through the wizard or narrative.

```bash
# Basic advance
poetry run nexus continue --slot 5

# Select a numbered choice (during narrative)
poetry run nexus continue --slot 5 --choice 2

# Provide custom input
poetry run nexus continue --slot 5 --user-text "I search the room"

# Send your edited version of a numbered choice (one request: the number
# is kept and the edited text is recorded as the player's action)
poetry run nexus continue --slot 5 --choice 2 --text "Ask Sana, quietly, about the torn page"

# Auto-advance without input (Accept Fate)
poetry run nexus continue --slot 5 --accept-fate

# Use a specific model
poetry run nexus continue --slot 5 --model TEST
```

### `retry` — Retry a Failed Continuation

When a continuation fails after your action was recorded, `load` shows the
failure and this command. `retry` resumes that recorded action without choosing
or recording it again, then prints the new turn the way `continue` does. It
exits with an error when the slot reports no failed continuation, and the
server rejects it if a newer attempt has replaced that failure.

```bash
poetry run nexus retry --slot 5
```

### `regenerate` — Re-Roll the Pending Turn

Regenerates the pending storyteller turn from the same parent and player text.
The current draft stays until its replacement is staged, so a failed
regeneration leaves it in place. `--note` adds an optional out-of-character
note to the storyteller, at most 500 characters.

```bash
poetry run nexus regenerate --slot 5
poetry run nexus regenerate --slot 5 --note "darker, plz"
```

### `clear` — Reset a Slot

Clears wizard state and returns the slot to empty.

```bash
poetry run nexus clear --slot 5
```

### `undo` — Revert Last Action

Steps back to the previous state (wizard phase or narrative chunk).

```bash
poetry run nexus undo --slot 5
```

### `model` — Manage LLM Model

View or change which language model a slot uses.

```bash
# Show current model
poetry run nexus model --slot 5

# Change model
poetry run nexus model --slot 5 --set TEST

# List available models
poetry run nexus model --list
```

Available models:
- `gpt-5.1` — Default production model
- `TEST` — Mock responses for development
- `claude` — Anthropic Claude

### `models` — Lock or Verify Model Artifacts

Pins the local production embedder and reranker files (not the LLM that
`model` selects). Neither verb downloads anything.

```bash
# Hash the local artifacts and write [memnon.artifacts].lock_file
poetry run nexus models lock

# Read-only check; exits 1 naming each problem and its restore command
poetry run nexus models verify
```

See `docs/vector_embeddings.md` for what the lock records.

### `lock` / `unlock` — Protect Slots

Lock a slot to prevent accidental modifications.

```bash
poetry run nexus lock --slot 1
poetry run nexus unlock --slot 1
```

## JSON Output

Add `--json` for machine-readable output:

```bash
poetry run nexus load --slot 5 --json
```

## Artifact Display

When the wizard generates artifacts (world settings, character concepts, etc.), the CLI displays a summary:

```
=== World Document ===
  World: Neon Palimpsest
  Genre: cyberpunk
  Secondary: scifi, noir
  Tone: dark
  Tech Level: near_future
  Themes: memory and identity, surveillance vs. secrecy, ...

[Wizard Phase: setting (complete)]
```

Use `--json` flag to see the full artifact data structure.

## Example: Full Wizard Playthrough

Starting from an empty slot and completing the wizard with mock responses:

```bash
# Reset to empty
poetry run nexus clear --slot 5

# Initialize wizard
poetry run nexus continue --slot 5 --model TEST

# Advance through each phase (setting, character, traits, wildcard, seed)
poetry run nexus continue --slot 5 --model TEST --accept-fate
poetry run nexus continue --slot 5 --model TEST --accept-fate
poetry run nexus continue --slot 5 --model TEST --accept-fate
poetry run nexus continue --slot 5 --model TEST --accept-fate
poetry run nexus continue --slot 5 --model TEST --accept-fate

# Transition to narrative (when phase is "ready")
poetry run nexus continue --slot 5

# Check narrative state
poetry run nexus load --slot 5
```

## Troubleshooting

**"Cannot connect to API server"**
Start the server: `poetry run python -m nexus.api.narrative`

**"Slot is not in wizard mode"**
The slot has already transitioned to narrative. Use `clear` to reset.

**"No wizard state found"**
The slot is empty. Run `continue` to initialize.

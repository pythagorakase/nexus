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

## Commands

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

# Auto-advance without input (Accept Fate)
poetry run nexus continue --slot 5 --accept-fate

# Use a specific model
poetry run nexus continue --slot 5 --model TEST
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

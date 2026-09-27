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

Under a remote runtime, only HTTP commands run. Commands that would open a
slot database or act on this machine's runtime files are refused before they
connect to anything; see Transports below.

## Command Contract

`nexus/cli_contract.py` declares every command's transport, the exit codes,
and the JSON envelopes. A test walks the parser and fails when a command is
added without a declared transport, or when the registry names a command that
no longer exists.

### Exit Codes

| Code | Meaning | JSON `code` values |
| --- | --- | --- |
| 0 | Success | — |
| 1 | Domain failure: the command ran and failed | `domain_failure`, `not_found`, `api_error`, `invalid_response`, `config_error` |
| 2 | Usage: unusable arguments (argparse errors also exit 2) | `usage_error` |
| 3 | Transport refused under a remote runtime | `transport_refused` |
| 4 | The NEXUS API could not be reached or did not answer in time | `api_unreachable` |

Expected failures are reported through these codes. A missing or invalid
active `nexus.toml`, a malformed `NEXUS_API_URL`, or a missing runtime
credential is a `config_error`, checked for every command before it runs. A
traceback means a programming fault.

### Transports

Each command declares the most privileged resource its handler opens:

| Transport | Opens | Commands |
| --- | --- | --- |
| `http` | The NEXUS API only | `load`, `continue`, `retry`, `undo`, `regenerate`, `clear`, `lock`, `unlock`, `inspect slot`, `model --set`, `model --clear` |
| `database` | A slot database directly | `model` (reading seat identities), `jobs`, `inspect-turn`, `prune-manifests`, `trait-audit`, `retrograde-packet`, `retrograde-seed-candidates --slot`, `retrograde-apply-expansion`, `retrograde-embed-history`, `record-revelation`, `faction-audit`, and the faction, character, and place manifest and apply commands |
| `local_operator` | This machine's processes, logs, runtime home, usage ledger, model artifacts, local files, or provider credentials | `up`, `down`, `restart`, `status`, `logs`, `home`, `usage`, `window-replay`, `models lock`, `models verify`, `model --list`, `retrograde-seed-candidates --packet`, `retrograde-expand-seeds`, `backfill-review-packet` |

The runtime is remote when the active `nexus.toml` sets `[runtime] profile =
"remote"`, or when `NEXUS_API_URL` names a host other than `localhost` or a
loopback address. A remote runtime refuses `database` and `local_operator`
commands with exit 3 before any connection is opened. Two exceptions follow
the remote profile itself: `up` and `status` probe the hosted runtime's
`/runtime/status` over HTTP. The runtime commands that accept `--config`
(`up`, `down`, `restart`, `status`, `logs`, `models lock`, `models verify`)
check the profile of that file.

Only the host name decides: a LAN address, a Tailscale name, or `0.0.0.0`
counts as remote even when it reaches this machine, so every `database` and
`local_operator` command, `up`, `status` and `logs` included, is refused while
`NEXUS_API_URL` names it. Point `NEXUS_API_URL` at `localhost` or `127.0.0.1`
for this machine's runtime.

### JSON Failure Envelope

With `--json`, every failure prints one object on stderr:

```json
{
  "ok": false,
  "code": "api_unreachable",
  "error": "Cannot connect to API server at http://localhost:8002",
  "partial": {}
}
```

`error` is the same message string earlier releases printed as
`{"error": ...}`. `partial` holds every non-empty field of the failed result
(a saved seed, a session ID, a recovery command); `false` and `0` are kept,
`null` and empty values are not. Without `--json`, a failure prints one
`Error: <message>` line on stderr.

One failure keeps its report instead: `trait-audit --fail-on-remainders`
prints the full audit on stdout with `"failed_policy": true` and exits 1.

Success output is unchanged for existing commands. JSON-first commands
(`inspect slot`) print `{"ok": true, "data": ...}` on stdout.

## Commands

### `inspect slot` — Read a Slot's State as JSON

Reads `GET /api/slot/{slot}/state`, the player-plane `slot.read` route, and
returns its body unchanged under `data`. Nothing is written. The request
timeout is `[runtime.cli].inspect_timeout_seconds`.

```bash
poetry run nexus inspect slot --slot 5 --json
```

Exits 1 with `not_found` when the gateway answers 404, and 4 with
`api_unreachable` when nothing answers. Without `--json`, the state prints as
one field per line.

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
# is kept and the edited text is recorded as the player's action). Narrative
# mode only; the wizard refuses --choice with --text.
poetry run nexus continue --slot 5 --choice 2 --text "Ask Sana, quietly, about the torn page"

# Auto-advance without input (Accept Fate)
poetry run nexus continue --slot 5 --accept-fate

# Use a specific model
poetry run nexus continue --slot 5 --model TEST

# Set the new story's strangeness (wizard only)
poetry run nexus continue --slot 5 --weird high
```

`--weird low|medium|high` records the new story's strangeness on the wizard
before the step runs, so any later transition uses it, and the transition that
creates the world carries it too. It is the player's appetite for surprise,
not a promise of bizarre content: Retrograde maps the level onto the story
genre's band in `[orrery.retrograde.weird.bands_by_genre]`, and a wizard with
no selection uses `[orrery.retrograde.weird].default_level`. The transition
records the selected level (null when none was chosen) beside the resolved
level, genre, and band as `global_variables.genesis_weird`, and `load --json`
shows the stored level.
A slot already in narrative mode rejects the flag.

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

Failures use the envelope described in JSON Failure Envelope above.

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

# Transition to narrative (when phase is "ready"), optionally at a strangeness
poetry run nexus continue --slot 5 --weird medium

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

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
| 1 | Domain failure: the command ran and failed | `domain_failure`, `not_found`, `api_error`, `invalid_response`, `config_error`, `database_error` |
| 2 | Usage: unusable arguments, argparse's own rejections included | `usage_error` |
| 3 | Transport refused under a remote runtime | `transport_refused` |
| 4 | The NEXUS API could not be reached or did not answer in time | `api_unreachable` |

Expected failures are reported through these codes. A missing or invalid
active `nexus.toml`, or a `NEXUS_API_URL` without a host, is a `config_error`
checked for every command but `doctor` before it runs. A `NEXUS_API_URL` that
is not `http://` or `https://`, and a runtime credential that is missing or
refused, are a `config_error` when the first request is sent. Every HTTP
command reports these, and an API that refuses or drops the connection or
does not answer in time (exit 4), the same way.

The play and slot commands (`load`, `continue`, `retry`, `undo`,
`regenerate`, `clear`, `lock`, `unlock`, `model --set`/`--clear`) and every
`inspect` verb classify the API's answers the same way:

- A non-2xx answer is `api_error`.
- A 401, a 403, or a redirect that is not followed is `config_error`. The
  gateway itself answers none of them, so an edge in front of it, such as
  Cloudflare Access, rejected the request. Requests follow redirects unless
  they carry a runtime credential, so a redirect is reported only when one
  was sent.
- When a command's own read rejects the answer, `partial.status_code` carries
  the HTTP status. A non-2xx answer's error is `API error: <body>` (an
  `inspect` verb names the URL and the status instead), and an access
  rejection's error names the URL, the status, a redirect's `Location`, and
  `[runtime.remote.cloudflare_access]`.
- The steps that keep their own wording report the same code with their own
  message and `partial`, and name no Access setting: wizard setup and the
  transition to narrative (the answer's body), the wizard's `--weird` and
  character-revision requests (the body, with `partial.status_code`), the
  wizard's artifact confirmations and phase introductions (the body, with a
  recovery command), the seed transition (the status in
  `transition_error.status_code`), the opening turn (`bootstrap_error`), and
  the generation wait (`generation_error`); the last two name the URL and the
  status in their detail.
- The `inspect` verbs report a 404 as `not_found`, before either rule above.
- Any other failed request, one that got no usable answer (a followed
  redirect loop, a body whose content encoding is broken), is a domain
  failure.
- A handler's read of a 2xx body that is not a JSON object is
  `invalid_response`; an unusable body during a generation wait, or of the
  opening turn's schedule answer, stays a domain failure with
  `generation_error.status` or `bootstrap_error` naming it.
- `model --slot N` reads the slot database itself; a database it cannot open
  or query is `database_error`, and a story pin naming a model no longer in
  the registry is a domain failure whose error names the `--clear` remedy.

Only a command that already saved work (a confirmed artifact, a saved seed, a
scheduled turn) reports a later failed request itself, with a `partial` that
keeps that work and its recovery command: as `api_unreachable` (exit 4) when
the gateway refused or dropped the connection, as `api_error` for a non-2xx
answer, as `config_error` for an access rejection, otherwise as a domain
failure. A traceback means a programming fault.

`[runtime.cli].request_timeout_seconds` bounds each short request of `load`,
`continue`, `retry`, `undo`, `regenerate`, `clear`, `lock`, `unlock`, and
`model --set`/`--clear`. `[runtime.cli].turn_request_timeout_seconds` bounds
each model-turn request: wizard chat, trait toggles, phase introductions, and
the POSTs that schedule `continue`, `retry`, `regenerate`, and the seed's
opening turn. The wizard's transition to narrative takes
`[orrery.retrograde.wizard].transition_timeout_seconds`. Waiting on a
generation session is described in Waiting on a Generation below.

### Transports

Each command declares the most privileged resource its handler opens:

| Transport | Opens | Commands |
| --- | --- | --- |
| `http` | The NEXUS API only | `load`, `continue`, `retry`, `undo`, `regenerate`, `clear`, `lock`, `unlock`, every `inspect` verb, `model --set`, `model --clear` |
| `database` | A slot database directly | `model` (reading seat identities), `jobs`, `inspect-turn`, `prune-manifests`, `trait-audit`, `retrograde-packet`, `retrograde-seed-candidates --slot`, `retrograde-apply-expansion`, `retrograde-embed-history`, `record-revelation`, `faction-audit`, `tags audit` (which also reads `NEXUS_template`), and the faction, character, and place manifest and apply commands |
| `local_operator` | This machine's processes, logs, runtime home, usage ledger, model artifacts, local files, or provider credentials | `up`, `down`, `restart`, `status`, `logs`, `home`, `doctor`, `usage`, `window-replay`, `models lock`, `models verify`, `model --list`, `retrograde-seed-candidates --packet`, `retrograde-expand-seeds`, `backfill-review-packet` |

The runtime is remote when the active `nexus.toml` sets `[runtime] profile =
"remote"`, or when `NEXUS_API_URL` names a host other than `localhost` or a
loopback address. A remote runtime refuses `database` and `local_operator`
commands with exit 3 before any connection is opened. Two exceptions follow
the remote profile itself: `up` and `status` probe the hosted runtime's
`/runtime/status` over HTTP. The runtime commands that accept `--config`
(`up`, `down`, `restart`, `status`, `logs`, `models lock`, `models verify`)
check the profile of that file. `doctor` is exempt from the refusal and from
the configuration check below: it diagnoses this machine's configuration and
role itself, so it runs under any profile, and an invalid `nexus.toml` is its
`config.valid` finding rather than a `config_error`.

Only the host name decides: a LAN address, a Tailscale name, or `0.0.0.0`
counts as remote even when it reaches this machine, so every `database` and
`local_operator` command, `up`, `status` and `logs` included, is refused while
`NEXUS_API_URL` names it. Point `NEXUS_API_URL` at `localhost` or `127.0.0.1`
for this machine's runtime.

### JSON Failure Envelope

With `--json` anywhere on the command line, every failure prints one object
on stderr, argparse's rejection of the arguments included:

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
`Error: <message>` line on stderr, and argparse prints its usage and error
lines.

One failure keeps its report instead: `trait-audit --fail-on-remainders`
prints the full audit on stdout with `"failed_policy": true` and exits 1.

Success output is unchanged for existing commands. JSON-first commands
(every `inspect` verb and `tags audit`) print `{"ok": true, "data": ...}` on stdout.

### Waiting on a Generation

`continue`, `retry`, `regenerate`, and the opening turn after the seed is
saved all schedule a generation session and then wait on it through one
helper, `nexus.cli.wait_for_session`:

- It reads `GET /api/narrative/status/{session_id}?slot=N` every
  `[runtime.cli].poll_interval_seconds` until the session reports a terminal
  status, and returns that terminal status payload.
- `[apex].generation_timeout_seconds` bounds the status polling. A single
  status read may take the remaining budget, since a turn generating inside
  the gateway can hold the read until it finishes.
- After the helper returns, its caller (`_wait_for_narrative_result`) loads
  the new turn with one more read, `GET /api/slot/{slot}/state`, under its own
  `[runtime.cli].request_timeout_seconds` budget. The generation budget does
  not bound that load.
- A session the API reports as failed is a domain failure (exit 1) whose
  `error` is the API's own message.
- A non-2xx answer to a status read or the state load is `api_error`, or
  `config_error` for a 401, a 403 or an unfollowed redirect (exit 1), with
  `generation_error.status` `http_error`.
- A session still running when the budget ends, a read that times out
  (before its headers arrive or while its body stalls after them), any other
  failed request (too many redirects, for example), or an unusable payload is
  a domain failure (exit 1).
- A gateway that refuses or drops the connection mid-wait, a body cut off
  mid-answer included, is `api_unreachable` (exit 4). A failed read is never
  retried.

Every failed wait keeps the scheduled work in `partial`: `session_id`,
`generation_error` (`status` and `detail`), and `recovery_command`
(`nexus load --slot N`), plus the saved seed when the opening turn failed.

## Commands

### `inspect` — Read Story Records as JSON

Each verb reads GET routes that `nexus/api/route_capabilities.py` declares on
the player plane and puts what they answer under `data`. Each record is the
route's own payload, unchanged. `inspect chunks` lists those payloads oldest
first, and `inspect incubator` reports the route's empty answer as `null`.
Nothing is written. Each request's timeout is `[runtime.cli].inspect_timeout_seconds`.
`--slot` is required.

| Verb | Routes | `data` |
| --- | --- | --- |
| `inspect slot` | `/api/slot/{slot}/state` | The slot state |
| `inspect chunks --last N` | `/api/narrative/latest-chunk`, then `/api/narrative/chunks/{id}/adjacent` backwards | The newest N committed chunks, oldest first; `[]` for an unplayed story. One sequential request per chunk |
| `inspect chunks --from A --to B` | `/api/narrative/chunks/{id}/adjacent` forwards from A | The committed chunks with ids A through B. `--from` may be left out (it starts at the first chunk); `--from` without `--to` is a usage error. One sequential request per chunk in the range, and one more when no committed chunk has id B |
| `inspect chunk ID` | `/api/narrative/chunks/{id}` | One committed chunk |
| `inspect incubator` | `/api/narrative/incubator` | The pending draft, or `null` when none waits |
| `inspect characters [ID]` | `/api/characters` (with `startId`/`endId` for one) | The list, or the one character |
| `inspect places [ID]` | `/api/places` | The list, or the one place |
| `inspect factions [ID]` | `/api/factions` | The list, or the one faction |

```bash
poetry run nexus inspect slot --slot 5 --json
poetry run nexus inspect chunks --slot 5 --last 2 --json
poetry run nexus inspect chunks --slot 5 --from 40 --to 45 --json
poetry run nexus inspect chunk 45 --slot 5 --json
poetry run nexus inspect incubator --slot 5 --json
poetry run nexus inspect characters --slot 5 --json
poetry run nexus inspect places 3 --slot 5 --json
```

`inspect chunks` takes `--last` or a `--from`/`--to` range, not both; a bad
combination is a usage error (exit 2). A chunk or entity id the route does not
serve exits 1 with `not_found`, a body the verb cannot pass through unchanged
exits 1 with `invalid_response`, and nothing answering exits 4 with
`api_unreachable`. Without `--json`, a record prints as one field per line, a
list as one such block per record.

Interactions, queues, settings, and secrets status have no inspect verb yet:
they have no player-plane read route.

### `tags audit` — Report Tags in Deprecated Categories

`tag_category_registry` marks a category deprecated and names its
`replacement_categories`, but rows bestowed before the deprecation stay
active. `tags audit` reports, per database, the active `entity_tags` rows
(`cleared_at IS NULL`) whose tag's category the registry deprecates, grouped
by category and tag with the registry's replacements, the row count, and the
canonical entity ids. `--slot N` reads one slot; `--all` reads
`NEXUS_template` and every slot. Each database is read in one read-only
transaction, so a locked slot is read like any other, and nothing is written
or enforced.

```bash
poetry run nexus tags audit --slot 4
poetry run nexus tags audit --all --json
```

Without `--json` it prints one row count per database, then one line per
category and tag. A database without `tag_category_registry` (or its
`deprecated` and `replacement_categories` columns) stops the audit with exit
1, naming the migration that creates it; the envelope's `partial` keeps the
databases already read.

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

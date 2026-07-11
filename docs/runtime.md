# The NEXUS Runtime Contract

This document defines the boundary between NEXUS clients and the NEXUS
runtime. It is written for the author of a future client — a desktop shell
(Electron/Tauri/native), a hosted web client, or any other front end — so
that targeting NEXUS never requires knowledge of its internal process
topology. Issues #396 (managed runtime) and the gateway consolidation in
PR #400 are the provenance.

## One Origin

A NEXUS runtime is **one HTTP(S) origin**. That origin serves:

- every API route (`/api/...`),
- the narrative websocket (`/ws/narrative`),
- liveness (`/health`) and the runtime status aggregate (`/runtime/status`),
- the built PWA and runtime image uploads (static routes, registered last).

Single-ASGI-origin is the converged end state, achieved in PR #400: the
FastAPI gateway (`nexus.api.narrative:app`) is the entire serving surface.
There is no Express layer, no sidecar API process, and no UNIX socket —
everything a client needs is loopback or remote TCP against one base URL.
A client that works against `http://127.0.0.1:8002` works against
`https://nexus.example.com` by changing its base URL and nothing else.

## The Runtime Endpoint

`GET /runtime/status` is the runtime's self-description. Clients use it for
"is my backend alive and what am I talking to" — not just process liveness
(`/health` answers that) but aggregate health:

```json
{
  "profile": "local",
  "version": "0.1.0",
  "slot": 5,
  "database": {"ok": true, "slot": 5, "dbname": "save_05"},
  "services": {
    "gateway": {"ok": true, "port": 8002},
    "mock_openai": {"ok": true, "port": 5102}
  },
  "auth": {"header": "X-Nexus-Auth", "enforced": false},
  "ok": true
}
```

Field semantics:

- `profile` — how this runtime is operated (see Profiles below).
- `version` — the installed `nexus` package version.
- `slot` / `database` — the active save slot and a live `SELECT 1` against
  its database; `database.ok == false` carries an `error` string.
- `services` — per-service health. `gateway` is always present (it answered
  the request). Model-backend services appear when enabled; absence means
  "not part of this runtime", not failure.
- `auth` — the reserved auth header name and whether this runtime enforces
  it.
- `ok` — conjunction of everything above; a client can gate its "connected"
  indicator on this single bit.

The canonical path and header names live in `nexus/runtime/contract.py`.

## Reserved Auth Header: `X-Nexus-Auth`

Every client request SHOULD carry the header

```
X-Nexus-Auth: <opaque credential>
```

Semantics, fixed now so clients never need retrofitting:

- The value is an **opaque bearer credential** issued by the runtime
  operator. Clients store and transmit it; they never parse it.
- **Local profile (today): the header is a no-op.** The runtime ignores it
  and `auth.enforced` is `false` in `/runtime/status`. Sending it anyway is
  the contract — a client built today must already have the plumbing.
- **Hosted runtimes (future): the header is required.** Requests without a
  valid credential are rejected; `auth.enforced` will be `true`.
- Browsers cannot attach custom headers to native `WebSocket` connects, so
  hosted runtimes will accept the same credential for the websocket via the
  first client message or a query token at connect time; the header remains
  authoritative for all HTTP routes.

## Profiles

The runtime is operated in one of three profiles, configured in
`nexus.toml` under `[runtime]` and reported in `/runtime/status`:

| Profile    | Who runs the processes | What `nexus up` does | What `nexus status` does |
|------------|------------------------|----------------------|--------------------------|
| `local`    | The supervisor (`nexus/runtime/`): spawns services detached with pidfiles and captured logs under `[runtime].state_dir` | Spawns enabled services, waits for health, fails loud with log excerpts | Merges supervisor process state (pid, port, uptime) with `/runtime/status` |
| `external` | You (or an IDE, a debugger, another orchestrator) | Health-checks the configured URLs; **spawns nothing**; nonzero exit if anything is down | Reads `/runtime/status` from `external.gateway_url` |
| `remote`   | A hosted operator | Confirms `<remote.base_url>/runtime/status` answers | Reads the remote runtime's status |

`nexus down`, `restart`, and `logs` are local-profile verbs: they manage or
read state that only exists when this machine's supervisor owns the
processes, and they fail loudly in other profiles.

### Local profile mechanics

- Services are declared in `[runtime.services.<name>]`: an argv `command`
  template (`{python}`, `{host}`, `{port}` placeholders — no shell), `port`,
  `health_path`, extra `env`, an `enabled` mode, and an `autorestart`
  policy.
- The supervisor is pure Python and cross-platform by construction: process
  spawning uses `subprocess` with platform-appropriate detach flags,
  liveness checks never signal the process, and all observation is loopback
  TCP. Linux and Windows hosts are intended targets; nothing in the runtime
  path shells out or touches UNIX sockets.
- State lives under `[runtime].state_dir` (default `.nexus/runtime`):
  `<service>.pid.json` records pid/port/slot/start time; `<service>.log`
  captures stdout+stderr. Logs survive `nexus down` for postmortems.
- `nexus up --foreground` keeps the supervisor attached: it streams
  prefixed service logs to the console, honors `autorestart = "on-failure"`
  (bounded by `autorestart_max_retries`), and tears everything down on
  Ctrl+C. `./iris` is a thin alias for exactly this.
- `nexus up` refuses ports held by unmanaged processes and refuses to
  double-start; partial startups are rolled back so `up` is all-or-nothing.

## CLI Surface

```
nexus up [--slot N] [--foreground] [--config PATH]
nexus down [service] [--config PATH]
nexus restart [service] [--slot N] [--config PATH]
nexus status [--config PATH]
nexus logs [service] [-n LINES] [-f] [--config PATH]
```

All verbs honor the global `--json` flag for machine-readable output.
`--config` points at an alternate `nexus.toml` (test harnesses, parallel
checkouts); spawned services receive its absolute path in the
`NEXUS_RUNTIME_CONFIG` environment variable so their `/runtime/status`
describes the config that actually launched them.

## Model Backends Are Runtime Services

Remote model providers (OpenAI, Anthropic) are reached through their native
SDKs. **Every other model backend is an OpenAI-compatible server registered
in config, not in code**: a provider section in
`[global.model.api_models.<name>]` with a `base_url` is the complete
integration. The mock TEST server is one such row; a local
Ollama/vLLM-served model (e.g. a hermes-class model) is another — add the
provider section, list its models, point `base_url` at the server, and
every request builder routes to it.

The supervisor treats these the same way: `[runtime.services.mock_openai]`
spawns the mock server only while the TEST provider is registered
(`enabled = "auto"`), and config load cross-validates that the service port
and the registry `base_url` agree.

`[runtime.services.llama_server]` defines the headless llama.cpp server for
the `@local` provider. It is shipped with `enabled = "never"` because loading
the configured Q6_K model consumes about 58 GB, so ordinary `nexus up` runs do
not start it. For an on-demand session, run the configured `command` directly;
it binds `127.0.0.1:1234`, exposes `/v1` and `/health`, and can be stopped with
Ctrl+C. To make the supervisor own it, set `enabled = "always"` and run
`nexus up`; use `nexus down llama_server` when it should be unloaded again.

Per-model request-parameter capability also lives in the registry: an
entry's `unsupported_params` lists parameters its API rejects (e.g.
`temperature` on reasoning-class models), and configuration that sets such
a parameter for that model is refused at config load. Request builders only
send explicitly configured parameters, so a provider can never receive a
parameter it rejects.

## Embedder and Reranker Run Host-Side

MEMNON's embedding model (Octen-Embedding-4B) and cross-encoder reranker
load **inside the gateway process** from local weights (paths in
`nexus.toml` `[memnon]`). They use MPS on Apple Silicon and CUDA on Linux
hosts. Consequences for deployment:

- The runtime host needs the model weights and a supported accelerator (or
  tolerable CPU latency); clients never see this — retrieval is behind the
  API boundary.
- A hosted runtime carries its own weights; nothing model-related crosses
  the client contract.

## Secrets per Profile

- **Local (macOS):** API keys live in the macOS Keychain (service
  `nexus-api`), read by `nexus.util.secret_manager.get_secret()` via the
  system `security` CLI — silent, no prompts in unattended runs. The API KEYS
  settings card is the supported write and rotation path.
- **Non-Mac hosts (Linux/Windows):** the canonical store is the platform's
  Python `keyring` backend. CI and hosted runtimes may set
  `NEXUS_KEYRING_DISABLE=1` and inject `<PROVIDER>_API_KEY` environment
  variables as a read-only escape hatch.
- **Clients never receive provider keys.** The settings pane sends a draft
  directly to `PUT /api/secrets/{provider}` and retains it only until that
  request completes; status responses contain at most the last four
  characters. Model calls remain runtime-side.
- Keyless local model servers (mock, Ollama) need no secret; a base_url
  provider that does need one names its secret-store account via
  `api_key_secret`.

## Development Workflows (unchanged)

- `npm --prefix ui run dev` — Vite dev server with HMR on :5001, proxying
  `/api`, `/ws`, and uploads to the gateway on :8002. Start the gateway
  with `nexus up` (or point Vite at an `external`-profile stack).
- `npm --prefix ui run build` — produces `ui/dist/public`, which the
  gateway serves statically. `nexus up` warns if the build is missing.
- Test harnesses run parallel runtimes by passing `--config` with their own
  ports and state dirs; the golden-path gate and agent worktrees use
  8030+/5130+ to stay clear of a developer's stack.

## What a Desktop Shell Needs to Know

The entire integration surface for a macOS/Windows/Linux shell:

1. Run `nexus up` (or link `nexus/runtime/` and call
   `Supervisor.from_config().up()`); the runtime owns its processes.
2. Point a webview at the gateway origin.
3. Poll `GET /runtime/status`; gate the UI on `ok`.
4. Send `X-Nexus-Auth` on every request (empty locally is fine today).
5. Run `nexus down` on quit.

Nothing else about NEXUS internals — slots, databases, model processes,
embedders — leaks across this boundary.

The Tauri shell added for issue #399 implements this contract in
`ui/src-tauri/`; see `docs/desktop.md` for run/build commands, the
checkout-level desktop config, and the preserved browser workflow.

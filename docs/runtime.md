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
`https://nexus.example.com` by changing its base URL and, when the remote
origin is Access-protected, configuring its edge-auth secret references.

The gateway is also the only application: the `nexus.api` package exports
none. #807 retired the pre-gateway Storyteller app (`nexus/api/storyteller.py`),
its file-backed session store, and `GET /api/chunks/states`, which always
answered 500, after a caller inventory found no client
(`docs/qa/807-one-gateway/inventory.md`). The Storyteller app's setup routes
were already served by the gateway.

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
  "ok": true,
  "readiness": {
    "schema_version": 1,
    "target": "owner-host",
    "ok": true,
    "checks": [
      {"id": "config.valid", "status": "pass", "...": "..."},
      {"id": "tools.pg_dump", "status": "pass", "...": "..."},
      {"id": "ui.bundle", "status": "pass", "...": "..."}
    ],
    "omitted": ["postgres.reachable", "...", "secrets.seat_providers"]
  }
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
- `readiness` — the owner-host readiness checks the gateway evaluates
  in-process, in the schema `nexus doctor --json` prints (see Readiness
  Checks). It never feeds `ok`; `omitted` names the checks only
  `nexus doctor` runs.

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
- A non-empty credential is sent only over HTTPS, except for genuine loopback
  HTTP targets used by local development. Credential-bearing requests never
  follow redirects.
- Browsers cannot attach custom headers to native `WebSocket` connects, so
  hosted runtimes will accept the same credential for the websocket via the
  first client message or a query token at connect time; the header remains
  authoritative for all HTTP routes.

### Cloudflare Access edge authentication

Cloudflare Access can protect a hosted origin without adding authentication
code to NEXUS. It is an outer edge boundary, independent of
`X-Nexus-Auth`. A service-token client sends both:

```
CF-Access-Client-Id: <service-token ID>
CF-Access-Client-Secret: <service-token secret>
```

The remote configuration stores only secret-store account names:

```toml
[runtime.remote]
base_url = "https://nexus.example.com"

[runtime.remote.cloudflare_access]
client_id_secret = "cloudflare_access_client_id"
client_secret_secret = "cloudflare_access_client_secret"
```

The CLI and supervisor resolve those accounts only while making a request to
the exact configured HTTPS origin. Configuration rejects plaintext or
ambiguous credential-bearing URLs. Requests carrying any non-empty credential
do not follow redirects, preventing custom headers from crossing to another
origin. Both references are required when the block is present; missing
credentials fail the request rather than falling back to interactive browser
login.

## Player and Operator Planes

Every route, websocket, and static mount the gateway registers is classified
in one table, `ROUTE_CAPABILITIES` in `nexus/api/route_capabilities.py`,
keyed by `(method, path template)`, `("WS", path)`, or `("MOUNT", path)`.
Handlers are not decorated. Each entry records the plane, a capability group,
the slot mode (`none`, `read`, `write`), whether the request can start
model-provider work, and whether it can irreversibly wipe a story, an
in-progress wizard, uploaded images, a stored credential, or a downloaded
model.

| Plane | Serves |
|---|---|
| Player | Liveness (`/health`, `/status`), reading routes, narrative turns (continue, retry, regenerate, approve, select-choice, undo, discarding the pending turn), the new-story wizard, preferences, `/ws/narrative`, the upload mounts, and the app shell |
| Operator | The player plane plus secrets, `/api/settings`, local models, diagnostics (`/runtime/status`, `/api/dev/*`, the OpenAPI schema and docs), slot lock, unlock, and model pins, `setup/reset`, `slot/select`, and asset uploads, main-image changes, and deletes |

The player plane can overwrite any unlocked slot through the wizard, occupied
or not; the slot lock is the only guard. `setup/start` discards the slot's
in-progress wizard and trait selections and persists the resolved wizard model
as the slot's Skald pin, so its `model` override replaces the pin that
`PATCH /api/slot/{slot}/settings` otherwise sets only on the operator plane.
`transition` deletes the slot's existing world. The registry marks both routes
destructive.

`build_player_app(app)` and `build_operator_app(app)` project new FastAPI
apps from the gateway. Each reuses the gateway's route objects in
registration order (the app-shell catch-all stays last), its middleware,
exception handlers, metadata, and root path, and runs the gateway's lifespan
against the gateway app itself so shared handlers see one scheduler; only one
projection may run that lifespan at a time. Serving the gateway app itself
beside a projection in one process is not yet detected.

The registry rule: a route enters the gateway only with an entry.
`nexus.api.narrative` calls `require_classified(app)` at import, so an
unclassified route, a route whose methods span both planes, or a route
registered after the app-shell catch-all fails the import, and the
projections refuse the same. `tests/test_api/test_route_capabilities.py`
also fails on entries no route uses.

The gateway still serves the whole runtime on one listener. Binding the
operator projection to loopback or a Unix socket, pointing the Cloudflare
tunnel at the player projection, and routing the Tauri shell to the operator
projection is the next slice, after the runtime home (#820). Before the
tunnel moves, the player client's reads of `/api/settings` (including its
`HEAD` connectivity probe) and `/api/local-models/status` need player-plane
sources.

## Profiles

The runtime is operated in one of three profiles, configured in
`nexus.toml` under `[runtime]` and reported in `/runtime/status`:

| Profile    | Who runs the processes | What `nexus up` does | What `nexus status` does |
|------------|------------------------|----------------------|--------------------------|
| `local`    | The supervisor (`nexus/runtime/`): spawns services detached with pidfiles and captured logs under `[runtime].state_dir` | Spawns enabled services, waits for health, fails loud with log excerpts | Merges supervisor process state (pid, port, uptime) with `/runtime/status` |
| `external` | You (or an IDE, a debugger, another orchestrator) | Health-checks the configured URLs; **spawns nothing**; nonzero exit if anything is down | Reads `/runtime/status` from `external.gateway_url` |
| `remote`   | A hosted operator | Confirms `<remote.base_url>/runtime/status` answers, using Access service auth when configured | Reads the remote runtime's status with the same authentication |

`nexus down`, `restart`, and `logs` are local-profile verbs: they manage or
read state that only exists when this machine's supervisor owns the
processes, and they fail loudly in other profiles. Under the remote profile
the CLI refuses them, like every command that would open a slot database or
this machine's runtime files, before they run (exit 3; see Command Contract
in `docs/cli.md`).

### Local profile mechanics

- Services are declared in `[runtime.services.<name>]`: an argv `command`
  template (`{python}`, `{host}`, `{port}`, `{log_config}` placeholders — no
  shell), `port`, `health_path`, extra `env`, an `enabled` mode, and an
  `autorestart` policy.
- The supervisor is pure Python and cross-platform by construction: process
  spawning uses `subprocess` with platform-appropriate detach flags,
  liveness checks never signal the process, and all observation is loopback
  TCP. Linux and Windows hosts are intended targets; nothing in the runtime
  path shells out or touches UNIX sockets.
- State lives under `[runtime].state_dir` (default `.nexus/runtime`):
  `<service>.pid.json` records pid/port/slot/start time; `<service>.log`
  captures stdout+stderr. Logs survive `nexus down` for postmortems.
- Each captured stream has one log-writer process
  (`nexus/runtime/log_capture.py`) that owns its file and its rotation. The
  supervisor starts the writer first, in a session of its own, and gives
  the service the writer's pipe as stdout and stderr, so a group signal to
  the service never reaches the writer. The writer ignores SIGINT and
  SIGTERM and ends only at end of input, when every process holding the
  pipe has exited, so it never drops a buffered line.
- The writer rotates while the service runs. Before a line that would take
  `<service>.log` past `[runtime.logs].max_bytes`, and at start when the file
  is already that large, it renames the file to `<service>.log.1` (older
  segments shift up to `backup_count`, the oldest is dropped) and opens a
  fresh file. It never splits a line across segments: a line longer than
  `max_bytes` gets a segment of its own. The writer's own errors go to
  `<service>.log.writer-error` beside the capture, which stays empty unless
  the writer fails.
- `nexus down`, `nexus up` over a stale pidfile, a restart, a failed start
  (before it prints the last log lines) and the foreground autorestart wait
  for the writer recorded in the pidfile (`log_writer_pid`), so two writers
  never hold one file. A writer still alive `[runtime.health].stop_grace_seconds`
  after its service stopped means another process still holds the output:
  the writer is killed and the command fails, naming its pid. A recycled pid
  that is no longer the file's writer is never waited on or signalled.
- A service's pidfile is written as soon as it is spawned, before the health
  wait. A failed start removes it only once its writer is gone, so a start
  whose writer cannot be waited out leaves the record, and the next start
  waits for that writer instead of starting a second one. If the pidfile
  write itself fails, the start stops its spawned service and waits out its
  writer before raising. The rollback of a failed `nexus up` stops only the
  service and writer pids successfully started by that invocation, and
  removes a record only if it still names that service pid; a rollback
  failure is attached to the original error as a note. When a
  service cannot be started at all, its writer is waited for (and killed
  after the grace) before the error is reported.
- The foreground supervisor reaps an exited service before it decides
  whether the service is live, so an ordinary exit reaches `autorestart`
  rather than reading as a live service that lost its writer. A dead writer
  triggers another service-liveness check before classification: a service
  that exited during the writer check also reaches the ordinary exit path.
- A writer counts as gone only when it has exited or when a `ps` probe ran
  and its command line does not name the file. A probe that cannot run (no
  `ps` on `PATH`, a non-zero exit while the pid is alive, or no answer within
  `stop_grace_seconds`) fails the command, names the pid and the file, and
  leaves the pidfile and the writer untouched.
- A live service whose writer has died writes into a broken pipe. The
  foreground supervisor stops such a service and fails, naming both pids.
  `nexus status` shows each service's writer (`WRITER`: `alive`, `dead`, or
  `-` for a pidfile written before writers existed), and `nexus doctor`'s
  `runtime.log_writers` check fails on a dead writer under a live service:
  restart that service by name (`nexus restart <service>`).
- `nexus logs -n N` continues into the rotated segments when the current
  file is shorter than `N`, reading at most `max_tail_bytes` of log text in
  all, and `-f` follows across every rotation. `--since MARK` reads a
  snapshot of the segment chain and waits out a rotation in progress for at
  most `stop_grace_seconds`, whether a segment is missing or the segments
  keep changing identity; the empty mark `0:0:0` is refused when that
  snapshot holds `<service>.log.<backup_count>`.
- `{log_config}` expands to `<state_dir>/logging.json`, a
  `logging.config.dictConfig` document the supervisor writes from
  `[runtime.logs]` before spawning. The gateway and the mock OpenAI server
  pass it to uvicorn as `--log-config`: application and uvicorn loggers write
  to stdout (never a file of their own) through one `format`, which must
  render a log record at config load, not just parse. `level` applies to
  application loggers, `uvicorn` and `uvicorn.error`; `uvicorn.access` stays
  at INFO because uvicorn logs every response at INFO, so access records
  appear at any `level`. Successful (below 400) access records for
  `access_success_exclude_paths` are dropped while every 4xx and 5xx is
  kept.
- `nexus up --foreground` keeps the supervisor attached: it streams
  prefixed service logs to the console, honors `autorestart = "on-failure"`
  (bounded by `autorestart_max_retries`), and tears everything down on
  Ctrl+C. `./iris` is a thin alias for exactly this.
- `nexus up` refuses ports held by unmanaged processes and refuses to
  double-start; partial startups are rolled back so `up` is all-or-nothing.
  The refusal identifies the listener (pid, age, command) when `lsof` is
  available.
- `NEXUS_GATEWAY_PORT=<port>` runs the gateway on an alternate port with
  fully isolated state (`state_dir/gateway-<port>/`), so an agent or test
  session coexists with the desktop app's instance on one checkout.
  Fixed-port siblings (the mock provider) always belong to the default
  instance: an override instance borrows one only when the default state
  ledger proves the listener is managed (live pidfile on that port, and
  healthy), skips it loudly when it is not running, and never spawns its
  own — so the default stack starts cleanly in either order. A foreign
  listener answering the health path is still refused; overrides equal to
  a configured sibling port are rejected at startup. `nexus down` under
  the override stops only the override instance. The desktop shell never
  sets this — its `runtimeOrigin` is pinned to the configured port.
- The gateway keeps the launch lifecycle of the app-managed local model
  and its download worker, and captures both through the same log writer
  under the same `[runtime.logs]` policy: `local-model.log` (llama-server)
  and `local-model.download.log` (the download worker) are writer-owned
  captures, each with its `local-model.log.writer-error` or
  `local-model.download.log.writer-error` file. The llama-server port and
  `local-model.pid.json` are one machine-wide endpoint and record, like the
  fixed-port siblings that belong to the default instance, so both captures
  stay beside that record in the default instance's logs directory whatever
  `NEXUS_GATEWAY_PORT` says; read them with `nexus logs local-model` (or
  `local-model.download`) in a shell without that variable. Deactivation,
  a cancelled or failed download, and the next activation or download wait
  for the previous writer the same way the supervisor does. When the record
  of a just-spawned server or download cannot be written, its process group
  gets SIGTERM, then SIGKILL after `stop_grace_seconds`, and its writer is
  waited for (killed after the same grace) before the write error is
  reported. Every removal of
  `local-model.pid.json` or `local-model.download.json`, on failure paths
  too, waits for the writer the record names first. A record is released as
  "no longer ours" only when a `ps` probe of its pid ran and its command line
  lacks the server's or the worker's markers; a probe that cannot run (no
  `ps`, a non-zero exit while the pid is alive, or no answer within
  `[runtime.health].timeout_seconds`) fails the status read or the command
  and leaves the record and its writer untouched.

## CLI Surface

```
nexus up [--slot N] [--foreground] [--config PATH]
nexus down [service] [--config PATH]
nexus restart [service] [--slot N] [--config PATH]
nexus status [--config PATH]
nexus logs [service] [-n LINES] [-f] [--mark | --since MARK] [--config PATH]
nexus doctor [--target owner-host|owner-client|ci-runner] [--config PATH]
```

All verbs honor the global `--json` flag for machine-readable output.
`--config` points at an alternate `nexus.toml` (test harnesses, parallel
checkouts); spawned services receive its absolute path in the
`NEXUS_RUNTIME_CONFIG` environment variable so their `/runtime/status`
describes the config that actually launched them. Story commands use
`remote.base_url` when the active config (see The Runtime Home) has
`profile = "remote"`; an explicit `NEXUS_API_URL` still overrides the base
URL. Access credentials are attached only when that override has the same
origin as `remote.base_url`. A remote profile, or an override naming a
non-loopback host, refuses the CLI's direct-database and local-operator
commands; `docs/cli_reference.md` lists each command's transport.

`nexus logs SERVICE --mark` prints a mark of the capture's current end
(`<inode>:<size>:<crc32 of the first 256 bytes>`, or `0:0:0` before the
capture exists), and `--since MARK` prints every line written after it, in
order, across every rotation since; it fails loudly when the marked text has
left retention. The QA kit (`scripts/qa_shift/mission_prompt.md`) slices its
gateway-log evidence with them.

## Readiness Checks

`nexus doctor` answers "is this machine ready for its role?" with one
registry of read-only checks in `nexus/runtime/readiness.py` (issue #803).
It never creates, migrates, locks, or writes anything: database sessions are
read-only, and secrets are reported present, missing, or unreadable, never
printed. It exits 1 when any check fails and 0 otherwise. Text output is one
line per check; `--json` prints the machine-readable report. Liveness
(`/health`), readiness, and slot playability are three separate answers; this
is the second.

| Check | Roles | Depends on | Passes when |
| --- | --- | --- | --- |
| `config.valid` | all | — | the active `nexus.toml` (The Runtime Home) resolves and validates |
| `postgres.reachable` | owner-host | `config.valid` | the `postgres` database accepts the `[api.database]` connection contract |
| `postgres.extensions` | owner-host | `postgres.reachable` | `vector` and `postgis` are in `pg_available_extensions` |
| `template.present` | owner-host | `postgres.reachable` | `NEXUS_template` exists |
| `template.migrations_current` | owner-host | `template.present` | its `schema_migrations` stamps match `migrations/` exactly |
| `slots.migrations_current` | owner-host | `template.present` | every probed slot that exists matches `migrations/`; an absent slot is reported, not failed |
| `template.idf_analyzer_current` | owner-host | `template.present` | `memory_idf_corpora` holds exactly the `narrative` and `retrograde_summary` rows, each keyed to the live server's `pg_catalog.english/v1/<server_version_num>`; a stale key or a missing or unexpected row names `python scripts/rebuild_memory_idf.py --template`; a missing table names `python scripts/migrate.py --template` while migration 114 is pending, and once 114 is stamped (only hand damage removes the table) says to restore the database from a backup or recreate it |
| `slots.idf_analyzer_current` | owner-host | `template.present` | the same for every probed slot that exists, naming `python scripts/rebuild_memory_idf.py --slot N` (plus `--write-locked-slot` for a locked slot); an absent slot is reported, not failed |
| `template.story_identity_absent` | owner-host | `template.present` | `story_identity` exists and holds no row; a row names `psql -d NEXUS_template -c 'DELETE FROM public.story_identity'`, and a missing table names `python scripts/migrate.py --template` |
| `slots.story_identity_present` | owner-host | `template.present` | every probed slot that exists holds exactly one `story_identity` row; no row names `python scripts/backfill_story_identity.py --slot N`, a missing table names `python scripts/migrate.py --slot N` (each plus `--write-locked-slot` for a locked slot); an absent slot is reported, not failed |
| `tools.pg_dump` | owner-host | `config.valid` | `pg_dump` resolves on `PATH` or `[api.database].tool_search_paths` |
| `ui.bundle` | owner-host | — | `ui/dist/public/index.html` exists |
| `secrets.seat_providers` | owner-host | `config.valid` | every key the model seats in use read is present (Required Keys and Headless Hosts); each account is listed as present, missing, or unreadable, and an unreadable store (a locked or unresponsive Keychain, or no `security` on `PATH`) fails the check with that store's remediation |
| `runtime.log_writers` | owner-host | `config.valid` | no live supervised service runs without the log writer its pidfile records; a dead writer names `nexus restart <service>` (restart the service by name) |
| `gateway.reachable` | owner-client | `config.valid` | the profile's gateway answers `/runtime/status` with the runtime's auth headers |
| `gateway.version` | owner-client | `gateway.reachable` | client and runtime report the same `nexus` version |
| `reachability.gate` | ci-runner | `config.valid` | `python -S scripts/check_reachability.py` passes |

Each report entry carries `id`, `targets`, `status` (`pass`, `fail`, or
`skip`), `observed`, `depends_on`, and `remediation`. A check whose
dependency did not pass is skipped, and its `observed` names the check that
failed at the root of the chain. The report adds `schema_version`, `target`,
`ok` (no check failed), and `omitted`. Stamps a database carries that this
checkout lacks fail the migration checks too: the code is older than the
schema.

`[runtime.readiness]` in `nexus.toml` bounds the checks:
`gateway_timeout_seconds` for the owner-client probe,
`reachability_timeout_seconds` for the gate, and `slots` for the slot
databases read. PostgreSQL checks connect exactly as the runtime does, so
`[api.database].connect_timeout_seconds` bounds them. With
`NEXUS_KEYRING_DISABLE=1`, `secrets.seat_providers` reads environment
variables only and says so.

CI runs `nexus doctor --target ci-runner --json` in
`.github/workflows/reachability-check.yml` and uploads the report. To
reproduce it, run `poetry run nexus doctor --target ci-runner --json` from a
checkout whose own `poetry install` provides the `nexus` package, with
`NEXUS_HOME` and `NEXUS_RUNTIME_CONFIG` unset. In a worktree that shares the
main checkout's venv, run `PYTHONPATH=$PWD python -m nexus.cli doctor --target
ci-runner --json` instead. The doctor checks the checkout that its imported
`nexus` package belongs to; the working directory does not change this.

`/runtime/status` carries the checks the gateway evaluates in-process
(`config.valid`, `tools.pg_dump`, `ui.bundle`): the gateway's own `PATH` and
build directory are the ones that matter to it. Guest-host checks, slot
playability, and `nexus init` are later slices of #803.

## The Runtime Home

The checkout holds code; the runtime home holds the active `nexus.toml` and
the runtime's mutable data (issue #820). `nexus/runtime/home.py` is the one
resolver for both: the configuration loader, the supervisor, player
preferences, local-model state, the usage ledger, the settings endpoint,
`/runtime/status`, LORE, and the CLI all ask it which config is active and
what a relative directory is relative to. The working directory never
selects a configuration.

| `NEXUS_HOME` | `NEXUS_RUNTIME_CONFIG` | Active config | Relative directories resolve under |
|---|---|---|---|
| unset | unset | the checkout's `nexus.toml` | the checkout (developer mode) |
| unset | set | that file | the checkout |
| set | unset | `$NEXUS_HOME/nexus.toml` | `$NEXUS_HOME` |
| set | the same file | `$NEXUS_HOME/nexus.toml` | `$NEXUS_HOME` |
| set | a different file | refused with a `RuntimeError` naming both | — |

- `NEXUS_HOME` locates the home; it is not another configuration system.
  It must be an absolute path, and an empty value counts as unset.
- `NEXUS_RUNTIME_CONFIG` stays the supervisor's spawn seam. `--config`
  outranks it, as before, and is held to the same agreement with
  `NEXUS_HOME`, so two active configurations cannot exist. Spawned services
  inherit `NEXUS_HOME` and receive the resolved config in
  `NEXUS_RUNTIME_CONFIG`, so they resolve the same home.
- A path passed to `load_settings(path)` or `settings_path_scope` is a
  per-call override and is not checked against the locators.
- Absolute configured directories are used as configured; `~` is expanded.
- Tests that point `NEXUS_RUNTIME_CONFIG` at temporary configs would be
  refused under an exported `NEXUS_HOME`, so `tests/conftest.py` clears it
  for the session and the QA lane's generated `runtime_env.sh` unsets it.

| Layout entry | Location | Holds |
|---|---|---|
| `state_dir` | `[runtime].state_dir` | pidfiles, `logging.json`, `preferences.toml`, local-model state |
| `logs_dir` | the same directory | captured `<service>.log` files and rotated segments |
| `usage_dir` | `[usage].usage_dir` | usage and prompt-window ledgers |
| `uploads_dir` | `ui/client/public` | `character_portraits/` and `place_images/` |
| `models_dir` | `models` | model directories named by `local_path` and `model_path` keys |
| `cache_dir` | `.nexus/cache` | reserved for derived caches |
| `backups_dir` | `.nexus/backups` | reserved for backups |

The last four have no configuration key yet: each gains one in the slice
that gives it a runtime owner. Until then the upload endpoints and static
mounts serve the checkout's `ui/client/public` even when `NEXUS_HOME` is
set, and model paths stay exactly as configured.

`nexus home plan [--to DIR]` is a read-only dry run of moving the
checkout's runtime data into a home. Before the move, run it as
`nexus home plan --to DIR` with `NEXUS_HOME` unset: until `DIR/nexus.toml`
exists, exporting `NEXUS_HOME=DIR` makes every command, this one included,
fail on the missing config. Once the home holds its config, the target
defaults to `NEXUS_HOME`. For the active config, every file under the state,
usage, cache, backup and upload directories, and every configured model
directory, it prints a status, the current and proposed paths, and the size
and SHA-256. A symlink is reported with its target and never followed, in
the checkout or in the target; that includes a symlinked `nexus.toml`, which
is reported as the link the locator selected, not as the file it points to.
`move` means the proposed path is free, `conflict` that it is taken,
`in-place` that the file stays where it is, and `missing` that a configured
model is not on disk. A destination is taken when it exists or when a path
on the way to it inside the target is a file or a symlink; the entry names
that path (`conflict_with` in `--json`, "blocked by" in text). A file is
`in-place` when it is already where the target layout puts it, when its
state or usage directory is configured as an absolute path, or when its
model directory is outside the checkout (an external drive or a shared
cache); a model directory inside the checkout moves to
`<home>/models/<name>`. It also lists the `nexus.toml` keys a move must
rewrite, and every path has one owner so each rewritten key names a
directory that receives exactly that model's files. It refuses, before
checksumming anything:

- a target that is the checkout, sits inside it, contains it, or is or sits
  beneath an existing file;
- two model paths that nest or name one directory, directly or through a
  symlink;
- a model path that is or contains the checkout, or that overlaps the active
  config or a state, usage, cache, backup or upload directory;
- two models that would land on one destination, including a moving model
  whose destination overlaps a model that stays in place.

It creates nothing. It reads every inventoried file in full to checksum it,
model weights included, and prints nothing until it finishes, so on a large
model store it runs for minutes. Moving files, re-anchoring uploads and
static mounts, slot-namespacing assets (which rewrites asset path rows and
needs PostgreSQL validation), and teaching the Tauri shell the home are the
next slices.

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
- **Remote Access clients:** the `cloudflare_access_client_id` and
  `cloudflare_access_client_secret` accounts live in the same `nexus-api`
  platform store. With `NEXUS_KEYRING_DISABLE=1`, their environment fallbacks
  are `CLOUDFLARE_ACCESS_CLIENT_ID_API_KEY` and
  `CLOUDFLARE_ACCESS_CLIENT_SECRET_API_KEY`.

### Required Keys and Headless Hosts

`GET /api/secrets/status` adds `required` and `required_by` (`seat`, `model`)
to each masked row. Skald, World State, the wizard, and the experience,
correspondence, entity-maturation, and summary seats resolve from `nexus.toml`
and the player's wizard preference. With `?slot=N` (the card passes the active
slot, and `PUT /api/secrets/{provider}` accepts the same parameter) they
resolve as that slot's turns do: its Skald and World State pins apply, and
seats that follow the story use its Skald. A seat that fails to resolve fails
the request with a detail naming the seat, where its model came from, and the
repair. Offline judgment, the display-only `global.model.default_model`, the
experience seat while `[orrery.experiences] enabled = false`, the maturation
seat while `[orrery.retrograde.maturation] enabled = false`, and keyless
providers never require a key. The API KEYS card lists required keys first,
marks a missing one with the warning state, dims the rest, shows a status
failure inside the card (so the Model card stays usable to repair a retired
pin), and re-reads the rows after the Model card changes a story pin. Status
and verification re-read the store on every request, past the gateway's
per-process key cache, so a key rotated outside the app shows at once; the
card asks for status again each time the pane opens. A store that is locked or
cannot be reached fails the card with its remediation (status and `PUT` answer
503) instead of reporting the key absent. Verification remains an explicit
click that is never stored; any status refresh, including a key replacement,
clears the Verified mark.

A host without a browser uses the same card through an SSH tunnel to its
loopback gateway (port 8002 by default), not another entry path:

```
ssh -N -L 8002:127.0.0.1:8002 <user>@<host>
```

Open `http://127.0.0.1:8002` locally and commit each key in Settings → API
Keys. If your own machine already serves a gateway on 8002, forward any free
local port instead (`-L 8012:127.0.0.1:8002`, then open
`http://127.0.0.1:8012`); the page and its API calls share that origin. The
gateway keeps its `127.0.0.1` bind, the key crosses only the SSH session to
`PUT /api/secrets/{provider}`, and it lands in the host's platform store, never
on a command line or in a file on the host.

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
5. For an Access-protected remote, resolve and send the configured service
   token headers without following redirects.
6. Run `nexus down` on quit.

Nothing else about NEXUS internals — slots, databases, model processes,
embedders — leaks across this boundary.

The Tauri shell added for issue #399 implements this contract in
`ui/src-tauri/`; see `docs/desktop.md` for run/build commands, the
checkout-level desktop config, and the preserved browser workflow.

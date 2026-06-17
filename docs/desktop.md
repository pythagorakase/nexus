# NEXUS Desktop Shell

Issue #399 adds a native shell around the managed runtime from issue #396. The
shell is deliberately thin: it launches or attaches to the documented runtime,
waits on `GET /runtime/status`, then navigates its webview to the runtime
origin. The PWA remains the product UI.

## Run It

```bash
npm --prefix ui run desktop:dev
```

The dev command builds the PWA first because the desktop shell points at the
gateway origin, not at Vite. Once the runtime is ready, the Tauri loading page
replaces itself with `http://127.0.0.1:8002` by default.

This is intentionally not a hot-reload path. Use the browser workflow below for
Vite HMR, Playwright, Safari/Chrome comparison, and agent-driven UI debugging.

Build a local macOS app bundle with:

```bash
npm --prefix ui run desktop:build
```

## Runtime Configuration

The obvious checkout-level config file is:

```text
ui/src-tauri/nexus.desktop.json
```

It defines the runtime origin, status path, auth header, and CLI command:

```json
{
  "runtimeOrigin": "http://127.0.0.1:8002",
  "statusPath": "/runtime/status",
  "authHeader": "X-Nexus-Auth",
  "authTokenEnv": "NEXUS_AUTH",
  "runtimeCommand": ["poetry", "run", "nexus"],
  "startArgs": ["--json", "up"],
  "stopArgs": ["--json", "down"],
  "workingDirectory": "../..",
  "commandTimeoutSeconds": 120
}
```

For a machine-local override, set `NEXUS_DESKTOP_CONFIG=/absolute/path/to/desktop.json`.
For a quick origin override, set `NEXUS_DESKTOP_RUNTIME_ORIGIN`.

The default command is development-friendly: it invokes the `nexus` CLI through
Poetry from the repo root. Packaged or globally installed environments can set
`runtimeCommand` to `["nexus"]` without changing the shell code.

## Ownership Rules

- If `/runtime/status` is already healthy, the shell attaches and does not stop
  the runtime on quit.
- If the shell runs the start command, it records ownership and runs the stop
  command on quit.
- The shell talks only to the runtime contract: origin, status surface, auth
  header, and CLI entrypoint.
- If startup fails before a window can be shown, the shell writes
  `~/Library/Logs/NEXUS/desktop.log` on macOS and shows a native alert.
- The bundled loading page has a restrictive local CSP. After navigation, the
  runtime origin controls its own HTTP response headers.

## Browser Workflow

The browser workflow remains intact for agent-driven testing and debugging:

```bash
nexus up
npm --prefix ui run dev
```

Then point Safari, Chrome, or Playwright at `http://localhost:5001`. Vite still
proxies API, websocket, and runtime-upload routes to the gateway.

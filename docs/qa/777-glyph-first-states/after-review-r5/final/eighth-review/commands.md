# Eighth Review Commands

The single full regeneration uses the checked-in 4123-second bound and writes
to scratch for comparison against `743ddab3` before replacing the shipping
receipt. UI suite invocations and plant children are bounded at 589 seconds.
Reachability keeps the secret-store guard active and unsets PG/live/secret-store
flags. Scope is `ui/` and `docs/`; the coordinator gate at `198e4e03` stands.

## Media Regressions

```sh
npm --prefix ui test -- media-state-shades
```

82 passed. [Complete output](unit.log).

## Check and Build

```sh
npm --prefix ui run check
npm --prefix ui run build
```

Both exit 0. [Check output](check.log), [build output](build.log).

## Reachability

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_SECRET_STORE \
  PYTHONPATH="$PWD" /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

54 passed. Secret-store guard active; `nexus-api` and disposable keychain denied.
[Complete output](reachability.log).

Codex, GPT-6.

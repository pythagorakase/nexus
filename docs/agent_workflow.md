# Agent Workflow

This repository favors autonomous, end-to-end agent work once the task scope is
clear. Use this workflow for normal implementation tasks unless the user gives
more specific instructions.

## Branches, Commits, and PRs

- Create a feature branch for implementation work unless the user explicitly
  asks for a direct commit to `main`.
- Commit intentionally as useful work lands. Do not leave completed changes
  unstaged when pausing or handing off.
- Open a ready-for-review PR autonomously when the branch is validated. Use a
  draft PR only when the user explicitly asks for one.
- Validate against the full gate before opening or merging a PR:
  `NEXUS_RUN_POSTGRES=1 poetry run pytest` with `NEXUS_GATEWAY_PORT` and
  `NEXUS_API_URL` unset. The PostgreSQL-gated tests are where fixture debt
  accumulates; a run that skips them is not the gate.
- The secret-store guard is a mandatory part of the gate. `tests/conftest.py`
  installs `tests/secret_store_guard.py` before collection and stops the
  session (exit 4) if collection removes it or if CPython's private
  `subprocess.Popen._execute_child` hook has changed shape. Before trusting a
  gate result, confirm the final terminal summary (or the run header, which
  `-q` hides) reads `secret-store guard: active; nexus-api: denied`, which
  requires `NEXUS_RUN_LIVE_LLM` to be unset. Never pass `--noconftest`.
  - Tests use the `in_memory_secret_store` fixture.
    `NEXUS_RUN_SECRET_STORE=1` enables only the macOS integration test, whose
    keychain file must sit under pytest's base temp directory.
    `NEXUS_RUN_LIVE_LLM=1` sessions may read `nexus-api`, never write it.
    Both flags count only when set before pytest starts.
  - In the pytest process the guard covers the real backends, the `keyring`
    password functions, the password methods of every `keyring` backend
    class, and `security` spawns through `subprocess`, `os.system`,
    `os.posix_spawn*`, and `os.spawn*`. A `security` spawn runs only as an
    argv list that exactly matches an open backend or disposable-keychain
    scope, and never with `-s nexus-api` outside a live read. Any argument
    that merely names `security` (`/etc/security`, say) also fails the test.
  - Every child process gets `NEXUS_KEYRING_DISABLE=1`, whatever the opt-in
    flags and whatever its `env` says. A test whose child genuinely needs
    store access, such as the golden-path gate's API server, passes
    `env=secret_store_guard.store_access_env(...)` and says why.
  - Not covered: `os.exec*`, fork-then-exec, `pty.spawn`, multiprocessing's
    `fork_exec`, a renamed or linked copy of `security`, a child that runs
    `security` itself, and `ctypes` calls into the Security framework. The
    guard is not a protected-path write guard, and no launcher preflight runs
    outside pytest; those parts of #963 are not implemented yet.
- The owner-connection audit is opt-in: run a gate with
  `-p tests.dbname_audit`, or set `NEXUS_DBNAME_AUDIT=1` before pytest starts
  (`tests/conftest.py` reads it once and loads the same plugin), whenever a
  change must prove that no test reaches an owner database, as every #885
  slice does. `tests/dbname_audit.py` records the database named by every
  psycopg2 connection (`psycopg2.connect` however imported, SQLAlchemy and
  pool connections, and direct `psycopg2.extensions.connection` construction)
  and every asyncpg connection, from keyword arguments, DSN strings, and URLs
  before the socket opens, and from the server once it does. The summary
  lists the targets and ends `dbname audit: owner targets: none`; any
  `save_NN` or `NEXUS_template` target turns the run into a failure (exit 1)
  naming each owner target and the test that opened it, even when every test
  passed. `postgres`, `template0`, and disposable clones are allowed. Child
  processes are not audited: `pg_dump` and `psql` read `NEXUS_template` when
  `disposable_slot_database` clones it, and a routed gateway or nested pytest
  needs its own audit.
- Include a concise PR summary, validation commands, and any schema,
  configuration, or data-impact notes.

## Review Orchestration

- After opening a PR, create a heartbeat to check agent review orchestration,
  review comments, failed checks, or merge readiness.
- Verify review-ready markers only after the downstream Claude workflow
  succeeds.
- If initial Codex or Claude feedback is present, address actionable items,
  validate locally, push fixes, and merge/prune when required checks pass.
- Do not wait for or expect re-reviews after follow-up commits unless there is
  explicit evidence of another required review cycle.
- Delete obsolete heartbeats after the PR is merged, closed, or no longer worth
  checking.

## When to Pause

Pause and ask the user before merging only when:

- review feedback conflicts or would cause a behavioral regression;
- required checks fail in a non-obvious way;
- the change has destructive data or migration implications;
- the remaining decision is genuinely a product, story, or design choice.

Otherwise, keep the fix, validate, merge, and prune loop moving.

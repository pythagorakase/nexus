# Database Connections

`nexus.database` owns target and session resolution. Use `get_connection()` for
API transactions and `create_slot_engine()` for SQLAlchemy. All engine checkout
pings are enabled. `[api.database]` defines minimum/maximum pool connections,
`preflight_idle_seconds` (zero pings every checkout), and `application_name_prefix`.
SQLAlchemy starts connections lazily; its retained pool size is the minimum and
its overflow allowance is maximum minus minimum.

Backend labels are `<prefix>:<role>:<suffix>`: the roles are `sync` (including API
pools and direct psycopg2 clients), `asyncpg`, `sqlalchemy`, and `subprocess`.
The suffix is `NEXUS_GATEWAY_PORT` when set, otherwise the process ID. For example,
lane 8017 pooled sessions are `nexus:sync:8017`. Existing explicit libpq session
options remain supported; termination probes must verify the actual backend label.

Pooled checkout rejects closed or non-idle sessions and pings sufficiently idle
sessions before yielding. One replacement is allowed, with an INFO reason; a
second failure escapes. Transaction connection errors and failed rollbacks discard
the session. Ordinary SQL errors roll back and preserve reusable connections.

## Ambiguous Commits Must Not Be Replayed

A connection-level error from commit does not establish whether PostgreSQL
committed the transaction. `AmbiguousCommit` names the database and original
error, closes the failed connection, and is terminal. Never replay the mutation,
try another fallback strategy, or requeue a job in response. Direct transaction
owners can use `commit_transaction()` or `transaction()` to preserve this contract.
Generic retries cover provider rate limits/timeouts only. Where a caller cannot
identify the commit phase, even a raw (or wrapped) database connection error is
terminal. Heartbeats may recover only when their commit-aware context proves
commit was not attempted. Otherwise the scheduler stops dispatch and reports
`failed`; operators must
reconcile durable state before restarting it. This policy does not infer success
or failure, and does not create an automatic recovery migration.

Slot replacement calls `dispose_database(dbname)` before destructive work and
before returning, invalidating local pools and registered engines. SQLAlchemy
engine references remain registered after disposal so repeated resets invalidate
their replacement pools too. Replacement must quiesce work using that database;
disposal does not coordinate transactions in other processes.

## Schema Documentation

PostgreSQL comments are the schema reference (`\d+` in psql or
`MEMNON.get_schema_summary`); add a non-empty `COMMENT ON TABLE` and
`COMMENT ON COLUMN` with each new table and column. The PostgreSQL-gated
`tests/test_schema_documentation_pg.py` ratchet checks every table and column in
`public` and `assets`, excluding extension ownership through `pg_depend`
(`deptype = 'e'`). Legacy debt is listed by qualified object name and reason in
`config/schema_docs_baseline.json`. To retire an entry, establish its contract
from reader/writer code, cite that evidence in the comment migration, add the
comment, and remove the baseline entry in the same change; documented or removed
objects left in the baseline fail, as do new undocumented objects. Run with
`NEXUS_RUN_POSTGRES=1`; the test migrates disposable template clones and proves
that schema-only dumps and the actual new-story setup preserve comments. Enums,
functions, and views are inventoried but not enforced in this slice.

# Verification: Shadow-Schema Migration Tests on Disposable Databases (#885 B2-6)

## Owner-Sequence Snapshot Bracket

Head `1f70e54d`, rebased on `3e8e692e`.

The audited proof below ran between two read-only snapshots of every public
sequence on `save_02`, `save_05`, and `NEXUS_template`. Each snapshot ran in a
`READ ONLY` transaction:

```
Q="SELECT schemaname, sequencename, last_value FROM pg_sequences WHERE schemaname='public' ORDER BY 1,2"
for db in save_02 save_05 NEXUS_template; do
  psql -X -At -v ON_ERROR_STOP=1 -d $db -c "BEGIN READ ONLY; $Q; COMMIT" > before_$db.txt   # after_$db.txt for the second pass
  md5 -q before_$db.txt
done
```

The md5 is over the psql output (the `BEGIN` and `COMMIT` tags plus 48
`schema|sequence|last_value` rows per database).

| Database | Before | After |
| --- | --- | --- |
| `save_02` | `64b1a40d2587a91f94ab1d114f2fcdab` | `64b1a40d2587a91f94ab1d114f2fcdab` |
| `save_05` | `cd490177df0ae132a741f58bd3ccb016` | `cd490177df0ae132a741f58bd3ccb016` |
| `NEXUS_template` | `6279441154d15a9d08563f036952b0eb` | `6279441154d15a9d08563f036952b0eb` |

`cmp` reported each before and after pair identical.

## Audited Gate

Head `1f70e54d`, rebased on `3e8e692e`.

Gateway variables unset (`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL`):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit \
    tests/test_orrery/test_backstory_secrets_migration_pg.py \
    tests/test_orrery/test_court_patron_migration_pg.py \
    tests/test_orrery/test_distortion_migration_pg.py \
    tests/test_orrery/test_polymorphic_patron_migration_pg.py \
    tests/test_orrery/test_pursue_romance_migration_pg.py \
    tests/test_orrery/test_recruit_ally_migration_pg.py \
    tests/test_orrery/test_seek_redemption_migration_pg.py \
    tests/test_orrery/test_valence_float_migration_pg.py \
    tests/test_orrery/test_build_venture_migration_pg.py \
    tests/test_orrery/test_claim_accounts_migration_pg.py \
    tests/test_orrery/test_mood_migration_pg.py \
    tests/test_orrery/test_geo_resolver_live.py \
    tests/test_orrery/test_weather_migration_pg.py \
    tests/test_dbname_audit.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_geo_resolver_*, qa640_mig077_*, qa640_mig084_*, qa640_mig085_*, qa640_mig086_*, qa640_mig087_*, qa640_mig088_*, qa640_mig090_*, qa640_mig091_*, qa640_mig092_*, qa640_mig095_*, qa640_mig096_*, qa640_weather_migration_*
dbname audit: owner targets: none
48 passed, 5 warnings in 8.61s
```

Exit status 0.


## Review Round (Astra)

Working tree on `f2e70ee4` with the review fixes applied (the commit that
adds this section). Gateway variables unset
(`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL`).

### Audited Gate

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_dbname_audit.py \
    tests/test_orrery/test_backstory_secrets_migration_pg.py \
    tests/test_orrery/test_court_patron_migration_pg.py \
    tests/test_orrery/test_distortion_migration_pg.py \
    tests/test_orrery/test_polymorphic_patron_migration_pg.py \
    tests/test_orrery/test_pursue_romance_migration_pg.py \
    tests/test_orrery/test_recruit_ally_migration_pg.py \
    tests/test_orrery/test_seek_redemption_migration_pg.py \
    tests/test_orrery/test_valence_float_migration_pg.py \
    tests/test_orrery/test_build_venture_migration_pg.py \
    tests/test_orrery/test_claim_accounts_migration_pg.py \
    tests/test_orrery/test_mood_migration_pg.py \
    tests/test_orrery/test_geo_resolver_live.py \
    tests/test_orrery/test_weather_migration_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_geo_resolver_*, qa640_mig077_*, qa640_mig084_*, qa640_mig085_*, qa640_mig086_*, qa640_mig087_*, qa640_mig088_*, qa640_mig090_*, qa640_mig091_*, qa640_mig092_*, qa640_mig095_*, qa640_mig096_*, qa640_weather_migration_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
50 passed, 5 warnings in 9.82s
exit 0
```

### Offline Run of the Audit's Own Tests

The three PostgreSQL cases skip offline; both owner-session cases run.

```
$ $PY -m pytest -q tests/test_dbname_audit.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
10 passed, 3 skipped, 5 warnings in 0.66s
exit 0
```

### Owner Session Counters for the Negative Case

`pg_stat_database.sessions` for the six owner databases, read with
`psql -X -At -d postgres` (the maintenance database) immediately before and
after the two owner-session cases (`exit 0`, `3 passed` in 1.44s, ending
23:58:27):

```
$ Q="SELECT datname, sessions FROM pg_stat_database WHERE datname IN ('save_01','save_02','save_03','save_04','save_05','NEXUS_template') ORDER BY 1"
$ psql -X -At -d postgres -c "$Q"   # before, then after
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit \
    tests/test_dbname_audit.py::test_owner_session_starts_no_owner_backend \
    tests/test_dbname_audit.py::test_session_naming_an_owner_is_refused_and_fails
before                 after
NEXUS_template|43091 NEXUS_template|43091
save_01|106347 save_01|106347
save_02|11721 save_02|11721
save_03|868 save_03|868
save_04|2836 save_04|2836
save_05|8722 save_05|8722
```

Every counter is unchanged. `test_owner_session_starts_no_owner_backend`
runs the same bracket inside the test: its parent environment carries
`PGHOSTADDR=127.0.0.1`, `PGPORT`, `PGDATABASE=save_01`, `PGSERVICE`, and
`PGSSLMODE`; the child asserts that `PGHOST` (the missing socket directory)
is its only libpq variable, that each owner call raises
`OwnerDatabaseConnectionRefused`, and that the libpq spy loaded ahead of the
audit saw no call to `psycopg2._connect` or asyncpg's `_connect_addr`.

The counters are not quiet on their own. Sampled with nothing of this order
running, `save_01` rose by 1 every five seconds (106330 to 106335 from
23:56:59 to 23:57:24; `pg_stat_activity` shows the owner's
`nexus:sync:48744` client on it), and during a concurrent builder's gate
`NEXUS_template` rose by 7 to 12 in each four-second window (`pg_dump` for
template clones). A single strict bracket therefore flaked; the test now runs
the child up to five times and clears each owner database once one bracket
leaves its counter still. The child names every owner database on every run,
so an owner connection from it would move that counter in every bracket and
fail the test.

### Mutation Checks

With the constructor sweep replaced by the old two-attribute swap,
`test_constructors_imported_before_the_audit_are_audited` fails
(`1 failed, 12 passed`). With the connect-time raise removed (recording
only), both owner-session cases, the counter case, and the preloaded case fail
(`4 failed, 9 passed`), each child showing libpq's own
`OperationalError` on the missing socket directory instead of the refusal.

### Linters

```
$ $PY -m black --check tests/dbname_audit.py tests/test_dbname_audit.py
All done!
2 files would be left unchanged.
$ $PY -m flake8 tests/dbname_audit.py tests/test_dbname_audit.py
(no output; exit 0)
$ $PY -m mypy -p tests.dbname_audit -p tests.test_dbname_audit
Success: no issues found in 2 source files
```
